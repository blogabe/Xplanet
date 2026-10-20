"""Offline checks for launcher delegation before other providers exist."""
import os
import shutil
import subprocess

from .support import PROJECT, Sandbox


PRODUCTS = ("clouds", "quake", "storm", "volcano")


class LauncherWiringTests(Sandbox):
    def setUp(self):
        super().setUp()
        scripts = self.root / "scripts"
        scripts.mkdir()
        self.launcher = scripts / "xplanet.sh"
        shutil.copy2(PROJECT / "scripts/xplanet.sh", self.launcher)
        runner = scripts / "run-totalmarker"
        runner.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$@" > "$TM_TEST_TRACE"\n'
            'exit "$TM_TEST_EXIT"\n')
        runner.chmod(0o755)
        setup = scripts / "xp-setup.sh"
        setup.write_text(
            '#!/bin/sh\n'
            ': > "$TM_SETUP_TRACE"\n'
            'for arg do printf "%s\\n" "$arg" >> "$TM_SETUP_TRACE"; done\n'
            'exit "$TM_SETUP_EXIT"\n')
        setup.chmod(0o755)

    def test_products_delegate_one_argument_and_preserve_exit_status(self):
        messages = {
            "clouds": "Fetching the live cloud image with Python TotalMarker.",
            "quake": "Fetching live USGS earthquake data with Python TotalMarker.",
            "storm": "Fetching worldwide storm positions and tracks with Python TotalMarker.",
            "volcano": "Fetching the live weekly volcano feed with Python TotalMarker.",
        }
        trace = self.base / "trace.txt"
        environment = {**os.environ, "TM_TEST_TRACE": str(trace),
                       "TM_TEST_EXIT": "37"}
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        for product in PRODUCTS:
            with self.subTest(product=product):
                trace.unlink(missing_ok=True)
                result = subprocess.run(
                    [str(self.launcher), product], cwd=self.base,
                    env=environment, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 37, result.stderr)
                self.assertEqual(trace.read_text(), product + "\n")
                self.assertEqual(result.stdout, messages[product] + "\n")
                self.assertEqual(
                    sorted(p.relative_to(self.root) for p in self.root.rglob("*")),
                    before)

    def test_setup_forwards_arguments_and_exit_status(self):
        trace = self.base / "setup-trace.txt"
        environment = {**os.environ, "TM_SETUP_TRACE": str(trace),
                       "TM_SETUP_EXIT": "37"}
        for command, options in (("setup", ()), ("setup", ("--dry-run",))):
            with self.subTest(command=command, options=options):
                trace.unlink(missing_ok=True)
                result = subprocess.run(
                    [str(self.launcher), command, *options], cwd=self.base,
                    env=environment, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 37, result.stderr)
                self.assertEqual(trace.read_text().splitlines(), list(options))

    def test_other_commands_still_reject_extra_arguments(self):
        result = subprocess.run(
            [str(self.launcher), "clouds", "--check"], cwd=self.base,
            text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected exactly one command", result.stderr)

    def test_regression_suite_delegates_to_totalmarker_launcher(self):
        trace = self.base / "test-trace.txt"
        result = subprocess.run([str(self.launcher), "test"], cwd=self.base,
                                env={**os.environ, "TM_TEST_TRACE": str(trace),
                                     "TM_TEST_EXIT": "37"},
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 37)
        self.assertEqual(trace.read_text(), "--test\n")

    def test_help_names_install_setup_and_lifecycle_commands(self):
        result = subprocess.run(
            [str(self.launcher), "--help"], cwd=self.base,
            text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        for product in (*PRODUCTS, "start", "stop", "setup", "install", "update",
                        "--dry-run", "--check"):
            self.assertIn(product, result.stdout)
