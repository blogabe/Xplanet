"""Management uses disposable command stubs; never host installers or jobs."""
import os
import re
import fcntl
import pty
import select
import signal
import shlex
import sys
import subprocess
import time
import termios
import struct

from pathlib import Path

from .support import PROJECT, Sandbox, copy_launcher

DASHBOARD='snapshot\t2026-11-04 12:00Z\n'+'\n'.join('unknown\t'+title+'\tsource-detail; freshness not assessed' for title in ('Clouds','Earthquakes','Storms','Volcanoes','Satellites','Eclipses','Santa'))


class ManagementTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.scripts = self.root / 'scripts'
        self.scripts.mkdir()
        self.entry = self.scripts / 'xplanet.sh'
        copy_launcher(self.entry)
        self.write_script(self.scripts / 'run-configurator', 'exit 3\n')
        self.trace = self.base / 'calls'
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.env = {**os.environ, 'PATH': f'{self.bin}:/usr/bin:/bin',
                    'TRACE': str(self.trace), 'PYTHON_RESULT': '0', 'TERM': 'dumb'}
        # CI selects its test interpreter globally; each sandbox owns overrides.
        self.env.pop('TOTALMARKER_PYTHON', None)
        # A sandbox without .git must not discover the surrounding CI checkout.
        self.env['GIT_CEILING_DIRECTORIES'] = str(self.root.parent)
        self.write_script(self.scripts / 'run-totalmarker',
                          'if [ "$1" = --python-path ]; then\n'
                          '  [ "$PYTHON_RESULT" = 0 ] || exit 2\n'
                          '  echo /fixture/python; exit 0; fi\n'
                          'echo "$*" >> "$TRACE"\n'
                          + "if [ \"$2\" = --dashboard ]; then cat <<'DASHBOARD'\n"+DASHBOARD+"\nDASHBOARD\nfi\n")
        self.write_script(self.scripts / 'xp-setup.sh', 'echo setup >> "$TRACE"\n')
        (self.scripts / 'lib/xplanet/python-runtime.zsh').write_text(
            'python_choose_runtime() { print -- "Fixture runtime selection"; return 0; }\n')
        self.write_script(self.bin / 'xplanet', 'exit 0\n')
        self.env.update(PROCESS_RESULT='1', JOB_RESULT='0', JOB_TABLE='PID Status Label')
        self.write_script(self.bin / 'pgrep', 'exit "$PROCESS_RESULT"\n')
        self.write_script(self.bin / 'launchctl',
                          '[ "$1" = print ] || exit 9\n'
                          '[ "$JOB_RESULT" = 0 ] || exit "$JOB_RESULT"\n'
                          'case "$JOB_TABLE" in *local.xplanet.desktop*) exit 0;; *) exit 113;; esac\n')
        self.write_script(self.bin / 'brew',
                          'case "$1" in --prefix) exit 1;; esac\n'
                          'echo "brew $*" >> "$TRACE"\n')
        (self.scripts / 'lib/xplanet/display.zsh').write_text(
            '\n'.join(f'{name}_xplanet() {{ print -- {name} >> "$TRACE"; }}'
                      for name in ('start', 'stop', 'restart')) + '\n')

    def write_script(self, path, body):
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)

    def calls(self):
        return self.trace.read_text().splitlines() if self.trace.exists() else []

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def terminal(self, answers=None, interrupt=False, eof=False, termination=None, pause_signal=None, pause_key=None, after_pause=None, menu_steps=(), resize=None, key_marker=None, startup_interrupt=False, confirm_interrupt=False):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH',
                    int(self.env.get('TEST_ROWS', 30)), int(self.env.get('TEST_COLS', 100)), 0, 0))
        terminal_before = termios.tcgetattr(slave)
        proc = subprocess.Popen([str(self.entry)], stdin=slave, stdout=slave,
                                stderr=slave, env=self.env, start_new_session=True,
                                preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
        output = b''
        try:
            deadline = time.monotonic() + 5
            marker = b'Reading saved health' if startup_interrupt else b'Choose: '
            while marker not in output and time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    output += os.read(master, 65536)
            self.assertIn(marker, output)
            if self.env.get('TERM') == 'xterm-256color' and b'\x1b[?1049h' in output and not startup_interrupt:
                while termios.tcgetattr(slave)[3] & (termios.ICANON | termios.ECHO) and time.monotonic() < deadline:
                    select.select([], [], [], .001)
                self.assertFalse(termios.tcgetattr(slave)[3] & (termios.ICANON | termios.ECHO), output.decode())
            if resize:
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', *resize, 0, 0))
                os.kill(proc.pid, signal.SIGWINCH)
            if startup_interrupt:
                while not Path(str(self.trace)+'.child').exists() and time.monotonic() < deadline:
                    select.select([],[],[],0.01)
                self.assertTrue(Path(str(self.trace)+'.child').exists())
                os.write(master,b'\x03')
            elif interrupt:
                if termios.tcgetattr(slave)[3] & termios.ICANON:
                    # Prompt bytes precede zsh's blocking canonical read. Wait
                    # for this owned shell to sleep there, not a timing margin.
                    state=''
                    while proc.poll() is None and time.monotonic()<deadline:
                        observed=subprocess.run(['/bin/ps','-o','state=','-p',str(proc.pid)],
                                                capture_output=True,text=True,timeout=1)
                        state=observed.stdout.strip()
                        if state.startswith('S'):break
                    self.assertTrue(state.startswith('S'),(state,output))
                os.write(master,b'\x03')
            elif termination:
                os.kill(proc.pid,termination)
            else:
                os.write(master, b'\x04' if eof else answers.encode())
            pause_signalled = False
            confirmation_signalled = False
            next_choice_sent = False
            pause_choices = 0
            menu_steps = iter(menu_steps)
            next_step = next(menu_steps, None)
            while proc.poll() is None and time.monotonic() < deadline:
                if confirm_interrupt and not confirmation_signalled and b'Run start? [y/N]' in output:
                    # Prompt output can arrive before zsh enters its read.
                    # Require both canonical mode and the owned shell sleeping
                    # at that read, rather than racing it with a fixed delay.
                    state=''
                    while proc.poll() is None and time.monotonic()<deadline:
                        observed=subprocess.run(['/bin/ps','-o','state=','-p',str(proc.pid)],
                                                capture_output=True,text=True,timeout=1)
                        state=observed.stdout.strip()
                        if termios.tcgetattr(slave)[3] & termios.ICANON and state.startswith('S'):break
                    self.assertTrue(termios.tcgetattr(slave)[3] & termios.ICANON,output.decode())
                    self.assertTrue(state.startswith('S'),(state,output))
                    os.write(master,b'\x03');confirmation_signalled=True
                if key_marker and key_marker in output:
                    os.write(master, b'q')
                    key_marker = None
                if next_step and output.count(b'Choose: ') >= next_step[0]:
                    os.write(master, next_step[1])
                    next_step = next(menu_steps, None)
                if (pause_signal or pause_key) and not pause_signalled and b'Press any key to continue' in output and not (termios.tcgetattr(slave)[3] & (termios.ICANON | termios.ECHO)):
                    if pause_signal:
                        os.kill(proc.pid, pause_signal)
                    else:
                        os.write(master, pause_key)
                    pause_choices = output.count(b'Choose: ') + output.count(b'Troubleshooting choice')
                    pause_signalled = True
                if after_pause and pause_signalled and not next_choice_sent and output.count(b'Choose: ') + output.count(b'Troubleshooting choice') > pause_choices:
                    os.write(master, after_pause.encode())
                    next_choice_sent = True
                if select.select([master], [], [], .1)[0]:
                    output += os.read(master, 65536)
            self.assertIsNotNone(proc.poll(), output.decode())
            proc.wait(timeout=2)
            while select.select([master], [], [], .05)[0]:
                chunk = os.read(master, 65536)
                if not chunk:
                    break
                output += chunk
            self.assertEqual(termios.tcgetattr(master), terminal_before)
            return proc.returncode, output.decode()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            os.close(master)
            os.close(slave)

    def test_non_terminal_no_args_and_help_are_usage_without_actions(self):
        before = self.snapshot()
        for args in ([], ['--help']):
            result = subprocess.run([str(self.entry), *args], env=self.env,
                                    input='', text=True, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0)
            self.assertIn('Usage:', result.stdout)
            self.assertNotIn('Choose:', result.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, self.snapshot())

    def test_cancel_eof_interrupt_and_repeated_entry_do_not_mutate(self):
        before = self.snapshot()
        for kwargs in ({'answers': 'q\n'}, {'answers': '\nq\n'}, {'eof': True},
                       {'interrupt': True}, {'answers': 'q\n'}):
            code, _ = self.terminal(**kwargs)
            self.assertEqual(code, 130 if kwargs.get('interrupt') else 0)
            self.assertEqual(self.calls(), [])
            self.assertEqual(before, self.snapshot())

    def test_cancelled_config_and_advanced_navigation_do_not_claim_saved_settings(self):
        before = self.snapshot()
        code, output = self.terminal('invalid\n2\n8\n q\n')
        self.assertEqual(code, 0)
        self.assertIn('Configurator cancelled; desktop settings unchanged.', output)
        self.assertIn('Fixture runtime selection', output)
        self.assertIn('Advanced Python', output)
        self.assertNotIn('Advanced Python options', output)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_direct_config_propagates_module_cancellation(self):
        before = self.snapshot()
        result = subprocess.run([str(self.entry), 'config'], env=self.env,
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(before, self.snapshot())

    def test_detection_new_partial_existing_is_read_only(self):
        config = self.root / 'config'
        config.mkdir()
        for expected, names in [('new', []), ('partial', ['xp.def']),
                                ('existing', ['xp.conf', 'earth', 'totalmarker.toml'])]:
            for name in names:
                (config / name).write_text('')
            before = self.snapshot()
            code, output = self.terminal('q\n')
            self.assertEqual(code, 0)
            self.assertRegex(output, f'Custom setup +{expected};')
            self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), ['health --dashboard'])

    def test_lifecycle_requires_confirmation_and_retains_direct_commands(self):
        self.terminal('3\nn\n4\nn\n5\nn\nq\n')
        self.assertEqual(self.calls(), [])
        self.terminal('3\ny\n4\ny\n5\ny\nq\n')
        self.assertEqual(self.calls(), ['start', 'stop', 'restart'])
        for command in ('start', 'stop', 'restart'):
            result = subprocess.run([str(self.entry), command], env=self.env,
                                    capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls(), ['start', 'stop', 'restart'] * 2)

    def test_existing_dependencies_skip_install_and_start_is_optional(self):
        code, output = self.terminal('1\nn\n q\n')
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), ['setup'])
        self.assertNotIn('Install these missing', output)

    def test_missing_dependencies_require_review_and_can_cancel(self):
        (self.bin / 'xplanet').unlink()
        self.env['PYTHON_RESULT'] = '2'
        before = self.snapshot()
        code, output = self.terminal('1\nn\nq\n')
        self.assertEqual(code, 0)
        self.assertIn('Proposed changes', output)
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, self.snapshot())

    def test_invalid_python_override_is_not_replaced_by_install(self):
        self.env.update(PYTHON_RESULT='2', TOTALMARKER_PYTHON='/missing')
        code, output = self.terminal('1\n q\n')
        self.assertEqual(code, 0)
        self.assertIn('correct it before continuing', output)
        self.assertEqual(self.calls(), [])

    def test_empty_explicit_python_override_is_not_replaced(self):
        self.env.update(PYTHON_RESULT='2', TOTALMARKER_PYTHON='')
        _, output = self.terminal('1\n q\n')
        self.assertIn('correct it before continuing', output)
        self.assertEqual(self.calls(), [])

    def test_shell_definition_is_preserved_for_setup_validation(self):
        config = self.root / 'config'
        config.mkdir()
        (config / 'xp.def').write_text(' export XPLANET_BIN="$CUSTOM/bin/xplanet"\n')
        (self.bin / 'xplanet').unlink()
        self.write_script(self.scripts / 'xp-setup.sh',
                          '[ "${XPLANET_INSTALLED_BIN+x}" != x ] || exit 17\n'
                          'echo setup >> "$TRACE"\n')
        _, output = self.terminal('1\nn\n ')
        self.assertIn('setup will validate', output)
        self.assertEqual(self.calls(), ['setup'])

    def test_missing_homebrew_does_not_install_it(self):
        (self.bin / 'brew').unlink()
        (self.bin / 'xplanet').unlink()
        _, output = self.terminal('1\nq\n')
        self.assertIn('Install it separately', output)
        self.assertEqual(self.calls(), [])

    def test_missing_dependencies_install_only_after_review_then_setup_and_exit(self):
        (self.bin / 'xplanet').unlink()
        self.env.update(PYTHON_RESULT='2', FIXTURE_BIN=str(self.bin))
        self.write_script(self.bin / 'brew',
                          'if [ "$1" = --prefix ]; then echo "$FIXTURE_BIN/.."; exit 0; fi\n'
                          'echo "brew $*" >> "$TRACE"\n'
                          'if [ "$1" = install ] && [ "$2" = --formula ]; then\n'
                          ' printf "#!/bin/sh\\nexit 0\\n" > "$FIXTURE_BIN/xplanet"; chmod +x "$FIXTURE_BIN/xplanet"; fi\n'
                          'if [ "$1 $2" = "install python" ]; then touch "$FIXTURE_BIN/python-ready"; fi\n')
        self.write_script(self.scripts / 'run-totalmarker',
                          '[ -f "$FIXTURE_BIN/python-ready" ] || exit 2\necho /fixture/python\n')
        (self.scripts / 'lib/xplanet/python-runtime.zsh').write_bytes(
            (PROJECT / 'scripts/lib/xplanet/python-runtime.zsh').read_bytes())
        code, output = self.terminal('1\ny\n1\ny\ny\nn\n ')
        self.assertEqual(code, 0, output)
        self.assertEqual(self.calls(), [
            'brew tap blogabe/xplanet', 'brew trust blogabe/xplanet',
            'brew install --formula --build-from-source blogabe/xplanet/xplanet --without-giflib --with-cspice',
            'brew install python', 'setup'])
        self.assertEqual(output.count('Xplanet management'), 1)

    def test_failed_setup_does_not_offer_start(self):
        self.write_script(self.scripts / 'xp-setup.sh', 'exit 17\n')
        code, output = self.terminal('1\n q\n')
        self.assertEqual(code, 0)
        self.assertNotIn('Start the desktop now?', output)
        self.assertEqual(self.calls(), [])

    def test_update_without_upstream_explains_before_confirmation(self):
        before = self.snapshot()
        code, output = self.terminal('6\nq\n')
        self.assertEqual(code, 0)
        self.assertIn('Update unavailable:', output)
        self.assertNotIn('Run update?', output)
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, self.snapshot())

    def test_parent_checkout_upstream_does_not_leak_into_management_fixture(self):
        def git(*args):
            subprocess.run(['git', '-C', str(self.base), *args],
                           capture_output=True, text=True, check=True)
        git('init', '-b', 'main')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-m', 'Parent fixture')
        git('remote', 'add', 'origin', '/missing-fixture-remote')
        git('config', 'branch.main.remote', 'origin')
        git('config', 'branch.main.merge', 'refs/heads/main')
        code, output = self.terminal('6\nq\n')
        self.assertEqual(code, 0, output)
        self.assertIn('Update unavailable:', output)
        self.assertNotIn('Run update?', output)
        self.assertEqual(self.calls(), [])

    def test_update_with_upstream_can_cancel_before_action(self):
        def git(*args):
            return subprocess.run(['git', '-C', str(self.root), *args],
                                  capture_output=True, text=True, check=True)
        git('init', '-b', 'main')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-m', 'Fixture')
        git('remote', 'add', 'origin', '/missing-fixture-remote')
        git('config', 'branch.main.remote', 'origin')
        git('config', 'branch.main.merge', 'refs/heads/main')
        code, output = self.terminal('6\nn\nq\n')
        self.assertEqual(code, 0)
        self.assertIn('Run update?', output)
        self.assertNotIn('Update unavailable:', output)
        self.assertEqual(self.calls(), [])

    def test_saved_health_source_issues_are_not_inspection_failures(self):
        config = self.root / 'config'
        config.mkdir()
        (config / 'totalmarker.toml').write_text('')
        for status, expected in [(0, 'Done - Saved health completed.'),
                                 (1, 'Issues - Health check completed; source issues reported.'),
                                 (2, 'Problem - Health inspection failed (exit 2)')]:
            self.write_script(self.scripts / 'run-totalmarker', "cat <<'DASHBOARD'\n"+DASHBOARD+f"\nDASHBOARD\nexit {status}\n")
            code, output = self.terminal('7\n', pause_key=b'x', after_pause='q\n')
            self.assertEqual(code, 0, output)
            self.assertIn(expected, output)
            self.assertIn('source-detail', output)
            self.assertNotIn('Saved health exited', output)

    def test_missing_health_config_gives_hint_without_invoking_runner(self):
        before = self.snapshot()
        code, output = self.terminal('7\nq\n')
        self.assertEqual(code, 0)
        self.assertIn('Choose 1 for guided setup.', output)
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, self.snapshot())
        # The direct health command deliberately retains its existing contract.
        subprocess.run([str(self.entry), 'health'], env=self.env, check=True)
        self.assertEqual(self.calls(), ['health'])

    def test_saved_health_with_config_delegates(self):
        config = self.root / 'config'
        config.mkdir()
        (config / 'totalmarker.toml').write_text('')
        self.terminal('7\n q\n')
        self.assertEqual(self.calls(), ['health --dashboard', 'health --dashboard'])

    def test_cancelled_setup_returns_to_menu_without_start_offer(self):
        self.write_script(self.scripts / 'xp-setup.sh', 'exit 3\n')
        code, output = self.terminal('1\nq\n')
        self.assertEqual(code, 0)
        self.assertEqual(output.count('Xplanet management'), 2)
        self.assertNotIn('Start the desktop now?', output)
        self.assertNotIn('Setup completed.', output)
        self.assertEqual(self.calls(), [])

    def test_first_run_exits_after_optional_start(self):
        code, output = self.terminal('1\ny\n ')
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), ['setup', 'start'])
        self.assertEqual(output.count('Xplanet management'), 1)

    def test_menu_groups_one_action_per_row_and_confirms_broad_stop(self):
        code, output = self.terminal('4\nn\n5\nn\nq\n')
        self.assertEqual(code, 0)
        lines = [line.strip() for line in output.splitlines()]
        for label in ['Setup', 'Desktop', 'Maintenance', '4) Stop',
                      '2) Configurator', 'q) Exit']:
            self.assertIn(label, lines)
        self.assertFalse(any('3) Start' in line and '4) Stop' in line for line in lines))
        self.assertIn('Remove the desktop job and stop normal/configured Xplanet processes, including finite renders?', output)
        self.assertIn('Restart: remove the desktop job, stop normal/configured Xplanet processes, then start one desktop?', output)
        self.assertEqual(self.calls(), [])

    def enhanced_terminal(self):
        self.env['TERM'] = 'xterm-256color'
        self.env['TEST_ROWS'] = '34'
        self.env.pop('NO_COLOR', None)
        self.write_script(self.bin / 'tput',
                          'case "$1" in\n'
                          ' smcup) printf "\\033[?1049h";;\n'
                          ' rmcup) printf "\\033[?1049l";;\n'
                          ' cup) printf "\\033[H";;\n'
                          ' ed) printf "\\033[J";;\n'
                          ' sc) printf "\\0337";;\n'
                          ' rc) printf "\\0338";;\n'
                          ' el) printf "\\033[K";;\n'
                          ' cuu) printf "\\033[%sA" "$2";;\n'
                          ' sgr0) printf "\\033[0m";;\n'
                          ' setaf) printf "\\033[3%sm" "$2";;\n'
                          'esac\n')

    def test_status_distinguishes_process_detection_from_registration(self):
        for process, jobs, result, expected_process, expected_job in [
            ('0', 'PID Status Label', '0', 'running', 'not registered'),
            ('1', '- 0 local.xplanet.desktop', '0', 'not detected', 'registered'),
            ('2', '', '3', 'unknown', 'unknown'),
        ]:
            self.env.update(PROCESS_RESULT=process, JOB_TABLE=jobs, JOB_RESULT=result)
            _, output = self.terminal('q\n')
            self.assertIn('xplanet: ' + expected_process, output)
            self.assertIn('Job: ' + expected_job, output)
            self.assertIn('Health needs configuration; choose Guided setup (1)', output)
        self.assertEqual(self.calls(), [])

    def test_opening_never_executes_configuration_or_python(self):
        config = self.root / 'config'
        config.mkdir()
        (config / 'xp.def').write_text('print forbidden > "$TRACE"\n')
        self.write_script(self.scripts / 'run-totalmarker', 'echo forbidden > "$TRACE"\nexit 2\n')
        before = self.snapshot()
        self.terminal('q\n')
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, self.snapshot())

    def test_setup_is_recommended_for_new_or_partial_configuration(self):
        for state in ('new', 'partial', 'existing'):
            config = self.root / 'config'
            config.mkdir(exist_ok=True)
            if state == 'partial':
                (config / 'xp.def').write_text('')
            if state == 'existing':
                for name in ('xp.conf', 'earth', 'totalmarker.toml'):
                    (config / name).write_text('')
            _, output = self.terminal('q\n')
            self.assertEqual('Guided setup [recommended]' in output, state != 'existing')

    def test_alternate_screen_restores_on_exit_eof_and_signals(self):
        self.enhanced_terminal()
        for kwargs, expected in [({'answers': 'q\n'}, 0), ({'eof': True}, 0),
                                 ({'interrupt': True}, 130),
                                 ({'termination': signal.SIGTERM}, 143),
                                 ({'termination': signal.SIGHUP}, 129)]:
            code, output = self.terminal(**kwargs)
            self.assertEqual(code, expected, output)
            self.assertEqual(output.count('\x1b[?1049h'), 1)
            self.assertEqual(output.count('\x1b[?1049l'), 1)
            self.assertLess(output.index('\x1b[?1049h'), output.index('Xplanet management'))
            self.assertTrue(output.endswith('\x1b[?1049l'), repr(output[-80:]))
        self.assertEqual(self.calls(), [])

    def test_action_starts_at_top_and_stays_in_one_alternate_screen(self):
        self.enhanced_terminal()
        code, output = self.terminal('8\n', pause_key=b' ', after_pause='q\n')
        self.assertEqual(code, 0)
        heading = output.index('\x1b[34mAdvanced Python\x1b[0m')
        pause = output.index('Press any key to continue')
        self.assertIn('\x1b[H\x1b[J\r\n', output[:heading])
        self.assertLess(heading, pause)
        self.assertGreater(output.index('\x1b[?1049l'), pause)
        self.assertEqual(output.count('\x1b[?1049h'), 1)
        self.assertEqual(output.count('\x1b[?1049l'), 1)
        self.assertEqual(output.count('Xplanet management'), 2)
        self.assertNotIn('Details remain in terminal history', output)

    def test_long_action_output_is_not_truncated_and_failure_still_pauses(self):
        self.enhanced_terminal()
        self.write_script(self.scripts / 'lib/xplanet/display.zsh',
                          'start_xplanet() { for n in {1..100}; do print "detail $n"; done; '
                          'print -u2 "late failure"; return 17; }\n')
        code, output = self.terminal('3\ny\n', pause_key=b' ', after_pause='q\n')
        self.assertEqual(code, 0)
        # PTY output processing can add a carriage return during mode changes.
        # Check every complete line in order without requiring one CR spelling.
        details = re.findall(r'\bdetail (\d+)\r*\n', output)
        self.assertEqual(details, [str(n) for n in range(1, 101)])
        self.assertIn('late failure', output)
        self.assertIn('Last action: [!] Problem - Start exited 17.', output)
        self.assertEqual(output.count('Press any key to continue'), 1)
        self.assertEqual(output.count('\x1b[?1049h'), 1)
        self.assertEqual(output.count('\x1b[?1049l'), 1)

    def test_terminal_cleanup_after_helper_failure(self):
        self.enhanced_terminal()
        (self.scripts / 'lib/xplanet/configurator.zsh').unlink()
        code, output = self.terminal('2\n')
        self.assertEqual(code, 2)
        self.assertIn('missing configurator helpers', output)
        self.assertEqual(output.count('\x1b[?1049h'), output.count('\x1b[?1049l'))

    def test_color_opt_out_and_plain_ascii_fallback(self):
        self.enhanced_terminal()
        self.env['NO_COLOR'] = ''
        _, output = self.terminal('q\n')
        self.assertIn('\x1b[?1049h', output)
        self.assertNotIn('\x1b[34m', output)
        self.assertNotIn('\x1b[33m', output)
        self.env['TERM'] = 'dumb'
        _, output = self.terminal('q\n')
        self.assertNotIn('\x1b', output)
        self.assertTrue(output.isascii())
        self.assertIn('[?] Health needs configuration', output)

    def test_eof_after_auto_return_restores_normal_screen(self):
        self.enhanced_terminal()
        code, output = self.terminal('2\n\x04')
        self.assertEqual(code, 0)
        self.assertNotIn('Press Enter to return to management:', output)
        self.assertIn('Last action:', output)
        self.assertEqual(output.count('\x1b[?1049h'), output.count('\x1b[?1049l'))

    def test_auto_return_sequence_retains_last_result_without_extra_input(self):
        self.enhanced_terminal()
        code, output = self.terminal('2\n8\n 7\n6\n4\nn\n3\ny\nq\n')
        self.assertEqual(code, 0)
        self.assertNotIn('Press Enter to return', output)
        self.assertEqual(output.count('Press any key to continue'), 1)
        self.assertIn('Configurator cancelled; desktop settings unchanged.', output)
        self.assertIn('Python interpreter selected.', output)
        self.assertIn('Health needs configuration; choose Guided setup (1).', output)
        self.assertIn('Update has no remote-tracking upstream.', output)
        self.assertIn('Stop was not run.', output)
        last_screen = output.rsplit('\x1b[H\x1b[J', 1)[-1]
        self.assertIn('Last action: [+] Done - Start request accepted; rendering runs asynchronously.', last_screen)
        self.assertEqual(self.calls(), ['start'])
        self.assertEqual(output.count('\x1b[?1049h'), output.count('\x1b[?1049l'))

    def test_action_failure_stays_visible_and_preserves_command_output(self):
        self.enhanced_terminal()
        helper = self.scripts / 'lib/xplanet/display.zsh'
        with helper.open('a') as stream:
            stream.write("start_xplanet() { print -- 'fixture stdout'; print -u2 -- 'fixture stderr'; return 17; }\n")
        code, output = self.terminal('3\ny\n q\n')
        self.assertEqual(code, 0)
        self.assertIn('fixture stdout', output)
        self.assertIn('fixture stderr', output)
        last_screen = output.rsplit('\x1b[H\x1b[J', 1)[-1]
        self.assertIn('Last action: [!] Problem - Start exited 17.', last_screen)
        direct = subprocess.run([str(self.entry), 'start'], env=self.env,
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(direct.returncode, 17)
        self.assertEqual(direct.stdout, 'fixture stdout\n')
        self.assertEqual(direct.stderr, 'fixture stderr\n')

    def test_guided_installer_failure_returns_to_menu_with_error(self):
        (self.bin / 'xplanet').unlink()
        self.env['PYTHON_RESULT'] = '2'
        self.write_script(self.bin / 'brew',
                          '[ "$1" = --prefix ] && exit 1\n'
                          'echo "brew $*" >> "$TRACE"\nexit 17\n')
        code, output = self.terminal('1\ny\n q\n')
        self.assertEqual(code, 0)
        self.assertIn('Could not add the Xplanet tap.', output)
        self.assertIn('Last action: [!] Problem - Setup exited 1;', output)
        self.assertEqual(output.count('Xplanet management'), 2)
        self.assertEqual(self.calls(), ['brew tap blogabe/xplanet'])

    def test_guided_sections_and_completion_summary_keep_real_decisions(self):
        config = self.root / 'config'
        config.mkdir()
        for name in ('xp.def', 'xp.conf', 'earth', 'totalmarker.toml'):
            (config / name).write_text('')
        code, output = self.terminal('1\nn\n q\n')
        self.assertEqual(code, 0)
        for heading in ('Guided setup', 'Prerequisites', 'Configuration, data and schedules', 'Desktop'):
            self.assertIn('\r\n\r\n' + heading + '\r\n\r\n', output)
        self.assertIn('Start the desktop now? [y/N]', output)
        self.assertIn('Last action: [+] Done - Setup completed; desktop start skipped.', output)
        self.assertEqual(self.calls(), ['health --dashboard', 'setup'])

    def test_single_key_returns_without_enter_and_preserves_next_choice(self):
        self.enhanced_terminal()
        code, output = self.terminal('8\n 2\nq\n')
        self.assertEqual(code, 0)
        self.assertEqual(output.count('Press any key to continue'), 1)
        self.assertIn('Last action: [-] Cancelled - Configurator cancelled; desktop settings unchanged.', output)
        self.assertEqual(output.count('Xplanet management'), 3)
        self.assertNotIn('Choose a listed option', output)

    def test_pause_ignores_only_already_queued_newlines(self):
        self.enhanced_terminal()
        code, output = self.terminal('8\n\nx2\nq\n')
        self.assertEqual(code, 0)
        self.assertEqual(output.count('Press any key to continue'), 1)
        self.assertIn('Configurator cancelled; desktop settings unchanged.', output)
        self.assertEqual(self.calls(), [])

    def test_pause_eof_and_interrupt_restore_terminal(self):
        self.enhanced_terminal()
        for pause_key, pause_signal, expected in [(b'\x04', None, 0),
                                                  (None, signal.SIGINT, 130),
                                                  (None, signal.SIGTERM, 143)]:
            code, output = self.terminal('8\n', pause_signal=pause_signal, pause_key=pause_key)
            self.assertEqual(code, expected, output)
            self.assertIn('Press any key to continue', output)
            self.assertEqual(output.count('\x1b[?1049h'), output.count('\x1b[?1049l'))

    def test_key_returns_before_any_next_line_is_sent(self):
        self.enhanced_terminal()
        code, output = self.terminal('8\n', pause_key=b'x', after_pause='2\nq\n')
        self.assertEqual(code, 0, output)
        self.assertIn('Configurator cancelled; desktop settings unchanged.', output)
        self.assertEqual(output.count('Press any key to continue'), 1)

    def test_ctrl_c_key_during_pause_restores_terminal(self):
        self.enhanced_terminal()
        code, output = self.terminal('8\n', pause_key=b'\x03')
        self.assertEqual(code, 130, output)
        self.assertIn('Press any key to continue', output)
        self.assertEqual(output.count('\x1b[?1049h'), output.count('\x1b[?1049l'))

    def test_short_results_and_cancellations_do_not_pause(self):
        self.enhanced_terminal()
        code, output = self.terminal('2\n7\n6\n4\nn\nq\n')
        self.assertEqual(code, 0)
        self.assertNotIn('Press any key to continue', output)
        self.assertIn('Stop was not run.', output)
        self.assertEqual(self.calls(), [])

    def test_digits_highlight_without_executing_and_enter_selects(self):
        self.enhanced_terminal()
        code, output = self.terminal('8q')
        self.assertEqual(code, 0)
        self.assertIn('> \x1b[34m8) Advanced Python', output)
        self.assertNotIn('Press any key to continue', output)
        self.assertEqual(self.calls(), [])
        code, output = self.terminal('2\nq')
        self.assertEqual(code, 0)
        self.assertIn('Configurator cancelled; desktop settings unchanged.', output)

    def test_arrow_navigation_repeats_and_stops_at_boundaries(self):
        self.enhanced_terminal()
        for keys, selected in [('\x1b[A' * 3 + 'q', 1),
                               ('\x1b[B' * 12 + 'q', 10),
                               ('\x1b[B\x1b[B\x1b[A\nq', 2),
                               ('\x1bOB\nq', 2)]:
            code, output = self.terminal(keys)
            self.assertEqual(code, 0)
            self.assertIn(f'> \x1b[34m{"h" if selected==10 else selected})', output)
            self.assertEqual('Configurator cancelled; desktop settings unchanged.' in output, selected == 2)
        self.assertEqual(self.calls(), [])

    def test_partial_and_malformed_escape_input_does_not_activate(self):
        self.enhanced_terminal()
        # Acknowledge completed parsing; a wall-clock delay races on slow runners.
        helper = self.scripts / 'lib/xplanet/management-input.zsh'
        original=helper.read_text()
        self.assertEqual(original.count('        management_key_read || return 1'),1)
        helper.write_text(original.replace(
            '        management_key_read || return 1',
            '        management_key_read || return 1\n'
            '        print -rn -- __fixture_key_read__'))
        for keys in ('\x1b', '\x1b[', '\x1b[?x', '\x1b[1234567890123456789012345678901234567890~'):
            code, output = self.terminal(keys, key_marker=b'__fixture_key_read__')
            self.assertEqual(code, 0, output)
            self.assertNotIn('Guided setup\x1b[0m\r\n', output)
            self.assertEqual(self.calls(), [])

    def test_acknowledgement_consumes_escape_sequence_and_keeps_next_choice(self):
        self.enhanced_terminal()
        for key in (b'x', b'\n', b'\x1b[A', b'\x1bOP', b'\x1b[15~'):
            code, output = self.terminal('8\n', pause_key=key, after_pause='2\nq')
            self.assertEqual(code, 0, output)
            self.assertIn('Configurator cancelled; desktop settings unchanged.', output)
            self.assertNotIn('Prerequisites', output)
            self.assertEqual(output.count('Press any key to continue'), 1)

    def test_navigation_repaints_only_two_rows_and_refreshes_status_after_action(self):
        self.enhanced_terminal()
        probes = self.base / 'probes'
        self.env['PROBES'] = str(probes)
        self.write_script(self.bin / 'pgrep', 'echo process >> "$PROBES"; exit 1\n')
        self.write_script(self.bin / 'launchctl', 'echo jobs >> "$PROBES"; exit 0\n')
        code, output = self.terminal('8\x1b[A\x1b[B2\nq')
        self.assertEqual(code, 0)
        self.assertEqual(output.count('Xplanet management'), 2)
        self.assertEqual(probes.read_text().splitlines(), ['process', 'jobs'] * 2)
        self.assertIn('\x1b7\x1b8\x1b[16A\r\x1b[K', output)
        self.assertIn('Configurator cancelled; desktop settings unchanged.', output)
        # Relative row offsets stay correct with a longer header/result above.
        self.assertIn('q) Exit\r\n\r\nUp/Down', output)
        first = output.split('Choose: ', 1)[0]
        rows = first.split('\r\n')
        for number, offset in enumerate((16, 15, 12, 11, 10, 7, 6, 5, 4, 3), 1):
            item = next(i for i, row in enumerate(rows) if f'{"h" if number==10 else number}) ' in row)
            self.assertEqual(len(rows) - 1 - item, offset)

    def test_narrow_terminal_uses_numbered_scrollback_without_hiding_status(self):
        self.enhanced_terminal()
        self.env.update(TEST_ROWS='20', TEST_COLS='40')
        probes = self.base / 'probes'
        self.env['PROBES'] = str(probes)
        self.write_script(self.bin / 'pgrep', 'echo process >> "$PROBES"; exit 1\n')
        self.write_script(self.bin / 'launchctl', 'echo jobs >> "$PROBES"; exit 0\n')
        code, output = self.terminal('q\n')
        self.assertEqual(code, 0)
        self.assertEqual(probes.read_text().splitlines(), ['process', 'jobs'])
        self.assertEqual(output.count('Xplanet management'), 1)
        self.assertIn('Compact terminal: numbered input',output)
        self.assertRegex(output,r'Running scene +\[\?\] Not identified')
        self.assertNotIn('\x1b[?1049h',output)
        self.assertNotIn('\x1b7', output)

    def test_resize_to_small_terminal_restores_screen_and_retains_safe_input(self):
        self.enhanced_terminal()
        for keys, following in [('\x1b[B', b'2\nq\n'), ('\x1b2', b'\nq\n')]:
            code, output = self.terminal(keys, resize=(20,40), menu_steps=[(2, following)])
            self.assertEqual(code, 0, output)
            self.assertIn('Compact terminal: numbered input',output)
            self.assertIn('Configurator cancelled',output)
            self.assertEqual(self.calls(), [])
            self.assertEqual(output.count('\x1b[?1049h'), 1)
            self.assertEqual(output.count('\x1b[?1049l'), 1)

    def test_menu_control_keys_restore_terminal(self):
        self.enhanced_terminal()
        for key, expected in [('\x04', 0), ('\x03', 130)]:
            code, output = self.terminal(key)
            self.assertEqual(code, expected)
            self.assertEqual(output.count('\x1b[?1049h'), 1)
            self.assertEqual(output.count('\x1b[?1049l'), 1)
            self.assertEqual(self.calls(), [])

    def test_pause_is_noop_without_a_terminal(self):
        helper = self.scripts / 'lib/xplanet/management-view.zsh'
        result = subprocess.run(['/bin/zsh', '-c',
                                 'source "$1"; source "$2"; management_pause', 'fixture', str(helper), str(helper.with_name('management-input.zsh'))],
                                input='', capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_completed_configurator_changes_do_not_claim_only_a_view_was_saved(self):
        self.write_script(self.scripts/'run-configurator','exit 0\n')
        code,output=self.terminal('2\nq\n')
        self.assertEqual(code,0);self.assertIn('Configurator closed; saved files and selection retained. Desktop not restarted.',output)
        self.assertNotIn('View saved; desktop settings unchanged.',output);self.assertEqual(self.calls(),[])

    def test_uncertain_selection_is_reported_for_inspection_not_as_saved_or_cancelled(self):
        self.write_script(self.scripts/'run-configurator','exit 5\n')
        code,output=self.terminal('2\n q\n')
        self.assertEqual(code,0);self.assertIn('Selection outcome uncertain; inspect config/desktop.scene',output)
        self.assertNotIn('Configurator changes saved;',output);self.assertNotIn('Configurator cancelled;',output)
        self.assertEqual(self.calls(),[])


    def test_health_snapshot_is_explicit_cached_and_never_claims_live_or_running_scene(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        code,output=self.terminal('7\n',pause_key=b'x',after_pause='q\n')
        self.assertEqual(code,0,output);self.assertEqual(self.calls(),['health --dashboard','health --dashboard'])
        self.assertRegex(output,r'Snapshot +2026-11-04 12:00Z \(saved evidence, not a live access check')
        self.assertIn('[?] Clouds',output);self.assertRegex(output,r'Running scene +\[\?\] Not identified')
        self.assertNotIn('Dashboard pending',output)

    def test_invalid_selection_is_not_silently_presented_as_legacy(self):
        (self.root/'config').mkdir();(self.root/'config/desktop.scene').write_text('invalid')
        before=self.snapshot();code,output=self.terminal('q\n')
        self.assertEqual(code,0,output);self.assertIn('invalid or unavailable selector',output)
        self.assertNotRegex(output,r'Next start +custom');self.assertEqual(before,self.snapshot());self.assertEqual(self.calls(),[])

    def test_selection_dashboard_binds_metadata_without_certifying_resources(self):
        import hashlib,plistlib
        record={'schema':1,'review':{'root':str(self.root),'scene':'config/scenes/my-scene.conf','geometry':'1920x1080'}}
        raw=plistlib.dumps(record);identity=hashlib.sha256(raw).hexdigest()
        revision=self.root/'.state/xplanet/scenes'/identity;revision.mkdir(parents=True)
        (revision/'deployment.plist').write_bytes(raw);(self.root/'config').mkdir()
        (self.root/'config/desktop.scene').write_text('v1 '+identity+'\n')
        before=self.snapshot();code,output=self.terminal('q\n')
        self.assertEqual(code,0,output);self.assertRegex(output,r'Next start +my-scene \(1920x1080\); metadata verified, resources unchecked')
        self.assertRegex(output,r'Running scene +\[\?\] Not identified');self.assertEqual(before,self.snapshot());self.assertEqual(self.calls(),[])
        (revision/'deployment.plist').write_bytes(raw+b' ')
        code,output=self.terminal('q\n');self.assertIn('invalid or unavailable selector',output)


    def test_malformed_health_records_never_become_successful_snapshot(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        for status in (0,1,2):
            self.write_script(self.scripts/'run-totalmarker',f'echo malformed-result; exit {status}\n')
            code,output=self.terminal('7\n',pause_key=b'x',after_pause='q\n')
            self.assertEqual(code,0,output);self.assertIn('Problem - Health inspection failed',output)
            self.assertIn('no verified snapshot',output);self.assertNotIn('Saved health completed',output)

    def test_saved_health_global_warning_is_visible_and_cached_as_a_caveat(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        self.write_script(self.scripts/'run-totalmarker',"cat <<'DASHBOARD'\n"+DASHBOARD+"\nnote\tRecorded error log unavailable\nDASHBOARD\n")
        code,output=self.terminal('7\n',pause_key=b'x',after_pause='q\n')
        self.assertEqual(code,0,output);self.assertIn('Recorded error log unavailable',output)
        self.assertIn('[!] Status warning; review health details',output)


    def test_long_completed_result_uses_safe_redraw_instead_of_wrong_cursor_rows(self):
        self.enhanced_terminal();self.write_script(self.scripts/'run-configurator','exit 0\n')
        code,output=self.terminal('2\r',menu_steps=[(2,b'\x1b[Bq')])
        self.assertEqual(code,0,output)
        self.assertGreaterEqual(output.count('Xplanet management'),3)
        self.assertIn('Desktop not restarted.',output);self.assertEqual(self.calls(),[])


    def test_configurator_signal_exit_is_interruption_not_failure_or_rollback(self):
        for status in (129,130,143):
            self.write_script(self.scripts/'run-configurator',f'exit {status}\n')
            code,output=self.terminal('2\nq\n')
            self.assertEqual(code,0,output)
            self.assertIn('Configurator interrupted; completed saves/selections remain. Desktop not restarted.',output)
            self.assertNotIn('Problem - Configurator',output);self.assertEqual(self.calls(),[])

    def test_binary_evidence_is_historical_and_menu_never_executes_probe(self):
        import json
        evidence=self.root/'.state/configurator/binary-evidence.json';evidence.parent.mkdir(parents=True)
        evidence.write_text(json.dumps({'schema':1,'report':{'status':'reported','completed_utc':'2026-11-04T01:02:03+00:00'}}))
        before=self.snapshot();code,output=self.terminal('q\n')
        self.assertEqual(code,0);self.assertIn('Xplanet build',output)
        self.assertIn('reported 2026-11-04T01:02:03Z',output)
        self.assertIn('Features reported 2026-11-04T01:02:03Z; not rechecked',output)
        self.assertEqual(self.calls(),[]);self.assertEqual(before,self.snapshot())
        evidence.write_text('{broken')
        code,output=self.terminal('q\n');self.assertEqual(code,0)
        self.assertIn('Build features not checked; choose Troubleshooting (9)',output);self.assertEqual(self.calls(),[])

    def test_diagnostic_and_help_entries_are_discoverable_without_activation(self):
        self.enhanced_terminal();before=self.snapshot()
        for keys in ('9q','hq'):
            code,output=self.terminal(keys)
            self.assertEqual(code,0);self.assertIn('9) Troubleshooting...',output);self.assertIn('h) Help',output)
            self.assertNotIn('Capture renderer support now?',output);self.assertNotIn('Usage: scripts/xplanet.sh',output)
        self.assertEqual(self.calls(),[]);self.assertEqual(before,self.snapshot())

    def test_diagnostic_cancellation_is_immediate_and_has_no_probe(self):
        self.enhanced_terminal();before=self.snapshot()
        code,output=self.terminal('9\n3\nn\nq')
        self.assertEqual(code,0);self.assertIn('Renderer diagnostic was not run.',output)
        self.assertNotIn('Press any key',output);self.assertEqual(self.calls(),[]);self.assertEqual(before,self.snapshot())

    def test_diagnostic_routes_existing_command_and_keeps_unknown_distinct_from_failure(self):
        self.enhanced_terminal()
        self.write_script(self.scripts/'lib/xplanet/diagnostics.zsh',
            'renderer_diagnostics() { echo diagnostics >> "$TRACE"; print -- "fixture support evidence"; return "$DIAGNOSTIC_RESULT"; }\n')
        for status,message in (('0','Renderer support captured'),('1','renderer support remains unknown'),('2','Renderer inspection failed (exit 2)')):
            self.env['DIAGNOSTIC_RESULT']=status
            if self.trace.exists():self.trace.unlink()
            before=self.snapshot();code,output=self.terminal('9\n3\ny\n',pause_key=b' ',after_pause='q')
            self.assertEqual(code,0,output);self.assertIn('fixture support evidence',output);self.assertIn(message,output)
            self.assertEqual(output.count('Press any key'),1);self.assertEqual(self.calls(),['diagnostics'])
            self.assertEqual(before,self.snapshot());self.assertEqual(output.count('\x1b[?1049h'),1);self.assertTrue(output.endswith('\x1b[?1049l'))

    def test_troubleshooting_navigation_and_back_do_not_read_or_probe(self):
        self.enhanced_terminal()
        self.write_script(self.scripts/'run-totalmarker', 'echo forbidden >> "$TRACE"; exit 2\n')
        before = self.snapshot()
        for keys in ('9\nbq', '9\n4\nq', '9\n2\x1b[B\x1b[Aq', '9\n' + '\x1b[B' * 8 + '\nq'):
            code, output = self.terminal(keys)
            self.assertEqual(code, 0, output)
            for label in ('View renderer log', 'View saved renderer support', 'Check renderer support now', 'Back to management'):
                self.assertIn(label, output)
            self.assertNotIn('Press any key', output)
            self.assertNotIn('Capture renderer support now?', output)
            self.assertEqual(self.calls(), [])
            self.assertEqual(before, self.snapshot())
        self.assertIn('> \x1b[34m9) Troubleshooting...', output)

    def real_log_view(self):
        (self.root/'logs').mkdir()
        path = self.root/'logs/xplanet-error.log'
        pair = 'Warning: Resizing night map\nFor better performance, all image maps should be the same size as the day map\n'
        path.write_text('first diagnostic\n' + pair * 3 + 'last diagnostic\n')
        self.write_script(self.scripts/'run-totalmarker',
            'echo "$*" >> "$TRACE"\n' +
            'PYTHONPATH=' + shlex.quote(str(PROJECT/'scripts')) + ' exec ' + shlex.quote(sys.executable) +
            ' -P -s -B -m totalmarker --root ' + shlex.quote(str(self.root)) + ' "$@"\n')
        return path

    def test_filtered_renderer_log_pauses_before_submenu_redraw_without_config(self):
        self.real_log_view()
        for enhanced in (False, True):
            if enhanced:
                self.enhanced_terminal()
            if self.trace.exists():
                self.trace.unlink()
            before = self.snapshot()
            code, output = self.terminal('9\n1\n\n\n', pause_key=b'x', after_pause='b\nq\n')
            self.assertEqual(code, 0, output)
            self.assertEqual(self.calls(), ['log-view'])
            self.assertEqual(output.count('Warning: Resizing night map'), 1)
            self.assertIn('night: 3 occurrence(s), 2 repeat(s) hidden', output)
            self.assertIn('first diagnostic', output)
            self.assertIn('last diagnostic', output)
            self.assertEqual(output.count('Press any key to continue'), 1)
            report = output.index('first diagnostic')
            pause = output.index('Press any key to continue')
            redraw = output.index('Read existing logs/evidence', pause)
            self.assertLess(report, pause)
            self.assertLess(pause, redraw)
            self.assertNotIn('\x1b[H\x1b[J', output[report:pause])
            self.assertEqual(before, self.snapshot())

    def test_direct_log_view_does_not_acquire_menu_pause(self):
        self.real_log_view()
        before = self.snapshot()
        result = subprocess.run([str(self.entry), 'log-view'], env=self.env,
                                input='', capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2 repeat(s) hidden', result.stdout)
        self.assertNotIn('Press any key', result.stdout)
        self.assertNotIn('Troubleshooting', result.stdout)
        self.assertEqual(self.calls(), ['log-view'])
        self.assertEqual(before, self.snapshot())

    def test_absent_renderer_log_is_clear_and_stays_visible_until_acknowledged(self):
        self.enhanced_terminal()
        before = self.snapshot()
        code, output = self.terminal('9\n1\n', pause_key=b'x', after_pause='q')
        self.assertEqual(code, 0, output)
        self.assertIn('No renderer log exists at logs/xplanet-error.log. Nothing was created.', output)
        self.assertIn('Renderer log is absent; no log to display.', output)
        self.assertEqual(output.count('Press any key to continue'), 1)
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, self.snapshot())

    def test_log_warnings_and_failures_pause_and_preserve_output(self):
        self.enhanced_terminal()
        (self.root/'logs').mkdir()
        (self.root/'logs/xplanet-error.log').write_text('fixture log\n')
        for status, message in ((1, 'Renderer log changed during reading'), (2, 'Renderer log inspection failed (exit 2)')):
            self.write_script(self.scripts/'run-totalmarker',
                f'echo "$*" >> "$TRACE"; echo "fixture log detail"; echo "fixture warning" >&2; exit {status}\n')
            if self.trace.exists():
                self.trace.unlink()
            before = self.snapshot()
            code, output = self.terminal('9\n1\n', pause_key=b' ', after_pause='q')
            self.assertEqual(code, 0, output)
            self.assertIn(message, output)
            self.assertIn('fixture log detail', output)
            self.assertIn('fixture warning', output)
            self.assertEqual(output.count('Press any key to continue'), 1)
            self.assertEqual(self.calls(), ['log-view'])
            self.assertEqual(before, self.snapshot())

    def test_saved_support_routes_show_without_probe_confirmation(self):
        self.enhanced_terminal()
        self.write_script(self.scripts/'lib/xplanet/diagnostics.zsh',
            'renderer_diagnostics() { echo "diagnostics $*" >> "$TRACE"; print -- "fixture saved evidence"; return "$DIAGNOSTIC_RESULT"; }\n')
        for status, message in (('0', 'Saved renderer support displayed'), ('1', 'Saved renderer support is missing, stale or unknown'), ('2', 'Saved renderer support inspection failed (exit 2)')):
            self.env['DIAGNOSTIC_RESULT'] = status
            if self.trace.exists():
                self.trace.unlink()
            before = self.snapshot()
            code, output = self.terminal('9\n2\n', pause_key=b'x', after_pause='q')
            self.assertEqual(code, 0, output)
            self.assertIn('fixture saved evidence', output)
            self.assertIn(message, output)
            self.assertNotIn('Capture renderer support now?', output)
            self.assertEqual(output.count('Press any key to continue'), 1)
            self.assertEqual(self.calls(), ['diagnostics --show'])
            self.assertEqual(before, self.snapshot())

    def test_troubleshooting_and_log_pause_control_keys_restore_terminal(self):
        self.enhanced_terminal()
        self.real_log_view()
        for key, expected in ((b'\x04', 0), (b'\x03', 130)):
            code, output = self.terminal('9\n' + key.decode())
            self.assertEqual(code, expected, output)
            self.assertTrue(output.endswith('\x1b[?1049l'))
            self.assertEqual(self.calls(), [])
        for key, expected in ((b'\x04', 0), (b'\x03', 130)):
            if self.trace.exists():
                self.trace.unlink()
            code, output = self.terminal('9\n1\n', pause_key=key)
            self.assertEqual(code, expected, output)
            self.assertIn('2 repeat(s) hidden', output)
            self.assertEqual(output.count('Press any key to continue'), 1)
            self.assertTrue(output.endswith('\x1b[?1049l'))
            self.assertEqual(self.calls(), ['log-view'])

    def test_plain_submenu_back_and_confirmation_eof_exit_without_probe(self):
        before = self.snapshot()
        for keys in ('9\nb\nq\n', '9\n4\nq\n', '9\n3\n\x04'):
            code, output = self.terminal(keys)
            self.assertEqual(code, 0, output)
            self.assertEqual(self.calls(), [])
            self.assertEqual(before, self.snapshot())

    def test_help_routes_existing_usage_and_exposes_detailed_help_without_probe(self):
        for enhanced in (False,True):
            if enhanced:self.enhanced_terminal()
            before=self.snapshot();code,output=self.terminal('h\n',pause_key=b' ',after_pause='q\n')
            self.assertEqual(code,0,output);self.assertIn('Usage: scripts/xplanet.sh [COMMAND [OPTIONS]]',output)
            self.assertIn('diagnostics --help',output);self.assertIn('config --help',output);self.assertIn('config --guide',output)
            for heading in ('Explore and configure', 'Control the desktop', 'Refresh data (Python TotalMarker)', 'Inspect and troubleshoot'):
                self.assertIn(heading,output)
            self.assertIn('no probe, setup or service action was run',output)
            self.assertEqual(self.calls(),[]);self.assertEqual(before,self.snapshot())

    def test_help_pause_ctrl_d_and_ctrl_c_restore_terminal_without_actions(self):
        self.enhanced_terminal()
        for key,expected in ((b'\x04',0),(b'\x03',130)):
            code,output=self.terminal('h\n',pause_key=key)
            self.assertEqual(code,expected,output);self.assertEqual(output.count('\x1b[?1049h'),1)
            self.assertTrue(output.endswith('\x1b[?1049l'));self.assertEqual(self.calls(),[])

    def test_dashboard_spacing_groups_facts_without_hiding_short_terminal_status(self):
        self.enhanced_terminal()
        for rows, cols in ((40, 120), (30, 80), (24, 60)):
            with self.subTest(rows=rows, cols=cols):
                self.env.update(TEST_ROWS=str(rows), TEST_COLS=str(cols))
                code, output = self.terminal('q\n')
                self.assertEqual(code, 0, output)
                import re
                plain = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]|\x1b[78]', '', output).replace('\r', '')
                self.assertRegex(plain,r'\n\n +Saved data +')
                for label in ('Desktop', 'Next start', 'Running scene',
                              'Xplanet build', 'Custom setup', 'q) Exit'):
                    self.assertIn(label, plain)
                if rows >= 35:
                    self.assertRegex(plain,r'\n\n +Next start +')
                    self.assertRegex(plain,r'\n\n +Custom setup +')
                else:
                    self.assertNotRegex(plain,r'\n\n +Next start +')

    def test_missing_configurator_can_decline_preparation_without_writes(self):
        self.write_script(self.scripts/'run-configurator', 'exit 4\n')
        before = self.snapshot()
        code, output = self.terminal('2\nn\nq\n')
        self.assertEqual(code, 0, output)
        self.assertIn('Prepare the configurator now? [y/N]', output)
        self.assertNotIn('Press any key', output)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_explicit_preparation_runs_once_then_opens_configurator(self):
        self.write_script(self.scripts/'run-configurator',
            'case "$1" in --prepare) echo prepare >> "$TRACE"; touch "$TRACE.ready"; exit 0;; esac\n'
            '[ -f "$TRACE.ready" ] && exit 3\nexit 4\n')
        code, output = self.terminal('2\ny\nq\n')
        self.assertEqual(code, 0, output)
        self.assertEqual(self.calls(), ['prepare'])
        self.assertIn('downloads pinned packages from PyPI', output)
        self.assertIn('Configurator cancelled', output)

    def test_failed_preparation_is_visible_and_does_not_reopen(self):
        self.write_script(self.scripts/'run-configurator',
            'case "$1" in --prepare) echo prepare >> "$TRACE"; echo fixture-failure >&2; exit 2;; esac\nexit 4\n')
        code, output = self.terminal('2\ny\n', pause_key=b'x', after_pause='q\n')
        self.assertEqual(code, 0, output)
        self.assertEqual(self.calls(), ['prepare'])
        self.assertIn('fixture-failure', output)
        self.assertIn('Configurator exited 2', output)

    def test_existing_unready_environment_is_not_replaced_by_menu(self):
        runtime = self.root/'.state/configurator/venv'
        runtime.mkdir(parents=True)
        (runtime/'keep').write_bytes(b'user runtime')
        self.write_script(self.scripts/'run-configurator', 'exit 4\n')
        before = self.snapshot()
        code, output = self.terminal('2\n', pause_key=b'x', after_pause='q\n')
        self.assertEqual(code, 0, output)
        self.assertNotIn('Prepare the configurator now?', output)
        self.assertIn('preserve recovery drafts', output)
        self.assertEqual(before, self.snapshot())

    def test_initial_saved_health_runs_once_before_first_dashboard_and_not_navigation(self):
        self.enhanced_terminal()
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        before=self.snapshot()
        code,output=self.terminal('\x1b[B\x1b[Bq')
        self.assertEqual(code,0,output)
        self.assertEqual(self.calls(),['health --dashboard'])
        self.assertEqual(output.count('Xplanet management'),1)
        self.assertLess(output.index('Reading saved health'),output.index('Xplanet management'))
        self.assertIn('[?] Clouds',output)
        self.assertIn('saved evidence, not a live access check; 7 products',output)
        self.assertNotIn('7 refreshes',output)
        self.assertEqual(before,self.snapshot())

    def test_initial_failed_health_keeps_menu_usable_and_unknown(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        self.write_script(self.scripts/'run-totalmarker','echo fixture-error; exit 2\n')
        code,output=self.terminal('q\n')
        self.assertEqual(code,0,output)
        self.assertIn('Inspection failed; no verified snapshot',output)
        self.assertIn('Saved health inspection unavailable',output)
        self.assertNotIn('fixture-error',output)

    def test_initial_health_timeout_cleans_only_owned_worker_group(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        helper=self.scripts/'lib/xplanet/management-dashboard.zsh'
        original=helper.read_text();self.assertEqual(original.count('{1..50}'),1)
        helper.write_text(original.replace('{1..50}','{1..3}'))
        self.write_script(self.scripts/'run-totalmarker',
            'echo $$ > "$TRACE.worker"; sleep 20 & echo $! > "$TRACE.child"; wait\n')
        unrelated=subprocess.Popen(['/bin/sleep','20'])
        try:
            code,output=self.terminal('q\n')
            self.assertEqual(code,0,output)
            self.assertIn('Saved health timed out',output)
            self.assertIsNone(unrelated.poll())
            for suffix in ('.worker','.child'):
                pid=int(Path(str(self.trace)+suffix).read_text())
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    try:os.kill(pid,0)
                    except ProcessLookupError:break
                    select.select([],[],[],0.02)
                else:self.fail(f'Owned health process {pid} survived timeout')
        finally:
            unrelated.terminate();unrelated.wait(timeout=3)

    def test_horizontal_alignment_on_wide_dashboard_preserves_full_narrow_values(self):
        self.enhanced_terminal()
        self.env.update(TEST_ROWS='40',TEST_COLS='120')
        code,output=self.terminal('q')
        self.assertEqual(code,0,output)
        plain=re.sub(r'\x1b\[[0-9;?]*[A-Za-z]|\x1b[78]','',output).replace('\r','')
        for label in ('Desktop','Next start','Running scene','Xplanet build','Saved data','Custom setup'):
            line=next(line for line in plain.splitlines() if line.startswith('  '+label))
            self.assertEqual(line[2:17].rstrip(),label)
            self.assertEqual(line[17:19],'  ')
        self.env.update(TEST_ROWS='24',TEST_COLS='60')
        code,output=self.terminal('q\n')
        self.assertEqual(code,0,output)
        self.assertRegex(output,r'Running scene +\[\?\] Not identified')
        self.assertIn('Build features not checked; choose Troubleshooting (9)',output)

    def test_startup_ctrl_c_restores_screen_and_cleans_owned_health_group(self):
        self.enhanced_terminal()
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        self.write_script(self.scripts/'run-totalmarker',
            'echo $$ > "$TRACE.worker"; sleep 20 & echo $! > "$TRACE.child"; wait\n')
        code,output=self.terminal('',startup_interrupt=True)
        self.assertEqual(code,130,output)
        self.assertTrue(output.endswith('\x1b[?1049l'),output)
        for suffix in ('.worker','.child'):
            pid=int(Path(str(self.trace)+suffix).read_text())
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_non_tty_with_configuration_does_not_run_automatic_health(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        result=subprocess.run([str(self.entry)],env=self.env,input='',capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Usage:',result.stdout);self.assertEqual(self.calls(),[])

    def test_health_capture_budget_refuses_excess_output_without_hiding_menu(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        self.write_script(self.scripts/'run-totalmarker',
            '/usr/bin/yes excessive-health-output\n')
        code,output=self.terminal('q\n')
        self.assertEqual(code,0,output)
        self.assertIn('Inspection failed; no verified snapshot',output)
        self.assertLess(len(output),10000)

    def test_action_return_reuses_snapshot_and_new_entry_reassesses_once(self):
        (self.root/'config').mkdir();(self.root/'config/totalmarker.toml').write_text('')
        code,output=self.terminal('2\nq\n')
        self.assertEqual(code,0,output);self.assertEqual(self.calls(),['health --dashboard'])
        code,output=self.terminal('q\n')
        self.assertEqual(code,0,output);self.assertEqual(self.calls(),['health --dashboard','health --dashboard'])

    def test_ctrl_c_at_actual_action_confirmation_restores_terminal_without_start(self):
        self.enhanced_terminal()
        code,output=self.terminal('3\n',confirm_interrupt=True)
        self.assertIn('Run start? [y/N]',output)
        self.assertEqual(code,130,output);self.assertEqual(self.calls(),[])
        self.assertEqual(output.count('\x1b[?1049h'),1)
        self.assertEqual(output.count('\x1b[?1049l'),1)

    def test_actual_saved_health_cli_records_populate_shell_dashboard(self):
        config=self.root/'config';config.mkdir()
        (config/'totalmarker.toml').write_bytes((PROJECT/'config/totalmarker.example.toml').read_bytes())
        self.env['PYTHONPATH']=str(PROJECT/'scripts')
        self.env['PYTHONDONTWRITEBYTECODE']='1'
        self.write_script(self.scripts/'run-totalmarker',
                          'exec '+shlex.quote(sys.executable)+' -B -m totalmarker --root '+shlex.quote(str(self.root))+' "$@"\n')
        raw=subprocess.run([str(self.scripts/'run-totalmarker'),'health','--dashboard'],env=self.env,text=True,capture_output=True,timeout=5)
        self.assertIn(raw.returncode,(0,1),raw.stdout+raw.stderr)
        rows=raw.stdout.splitlines();self.assertTrue(rows[0].startswith('snapshot\t'))
        products=[line.split('\t') for line in rows[1:] if not line.startswith('note\t')]
        self.assertEqual(len(products),7)
        code,output=self.terminal('q\n')
        self.assertEqual(code,0,output)
        badges={'good':'[+]','warning':'[!]','error':'[x]','disabled':'[-]','unknown':'[?]'}
        for kind,title,*_ in products:
            with self.subTest(product=title):self.assertIn(badges[kind]+' '+title,output)
        self.assertNotIn('Inspection failed; no verified snapshot',output)
