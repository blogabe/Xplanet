"""Offline checks for launcher delegation before other providers exist."""
import os
import pty
import select
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
            'if [ -n "$TM_TEST_OUTPUT" ]; then printf "%s\\n" "$TM_TEST_OUTPUT"; fi\n'
            'if [ -n "$TM_TEST_STDERR" ]; then printf "%s\\n" "$TM_TEST_STDERR" >&2; fi\n'
            'exit "$TM_TEST_EXIT"\n')
        runner.chmod(0o755)
        setup = scripts / "xp-setup.sh"
        setup.write_text(
            '#!/bin/sh\n'
            ': > "$TM_SETUP_TRACE"\n'
            'for arg do printf "%s\\n" "$arg" >> "$TM_SETUP_TRACE"; done\n'
            'exit "$TM_SETUP_EXIT"\n')
        setup.chmod(0o755)

    def test_products_delegate_json_and_errors_without_scheduled_banners(self):
        trace = self.base / "trace.txt"
        environment = {**os.environ, "TM_TEST_TRACE": str(trace),
                       "TM_TEST_EXIT": "37",
                       "TM_TEST_OUTPUT": '{"outcome":"failed"}',
                       "TM_TEST_STDERR": "provider diagnostic"}
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        for product in PRODUCTS:
            with self.subTest(product=product):
                trace.unlink(missing_ok=True)
                result = subprocess.run(
                    [str(self.launcher), product], cwd=self.base,
                    env=environment, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 37, result.stderr)
                self.assertEqual(trace.read_text(), product + "\n")
                self.assertEqual(result.stdout, '{"outcome":"failed"}\n')
                self.assertEqual(result.stderr, "provider diagnostic\n")
                self.assertEqual(
                    sorted(p.relative_to(self.root) for p in self.root.rglob("*")),
                    before)

    def test_interactive_product_has_banner_and_preserves_json(self):
        trace = self.base / "tty-trace.txt"
        environment = {**os.environ, "TM_TEST_TRACE": str(trace),
                       "TM_TEST_EXIT": "0",
                       "TM_TEST_OUTPUT": '{"outcome":"unchanged"}',
                       "TM_TEST_STDERR": ""}
        master, slave = pty.openpty()
        try:
            result = subprocess.run([str(self.launcher), "quake"],
                                    cwd=self.base, env=environment, stdout=slave,
                                    stderr=subprocess.PIPE, text=True, timeout=5)
            ready, _, _ = select.select([master], [], [], 1)
            output = os.read(master, 4096).decode() if ready else ""
        finally:
            os.close(slave)
            os.close(master)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fetching live USGS earthquake data", output)
        self.assertIn('{"outcome":"unchanged"}', output)
        self.assertEqual(trace.read_text(), "quake\n")

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
        for product in (*PRODUCTS, "start", "stop", "restart", "setup", "install", "update",
                        "--dry-run", "--check"):
            self.assertIn(product, result.stdout)
