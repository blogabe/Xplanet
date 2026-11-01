"""The normal shell entry point delegates health options and exit status."""
import os
import shutil
import subprocess

from .support import PROJECT, Sandbox


class HealthLauncherTests(Sandbox):
    def test_health_options_json_and_exit_status_are_forwarded(self):
        scripts = self.root / 'scripts'
        scripts.mkdir()
        launcher = scripts / 'xplanet.sh'
        shutil.copy2(PROJECT / 'scripts/xplanet.sh', launcher)
        runner = scripts / 'run-totalmarker'
        trace = self.base / 'arguments'
        runner.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$HEALTH_TRACE"\n'
                          'printf \'{"mode":"live"}\\n\'\nexit 1\n')
        runner.chmod(0o755)
        for args in [('health',), ('health', '--live', '--json')]:
            result = subprocess.run([str(launcher), *args], cwd=self.base,
                                    env={**os.environ, 'HEALTH_TRACE': str(trace)},
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(trace.read_text().splitlines(), list(args))
            self.assertEqual(result.stdout, '{"mode":"live"}\n')
        help_result = subprocess.run([str(launcher), '--help'], cwd=self.base,
                                     text=True, capture_output=True, timeout=5)
        self.assertIn('health', help_result.stdout)
        self.assertIn('--live', help_result.stdout)

    def test_health_options_stay_invalid_for_refresh_commands(self):
        result = subprocess.run([str(PROJECT / 'scripts/xplanet.sh'), 'volcano', '--live'],
                                cwd=self.base, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
