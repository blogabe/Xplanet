"""The public entry separates standalone/bootstrap/data and macOS workflows."""
import subprocess

from .support import Sandbox, copy_launcher


class ShellBoundaryTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.entry = self.scripts / "xplanet.sh"
        copy_launcher(self.entry)

    def invoke(self, *args):
        return subprocess.run([str(self.entry), *args], cwd=self.base,
                              capture_output=True, text=True, timeout=5)

    def test_help_and_data_commands_do_not_load_mac_workflows(self):
        # Missing internal platform helpers cannot disable diagnostics/data CLI.
        (self.scripts / "lib").rename(self.base / "unused-helpers")
        result = self.invoke("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        runner = self.scripts / "run-totalmarker"
        runner.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 37\n')
        runner.chmod(0o755)
        for args in (("quake",), ("health", "--json")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 37, result.stderr)
                self.assertEqual(result.stdout.splitlines(), list(args))

    def test_missing_platform_helper_fails_before_workflow_side_effects(self):
        (self.scripts / "lib/xplanet/display.zsh").unlink()
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        result = self.invoke("start")
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing display helpers", result.stderr)
        self.assertEqual(before, sorted(p.relative_to(self.root) for p in self.root.rglob("*")))
