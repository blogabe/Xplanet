"""The normal shell entry point delegates health options and exit status."""
import subprocess

from .support import copy_launcher, Sandbox


class HealthLauncherTests(Sandbox):
    def setUp(self):
        super().setUp()
        scripts = self.root / 'scripts'
        scripts.mkdir()
        self.launcher = scripts / 'xplanet.sh'
        copy_launcher(self.launcher)
        self.trace = self.base / 'arguments'
        self.environment = {'PATH': '/usr/bin:/bin', 'HOME': str(self.base),
                            'PYTHONDONTWRITEBYTECODE': '1',
                            'HEALTH_TRACE': str(self.trace)}
        runner = scripts / 'run-totalmarker'
        runner.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$HEALTH_TRACE"\n'
                          'printf \'{"mode":"live"}\\n\'\nexit 1\n')
        runner.chmod(0o755)

    def test_health_options_json_and_exit_status_are_forwarded(self):
        for args in [('health',), ('health', '--live', '--json'),
                     ('health', '--verbose'), ('health', '--live', '--verbose')]:
            result = subprocess.run([str(self.launcher), *args], cwd=self.base,
                                    env=self.environment,
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(self.trace.read_text().splitlines(), list(args))
            self.assertEqual(result.stdout, '{"mode":"live"}\n')
        help_result = subprocess.run([str(self.launcher), '--help'], cwd=self.base,
                                     env=self.environment, text=True, capture_output=True, timeout=5)
        self.assertIn('health', help_result.stdout)
        self.assertIn('--live', help_result.stdout)

    def test_health_options_stay_invalid_for_refresh_commands(self):
        for option in ('--live', '--verbose'):
            result = subprocess.run([str(self.launcher), 'volcano', option],
                                    cwd=self.base, env=self.environment, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(self.trace.exists(), "invalid refresh option must not invoke the runner")
