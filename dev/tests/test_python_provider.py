"""Provider commands run only against disposable package-manager stubs."""
import os
import pty
import select
import time
import plistlib
from pathlib import Path
import shutil
import subprocess
import sys

from .support import PROJECT, Sandbox


class PythonProviderTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.scripts = self.root / 'scripts'
        self.scripts.mkdir()
        shutil.copy2(PROJECT / 'scripts/run-totalmarker', self.scripts / 'run-totalmarker')
        self.brew_prefix = self.root / 'brew python'
        self.uv_prefix = self.root / 'brew uv'
        self.uv_python = self.root / 'managed python/bin/python3'
        for prefix in (self.brew_prefix, self.uv_prefix, self.uv_python.parent.parent):
            (prefix / 'bin').mkdir(parents=True)
        self.trace = self.root / 'calls'
        self.env = {**os.environ, 'PATH': f'{self.bin}:/usr/bin:/bin',
                    'TRACE': str(self.trace), 'BREW_PREFIX': str(self.brew_prefix),
                    'UV_PREFIX': str(self.uv_prefix), 'UV_PYTHON': str(self.uv_python),
                    'TEST_PYTHON': sys.executable}
        self.env.pop('TOTALMARKER_PYTHON', None)
        uv = '''#!/bin/sh
printf 'uv %s\\n' "$*" >> "$TRACE"
case " $* " in
 *' python find '*) printf '%s\\n' "$UV_PYTHON";;
 *' python install '*) [ "${FAIL_INSTALL:-0}" = 0 ] || exit 9
   [ -e "$UV_PYTHON" ] || ln -s "$TEST_PYTHON" "$UV_PYTHON";;
 *) exit 8;;
esac
'''
        self.template = self.root / 'uv-template'
        self.template.write_text(uv)
        self.template.chmod(0o755)
        self.env['UV_TEMPLATE'] = str(self.template)
        brew = self.bin / 'brew'
        brew.write_text('''#!/bin/sh
printf 'brew %s\\n' "$*" >> "$TRACE"
case "$1 $2" in
 '--prefix python') printf '%s\\n' "$BREW_PREFIX";;
 '--prefix uv') printf '%s\\n' "$UV_PREFIX";;
 'install python') [ "${FAIL_INSTALL:-0}" = 0 ] || exit 9
   [ -e "$BREW_PREFIX/bin/python3" ] || ln -s "$TEST_PYTHON" "$BREW_PREFIX/bin/python3";;
 'install uv') [ "${FAIL_INSTALL:-0}" = 0 ] || exit 9
   cp "$UV_TEMPLATE" "$UV_PREFIX/bin/uv";;
 *) exit 8;;
esac
''')
        brew.chmod(0o755)

    def invoke(self, action, provider="", answers="", flags=()):
        return subprocess.run(['/bin/zsh', '-c',
                               'script_dir=$1; project_root=${script_dir:h}; source "$2"; shift 2; "$@"', 'fixture',
                               str(self.scripts), str(PROJECT / 'scripts/lib/xplanet/python-runtime.zsh'),
                               action, provider, *flags], env=self.env, input=answers, capture_output=True, text=True,
                              timeout=5)

    def calls(self):
        return self.trace.read_text().splitlines() if self.trace.exists() else []

    def test_homebrew_choice_is_validated_and_does_not_fall_back_to_path(self):
        result = self.invoke('python_provider_find', 'homebrew')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        candidate = self.brew_prefix / 'bin/python3'
        candidate.symlink_to(sys.executable)
        result = self.invoke('python_provider_find', 'homebrew')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(candidate))
        self.assertFalse(any('install' in call for call in self.calls()))

    def test_uv_discovery_is_offline_without_projects_or_downloads(self):
        shutil.copy2(self.template, self.bin / 'uv')
        self.uv_python.symlink_to(sys.executable)
        result = self.invoke('python_provider_find', 'uv')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.uv_python))
        call = self.calls()[-1]
        for option in ('--no-config', '--offline', '--no-python-downloads',
                       '--managed-python', '--system', '--no-project', '>=3.11'):
            self.assertIn(option, call)
        self.assertNotIn('install', call)

    def test_explicit_uv_provision_uses_provider_commands_without_bin_links(self):
        result = self.invoke('python_provider_install', 'uv')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('brew install uv', self.calls())
        self.assertIn('uv --no-config python install --no-bin >=3.11', self.calls())
        self.assertFalse((self.bin / 'python3').exists())
        for forbidden in ('pip', 'venv', 'update-shell', 'uninstall', 'relink'):
            self.assertFalse(any(forbidden in call for call in self.calls()))

    def test_homebrew_install_and_failed_install_are_explicit(self):
        self.env['FAIL_INSTALL'] = '1'
        result = self.invoke('python_provider_install', 'homebrew')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertFalse((self.brew_prefix / 'bin/python3').exists())
        self.env['FAIL_INSTALL'] = '0'
        result = self.invoke('python_provider_install', 'homebrew')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertTrue(all(call.startswith('brew ') for call in self.calls()))

    def test_selection_switches_both_ways_and_invalid_candidate_preserves_prior_choice(self):
        config = self.root / 'config'
        config.mkdir()
        brew_python = self.brew_prefix / 'bin/python3'
        brew_python.symlink_to(sys.executable)
        self.uv_python.symlink_to(sys.executable)
        selection = config / 'totalmarker.python'
        for candidate in (brew_python, self.uv_python, brew_python):
            result = self.invoke('python_save_selection', str(candidate))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(selection.read_text(), str(candidate) + '\n')
            selected = subprocess.run([str(self.scripts / 'run-totalmarker'), '--python-path'],
                                      env=self.env, capture_output=True, text=True, timeout=3)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(selected.stdout.strip(), str(candidate))
        before = selection.read_bytes()
        self.assertNotEqual(self.invoke('python_save_selection', '/missing/python').returncode, 0)
        self.assertEqual(selection.read_bytes(), before)
        self.env['TOTALMARKER_PYTHON'] = sys.executable
        self.assertEqual(self.invoke('python_save_selection', str(self.uv_python)).returncode, 2)
        self.assertEqual(selection.read_bytes(), before)

    def test_explicit_project_choice_never_falls_back_and_environment_override_still_wins(self):
        config = self.root / 'config'
        config.mkdir()
        selection = config / 'totalmarker.python'
        selection.write_text('/missing/python\n')
        command = [str(self.scripts / 'run-totalmarker'), '--python-path']
        result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Selected TotalMarker Python', result.stderr)
        result = subprocess.run(command, env={**self.env, 'TOTALMARKER_PYTHON': sys.executable},
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), sys.executable)

    def test_interactive_choice_cancel_and_failed_provision_preserve_selection(self):
        config = self.root / 'config'
        config.mkdir()
        candidate = self.brew_prefix / 'bin/python3'
        candidate.symlink_to(sys.executable)
        selected = config / 'totalmarker.python'
        selected.write_text(str(candidate) + '\n')
        before = selected.read_bytes()
        for answers in ('q\n', '2\nn\n', '1\nn\n', ''):
            result = self.invoke('python_choose_runtime', answers=answers)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(selected.read_bytes(), before)
        self.env['FAIL_INSTALL'] = '1'
        result = self.invoke('python_choose_runtime', answers='2\ny\n')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(selected.read_bytes(), before)

    def test_interactive_switches_existing_providers_without_installing(self):
        candidate = self.brew_prefix / 'bin/python3'
        candidate.symlink_to(sys.executable)
        self.uv_python.symlink_to(sys.executable)
        shutil.copy2(self.template, self.bin / 'uv')
        for answers, expected in (('1\ny\n', candidate), ('2\ny\n', self.uv_python),
                                  ('1\ny\n', candidate)):
            result = self.invoke('python_choose_runtime', answers=answers)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.root / 'config/totalmarker.python').read_text(), str(expected) + '\n')
        self.assertFalse(any('install' in call for call in self.calls()))

    def test_failed_selection_cannot_overwrite_a_symlink(self):
        (self.root / 'config').mkdir()
        outside = self.root / 'other-selection'
        outside.write_text('untouched')
        (self.root / 'config/totalmarker.python').symlink_to(outside)
        result = self.invoke('python_save_selection', sys.executable)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_text(), 'untouched')

    def test_interactive_install_uses_same_selector_before_setup(self):
        setup = self.scripts / 'xp-setup.sh'
        setup.write_text('#!/bin/sh\nprintf "setup\\n" >> "$TRACE"\n')
        setup.chmod(0o755)
        renderer = self.brew_prefix / 'bin/xplanet'
        renderer.write_text('#!/bin/sh\nexit 0\n')
        renderer.chmod(0o755)
        brew = self.bin / 'brew'
        brew.write_text(brew.read_text().replace(" '--prefix uv')", " '--prefix blogabe/xplanet/xplanet') printf '%s\\n' \"$BREW_PREFIX\";;\n '--prefix uv')"))
        master, slave = pty.openpty()
        process = subprocess.Popen(['/bin/zsh', '-c',
            'script_dir=$1; project_root=${script_dir:h}; runtime_helper=$3; source "$2"; '
            'load_helpers() { source "$runtime_helper"; }; '
            'install_renderer() { print renderer >> "$TRACE"; }; install_xplanet',
            'fixture', str(self.scripts), str(PROJECT / 'scripts/lib/xplanet/install.zsh'),
            str(PROJECT / 'scripts/lib/xplanet/python-runtime.zsh')],
            stdin=slave, stdout=slave, stderr=slave, env=self.env)
        output = b''
        try:
            deadline = time.monotonic() + 5
            sent = False
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    output += os.read(master, 65536)
                if not sent and b'Python provider [1]:' in output:
                    os.write(master, b'1\ny\ny\nn\n')
                    sent = True
            self.assertEqual(process.poll(), 0, output.decode())
            self.assertIn('brew install python', self.calls())
            self.assertEqual(self.calls()[-1], 'setup')
            self.assertEqual((self.root / 'config/totalmarker.python').read_text(),
                             str(self.brew_prefix / 'bin/python3') + '\n')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            os.close(master)
            os.close(slave)

    def test_existing_pinned_job_warning_precedes_save_confirmation(self):
        candidate = self.brew_prefix / 'bin/python3'
        candidate.symlink_to(sys.executable)
        jobs = self.scripts / 'launchd'
        jobs.mkdir()
        job = jobs / 'local.xplanet.quake.plist'
        job.write_bytes(plistlib.dumps({'EnvironmentVariables': {'TOTALMARKER_PYTHON': '/older/python'}}))
        result = self.invoke('python_choose_runtime', answers='1\ny\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('still pins another interpreter: /older/python', result.stdout)
        self.assertIn('does not change that job', result.stdout)
        self.assertEqual(plistlib.loads(job.read_bytes())['EnvironmentVariables']['TOTALMARKER_PYTHON'], '/older/python')

    def test_advanced_change_requires_explicit_confirmation_and_cancel_preserves_choice(self):
        candidate = self.brew_prefix / 'bin/python3'
        candidate.symlink_to(sys.executable)
        self.assertEqual(self.invoke('python_save_selection', str(candidate)).returncode, 0)
        selected = self.root / 'config/totalmarker.python'
        before = selected.read_bytes()
        result = self.invoke('python_choose_runtime', 'change', answers='n\n')
        self.assertEqual(result.returncode, 3)
        self.assertNotIn('Python provider [1]', result.stdout)
        self.assertEqual(selected.read_bytes(), before)
        result = self.invoke('python_choose_runtime', 'change', answers='y\n1\ny\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any('install' in call for call in self.calls()))

    def test_initial_choice_can_keep_a_compatible_existing_interpreter(self):
        self.env['PATH'] = str(Path(sys.executable).parent) + ':' + self.env['PATH']
        result = self.invoke('python_choose_runtime', answers='k\ny\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        selected = self.root / 'config/totalmarker.python'
        self.assertTrue(Path(selected.read_text().strip()).is_absolute())
        self.assertFalse(any('install' in call for call in self.calls()))

    def test_setup_record_cannot_replace_an_existing_choice(self):
        self.assertEqual(self.invoke('python_save_selection', sys.executable).returncode, 0)
        selected = self.root / 'config/totalmarker.python'
        before = selected.read_bytes()
        result = self.invoke('python_save_selection', sys.executable, flags=('--if-missing',))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(selected.read_bytes(), before)
        self.assertEqual(list(selected.parent.glob('.totalmarker.python.*')), [])
