"""Management uses disposable command stubs; never host installers or jobs."""
import os
import fcntl
import pty
import select
import signal
import subprocess
import time
import termios
import struct

from .support import Sandbox, copy_launcher


class ManagementTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.scripts = self.root / 'scripts'
        self.scripts.mkdir()
        self.entry = self.scripts / 'xplanet.sh'
        copy_launcher(self.entry)
        self.trace = self.base / 'calls'
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.env = {**os.environ, 'PATH': f'{self.bin}:/usr/bin:/bin',
                    'TRACE': str(self.trace), 'PYTHON_RESULT': '0', 'TERM': 'dumb'}
        # CI selects its test interpreter globally; each sandbox owns overrides.
        self.env.pop('TOTALMARKER_PYTHON', None)
        self.write_script(self.scripts / 'run-totalmarker',
                          'if [ "$1" = --python-path ]; then\n'
                          '  [ "$PYTHON_RESULT" = 0 ] || exit 2\n'
                          '  echo /fixture/python; exit 0; fi\n'
                          'echo "$*" >> "$TRACE"\n')
        self.write_script(self.scripts / 'xp-setup.sh', 'echo setup >> "$TRACE"\n')
        self.write_script(self.bin / 'xplanet', 'exit 0\n')
        self.env.update(PROCESS_RESULT='1', JOB_RESULT='0', JOB_TABLE='PID Status Label')
        self.write_script(self.bin / 'pgrep', 'exit "$PROCESS_RESULT"\n')
        self.write_script(self.bin / 'launchctl',
                          'printf "%s\\n" "$JOB_TABLE"\nexit "$JOB_RESULT"\n')
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

    def terminal(self, answers=None, interrupt=False, eof=False, termination=None, pause_signal=None, pause_key=None, after_pause=None, menu_steps=(), resize=None, delayed_input=None):
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
            while b'Choose: ' not in output and time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    output += os.read(master, 65536)
            self.assertIn(b'Choose: ', output)
            if self.env.get('TERM') == 'xterm-256color':
                while termios.tcgetattr(slave)[3] & termios.ICANON and time.monotonic() < deadline:
                    select.select([], [], [], .001)
            if resize:
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', *resize, 0, 0))
                os.kill(proc.pid, signal.SIGWINCH)
            if interrupt or termination:
                os.kill(proc.pid, termination or signal.SIGINT)
            else:
                os.write(master, b'\x04' if eof else answers.encode())
            pause_signalled = False
            next_choice_sent = False
            menu_steps = iter(menu_steps)
            next_step = next(menu_steps, None)
            input_ready_at = time.monotonic() + .15 if delayed_input else None
            while proc.poll() is None and time.monotonic() < deadline:
                if input_ready_at and time.monotonic() >= input_ready_at:
                    os.write(master, delayed_input)
                    input_ready_at = None
                if next_step and output.count(b'Choose: ') >= next_step[0]:
                    os.write(master, next_step[1])
                    next_step = next(menu_steps, None)
                if (pause_signal or pause_key) and not pause_signalled and b'Press any key to continue' in output and not (termios.tcgetattr(slave)[3] & (termios.ICANON | termios.ECHO)):
                    if pause_signal:
                        os.kill(proc.pid, pause_signal)
                    else:
                        os.write(master, pause_key)
                    pause_signalled = True
                if after_pause and pause_signalled and not next_choice_sent and output.count(b'Choose: ') >= 2:
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

    def test_config_stub_and_advanced_navigation_do_not_claim_saved_settings(self):
        before = self.snapshot()
        code, output = self.terminal('invalid\n2\n8\n q\n')
        self.assertEqual(code, 0)
        self.assertIn('not implemented yet. No settings were saved or applied.', output)
        self.assertIn('uv integration is deferred', output)
        self.assertIn('Homebrew Python is the recommended default', output)
        self.assertIn('Python runtime information', output)
        self.assertNotIn('Advanced Python options', output)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_direct_config_is_noninteractive_and_noop(self):
        before = self.snapshot()
        result = subprocess.run([str(self.entry), 'config'], env=self.env,
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertIn('No settings were saved or applied', result.stdout)
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
            self.assertIn(f'{expected} configuration', output)
            self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

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
        code, output = self.terminal('1\ny\nn\n ')
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
        self.assertEqual(self.calls(), ['health'])

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
                      '2) Configurator (placeholder)', 'q) Exit']:
            self.assertIn(label, lines)
        self.assertFalse(any('3) Start' in line and '4) Stop' in line for line in lines))
        self.assertIn('Stop ALL your Xplanet processes, including finite renders?', output)
        self.assertIn('Restart: stop ALL your Xplanet processes, then start one desktop?', output)
        self.assertEqual(self.calls(), [])

    def enhanced_terminal(self):
        self.env['TERM'] = 'xterm-256color'
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
            self.assertIn('Dashboard pending; saved health (7)', output)
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
        heading = output.index('\x1b[34mPython runtime\x1b[0m')
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
        for n in range(1, 101):
            self.assertIn(f'detail {n}\r\n', output)
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
        self.assertIn('[?] Dashboard pending', output)

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
        self.assertIn('Configurator pending; no settings saved or applied.', output)
        self.assertIn('Python: Homebrew recommended; uv deferred.', output)
        self.assertIn('Health needs configuration; choose Guided setup (1).', output)
        self.assertIn('Update has no remote-tracking upstream.', output)
        self.assertIn('Stop was not run.', output)
        last_screen = output.rsplit('\x1b[H\x1b[J', 1)[-1]
        self.assertIn('Last action: [+] Done - Start completed.', last_screen)
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
        self.assertEqual(self.calls(), ['setup'])

    def test_single_key_returns_without_enter_and_preserves_next_choice(self):
        self.enhanced_terminal()
        code, output = self.terminal('8\n 2\nq\n')
        self.assertEqual(code, 0)
        self.assertEqual(output.count('Press any key to continue'), 1)
        self.assertIn('Last action: [i] Unavailable - Configurator pending;', output)
        self.assertEqual(output.count('Xplanet management'), 3)
        self.assertNotIn('Choose a listed option', output)

    def test_pause_ignores_only_already_queued_newlines(self):
        self.enhanced_terminal()
        code, output = self.terminal('8\n\nx2\nq\n')
        self.assertEqual(code, 0)
        self.assertEqual(output.count('Press any key to continue'), 1)
        self.assertIn('Configurator pending;', output)
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
        self.assertIn('Configurator pending;', output)
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
        self.assertIn('> \x1b[34m8) Python runtime information', output)
        self.assertNotIn('Press any key to continue', output)
        self.assertEqual(self.calls(), [])
        code, output = self.terminal('2\nq')
        self.assertEqual(code, 0)
        self.assertIn('Configurator pending;', output)

    def test_arrow_navigation_repeats_and_stops_at_boundaries(self):
        self.enhanced_terminal()
        for keys, selected in [('\x1b[A' * 3 + 'q', 1),
                               ('\x1b[B' * 12 + 'q', 8),
                               ('\x1b[B\x1b[B\x1b[A\nq', 2),
                               ('\x1bOB\nq', 2)]:
            code, output = self.terminal(keys)
            self.assertEqual(code, 0)
            self.assertIn(f'> \x1b[34m{selected})', output)
            self.assertEqual('Configurator pending;' in output, selected == 2)
        self.assertEqual(self.calls(), [])

    def test_partial_and_malformed_escape_input_does_not_activate(self):
        self.enhanced_terminal()
        for keys in ('\x1b', '\x1b[', '\x1b[?x', '\x1b[1234567890123456789012345678901234567890~'):
            code, output = self.terminal(keys, delayed_input=b'q')
            self.assertEqual(code, 0, output)
            self.assertNotIn('Guided setup\x1b[0m\r\n', output)
            self.assertEqual(self.calls(), [])

    def test_acknowledgement_consumes_escape_sequence_and_keeps_next_choice(self):
        self.enhanced_terminal()
        for key in (b'x', b'\n', b'\x1b[A', b'\x1bOP', b'\x1b[15~'):
            code, output = self.terminal('8\n', pause_key=key, after_pause='2\nq')
            self.assertEqual(code, 0, output)
            self.assertIn('Configurator pending;', output)
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
        self.assertIn('\x1b7\x1b8\x1b[14A\r\x1b[K', output)
        self.assertIn('Configurator pending;', output)
        # Relative row offsets stay correct with a longer header/result above.
        self.assertIn('q) Exit\r\n\r\nUp/Down', output)
        first = output.split('Choose: ', 1)[0]
        rows = first.split('\r\n')
        for number, offset in enumerate((14, 13, 10, 9, 8, 5, 4, 3), 1):
            item = next(i for i, row in enumerate(rows) if f'{number}) ' in row)
            self.assertEqual(len(rows) - 1 - item, offset)

    def test_narrow_navigation_redraws_using_cached_status(self):
        self.enhanced_terminal()
        self.env.update(TEST_ROWS='20', TEST_COLS='40')
        probes = self.base / 'probes'
        self.env['PROBES'] = str(probes)
        self.write_script(self.bin / 'pgrep', 'echo process >> "$PROBES"; exit 1\n')
        self.write_script(self.bin / 'launchctl', 'echo jobs >> "$PROBES"; exit 0\n')
        code, output = self.terminal('8\x1b[Aq')
        self.assertEqual(code, 0)
        self.assertEqual(probes.read_text().splitlines(), ['process', 'jobs'])
        self.assertEqual(output.count('Xplanet management'), 3)
        self.assertNotIn('\x1b7', output)

    def test_resize_refreshes_screen_and_preserves_navigation_input(self):
        self.enhanced_terminal()
        for keys, selected in [('\x1b[B', 2), ('\x1b4', 4)]:
            code, output = self.terminal(keys, resize=(20, 40), menu_steps=[(2, b'q')])
            self.assertEqual(code, 0, output)
            self.assertGreaterEqual(output.count('Xplanet management'), 2)
            self.assertIn(f'> \x1b[34m{selected})', output)
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
