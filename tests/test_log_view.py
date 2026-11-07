"""Read-only text-log views use only disposable logs, never an installation."""
import io
import os
import subprocess
import sys
from unittest.mock import patch

from totalmarker import cli, log_view
from totalmarker.errors import StorageError
from .support import PROJECT, Sandbox


NIGHT = b"Warning: Resizing night map\n"
PAIR = NIGHT + log_view.ADVICE


class LogViewTests(Sandbox):
    def setUp(self):
        super().setUp()
        (self.root / "logs").mkdir()
        self.path = self.root / "logs/xplanet-error.log"

    def view(self, data):
        self.path.write_bytes(data)
        before = self.path.stat()
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(self.fs, "lock", side_effect=AssertionError("view locked")), \
             patch.object(self.fs, "write", side_effect=AssertionError("view wrote")):
            status = log_view.view(self.fs, "logs/xplanet-error.log", output, errors)
        self.assertEqual(self.path.read_bytes(), data)
        self.assertEqual(log_view._identity(self.path.stat()), log_view._identity(before))
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")),
                         ["logs", "logs/xplanet-error.log"])
        return status, output.getvalue(), errors.getvalue()

    def test_only_exact_pairs_collapse_and_distinct_errors_repeat_in_order(self):
        notice_pairs = [line + log_view.ADVICE for line in log_view.NOTICES]
        data = b"".join(notice_pairs) + b"Error: first\n" + b"".join(notice_pairs) + b"Error: first\nError: last\n"
        status, output, errors = self.view(data)
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        expected = (b"".join(notice_pairs) + b"Error: first\nError: first\nError: last\n").decode()
        self.assertTrue(output.startswith(expected), output)
        for kind in log_view.NOTICES.values():
            self.assertIn(f"  {kind}: 2 occurrence(s), 1 repeat(s) hidden", output)

    def test_single_notice_is_shown_and_counted_without_suppression(self):
        status, output, errors = self.view(PAIR)
        self.assertEqual(status, 0)
        self.assertTrue(output.startswith(PAIR.decode()))
        self.assertIn("night: 1 occurrence(s), 0 repeat(s) hidden", output)

    def test_incomplete_unknown_or_altered_notices_are_never_collapsed(self):
        cases = [NIGHT, NIGHT + log_view.ADVICE[:-1],
                 NIGHT + b"Different advice\n", log_view.ADVICE,
                 b"Warning: Resizing new map\n" + log_view.ADVICE,
                 b"prefix " + PAIR, PAIR.replace(b"\n", b"\r\n"),
                 NIGHT + b"\xff" + log_view.ADVICE,
                 b"Warning: Resizing night map \n" + log_view.ADVICE]
        for data in cases:
            with self.subTest(data=data):
                status, output, errors = self.view(data + data)
                self.assertEqual(status, 0)
                expected = io.StringIO()
                log_view._display(data + data, expected)
                self.assertEqual(output, expected.getvalue())
                self.assertNotIn("repeat(s) hidden", output)

    def test_adjacent_incomplete_header_does_not_hide_next_complete_notice(self):
        status, output, errors = self.view(NIGHT + PAIR + PAIR + NIGHT)
        self.assertEqual(output.count(NIGHT.decode()), 3)
        self.assertIn("night: 2 occurrence(s), 1 repeat(s) hidden", output)

    def test_invalid_utf8_controls_and_trailing_fragment_remain_visible(self):
        status, output, errors = self.view(PAIR + PAIR + b"Error: \xff\x00\x1b[2J\runfinished")
        self.assertIn(r"Error: \xff\x00\x1b[2J\x0dunfinished" + "\n", output)
        self.assertIn("night: 2 occurrence(s)", output)
        self.assertEqual(status, 0)

    def test_utf8_split_at_chunk_boundary_and_incomplete_final_bytes(self):
        data = b"x" * (log_view.CHUNK - 1) + "é warning\n".encode() + b"\xe2\x82"
        status, output, errors = self.view(data)
        self.assertEqual(output, "x" * (log_view.CHUNK - 1) + "é warning\n" + r"\xe2\x82")

    def test_empty_log_stays_empty(self):
        self.assertEqual(self.view(b""), (0, "", ""))

    def test_chunk_boundary_inside_long_line_is_not_a_notice_start(self):
        data = b"x" * log_view.CHUNK + PAIR + PAIR + PAIR
        status, output, errors = self.view(data)
        self.assertTrue(output.startswith((b"x" * log_view.CHUNK + PAIR + PAIR).decode()))
        self.assertIn("night: 2 occurrence(s), 1 repeat(s) hidden", output)

    def test_missing_directory_fifo_symlink_and_outside_path_fail_without_creation(self):
        with self.assertRaisesRegex(StorageError, "not found"):
            log_view.view(self.fs, "logs/missing", io.StringIO(), io.StringIO())
        self.path.mkdir()
        with self.assertRaisesRegex(StorageError, "regular file"):
            log_view.view(self.fs, "logs/xplanet-error.log", io.StringIO(), io.StringIO())
        self.path.rmdir()
        os.mkfifo(self.path)
        with self.assertRaisesRegex(StorageError, "regular file"):
            log_view.view(self.fs, "logs/xplanet-error.log", io.StringIO(), io.StringIO())
        self.path.unlink()
        target = self.root / "logs/target"
        target.write_bytes(PAIR)
        self.path.symlink_to(target)
        for path in ("logs/xplanet-error.log", "../outside", str(self.base / "outside")):
            with self.subTest(path=path), self.assertRaises(StorageError):
                log_view.view(self.fs, path, io.StringIO(), io.StringIO())
        self.assertEqual(target.read_bytes(), PAIR)

    def test_append_is_bounded_and_changed_read_reports_nonzero(self):
        self.path.write_bytes(PAIR)
        original_scan = log_view._scan
        def append_then_read(source, size, output):
            with self.path.open("ab") as writer:
                writer.write(b"Error: appended\n")
            return original_scan(source, size, output)
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(log_view, "_scan", append_then_read):
            status = log_view.view(self.fs, "logs/xplanet-error.log", output, errors)
        self.assertEqual(status, 1)
        self.assertNotIn("appended", output.getvalue())
        self.assertIn("Log changed", errors.getvalue())
        self.assertEqual(self.path.read_bytes(), PAIR + b"Error: appended\n")

    def test_replacement_truncation_removal_and_in_place_change_are_reported(self):
        original_scan = log_view._scan
        for action in ("replace", "truncate", "unlink", "edit"):
            self.path.write_bytes(PAIR)
            def change_then_read(source, size, output):
                if action == "replace":
                    replacement = self.root / "logs/replacement"
                    replacement.write_bytes(b"New warning\n")
                    replacement.replace(self.path)
                elif action == "unlink":
                    self.path.unlink()
                elif action == "truncate":
                    self.path.write_bytes(b"")
                else:
                    self.path.write_bytes(PAIR.replace(b"night", b"other"))
                return original_scan(source, size, output)
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(action=action), patch.object(log_view, "_scan", change_then_read):
                self.assertEqual(log_view.view(self.fs, "logs/xplanet-error.log", output, errors), 1)
                self.assertIn("Log changed", errors.getvalue())

    def test_cli_reads_default_and_custom_file_without_loading_config(self):
        self.path.write_bytes(PAIR * 2)
        for options in ([], ["--file", "logs/xplanet-error.log"]):
            output = io.StringIO()
            with patch.object(cli, "load", side_effect=AssertionError("config loaded")), \
                 patch.object(cli.sys, "stdout", output):
                self.assertEqual(cli.main(["--root", str(self.root), "log-view", *options]), 0)
            self.assertIn("night: 2 occurrence(s)", output.getvalue())
        self.assertFalse((self.root / ".state").exists())

    def test_cli_rejects_other_commands_options_and_reports_missing_file(self):
        for options in (["log-view", "--json"], ["log-view", "--dry-run"],
                        ["log-view", "--days", "2"], ["health", "--file", "logs/other"]):
            with self.subTest(options=options), patch.object(cli.sys, "stderr", io.StringIO()), \
                 self.assertRaises(SystemExit) as caught:
                cli.main(["--root", str(self.root), *options])
            self.assertEqual(caught.exception.code, 2)
        output = io.StringIO()
        with patch.object(cli.sys, "stdout", output):
            self.assertEqual(cli.main(["--root", str(self.root), "log-view"]), 2)
        self.assertIn("not found", output.getvalue())

    def test_public_runner_selects_explicit_root_without_config_or_runtime_writes(self):
        self.path.write_bytes(PAIR * 3 + b"Warning: distinct\n")
        result = subprocess.run([str(PROJECT / "scripts/run-totalmarker"), "--root", str(self.root), "log-view"],
            env={**os.environ, "TOTALMARKER_PYTHON": sys.executable},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("night: 3 occurrence(s), 2 repeat(s) hidden", result.stdout)
        self.assertIn("Warning: distinct", result.stdout)
        self.assertFalse((self.root / ".state").exists())
