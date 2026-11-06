"""The public entry separates standalone/bootstrap/data and macOS workflows."""
import os
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

    def test_hostile_owned_zshenv_options_are_reset_before_workflow_helpers(self):
        startup=self.base/'owned-zdot';startup.mkdir()
        observed=self.base/'shell-options';observed.write_text('existing private bytes')
        (startup/'.zshenv').write_text('print -r -- loaded >> "$ZDOTDIR/loaded"\nsetopt NOCLOBBER SH_WORD_SPLIT GLOB_SUBST\n')
        (self.scripts/'lib/xplanet/display.zsh').write_text(
            'print -r -- "$options[noclobber]:$options[shwordsplit]:$options[globsubst]" > "$OBSERVED"\n'
            'start_xplanet() { print -r -- fixture-start; }\n')
        result=subprocess.run([str(self.entry),'start'],cwd=self.base,
                              env={**os.environ,'HOME':str(self.base),'ZDOTDIR':str(startup),'OBSERVED':str(observed)},
                              capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((startup/'loaded').read_text(),'loaded\n')
        self.assertEqual(observed.read_text(),'off:off:off\n')
        self.assertEqual(result.stdout,'fixture-start\n')
