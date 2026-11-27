"""Manual wallpaper cleanup fixtures never access the user's wallpaper stores."""

from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import pty
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from .support import PROJECT

HELPER = PROJECT / "scripts/lib/xplanet/wallpaper-cleanup.py"
SPEC = importlib.util.spec_from_file_location("wallpaper_cleanup", HELPER)
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


class WallpaperCleanupTests(unittest.TestCase):
    def setUp(self):
        sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(sandbox.cleanup)
        self.home = Path(sandbox.name).resolve()
        self.runtime = self.home / "tmp"
        self.runtime.mkdir()
        self.roots = {self.runtime}
        self.cache = self.home / cleanup.CACHE
        self.cache.mkdir(parents=True)
        self.png_cache = self.home / cleanup.PNG_CACHE
        self.png_cache.mkdir(parents=True)
        self.gallery = self.home / cleanup.GALLERY
        self.gallery.parent.mkdir(parents=True)
        self.index = self.home / cleanup.INDEX
        self.index.parent.mkdir(parents=True)
        self.now = time.time() + cleanup.MIN_AGE + 100
        self.old = self.runtime / "Xplanet.a1B2c3.png"
        self.current = self.runtime / "Xplanet.d4E5f6" / "wallpaper.png"
        self.other = self.runtime / "Family.png"
        self.write_gallery(self.old, self.current, self.other)
        self.write_index(self.current)

    def write_gallery(self, *paths, copies=None):
        rows = []
        for path in paths:
            row = {"originalURL": {"relative": path.as_uri()}}
            if copies and path in copies:
                row["copyURL"] = {"relative": copies[path].as_uri()}
            rows.append(plistlib.dumps(row, fmt=plistlib.FMT_BINARY))
        self.gallery.write_bytes(plistlib.dumps({"ChoiceRequests.ImageFiles": rows}))

    def write_index(self, *paths):
        choices = [{
            "Provider": cleanup.IMAGE_PROVIDER,
            "Files": [],
            "Configuration": plistlib.dumps({
                "type": "imageFile", "url": {"relative": path.as_uri()},
            }, fmt=plistlib.FMT_BINARY),
        } for path in paths]
        self.index.write_bytes(plistlib.dumps({
            "SystemDefault": {}, "Displays": {},
            "Spaces": {"one": {"Displays": {"external": {"Choices": choices}}}},
        }))

    def bmp_path(self, source, suffix="41c85ca257b9ef44"):
        name = f"{cleanup.digest(os.fsencode(source))}-3840-2400-0-{suffix}.bmp"
        return self.cache / name

    def bmp(self, source):
        path = self.bmp_path(source)
        path.write_bytes(b"bmp fixture")
        return path

    def inventory(self):
        return cleanup.inventory(self.home, self.roots, self.now)

    def test_only_recognized_old_unreferenced_bitmap_removed(self):
        old = self.bmp(self.old)
        held = self.bmp(self.current)
        other = self.bmp(self.other)
        missing = self.bmp(self.runtime / "Xplanet.654321.png")
        cached_png = self.cache / "retained.png"
        cached_png.write_bytes(b"not a bitmap")
        link = self.bmp_path(self.old, "41c85ca257b9ef45")
        link.symlink_to(other)
        self.assertEqual([row[1] for row in self.inventory()["candidates"]], [old.name])
        plan = self.inventory()
        with patch.object(cleanup.time, "time", return_value=self.now):
            cleanup.apply(self.home, self.roots, plan)
        self.assertFalse(old.exists())
        for preserved in (held, other, missing, cached_png, link, self.index, self.gallery):
            self.assertTrue(preserved.exists())

    def test_changed_live_reference_is_preserved_without_cancelling_unrelated_cleanup(self):
        old = self.bmp(self.old)
        second = self.runtime / "Xplanet.112233.png"
        second_bmp = self.bmp(second)
        self.write_gallery(self.old, self.current, second)
        plan = self.inventory()
        self.write_index(self.current, self.old)
        with patch.object(cleanup.time, "time", return_value=self.now):
            cleanup.apply(self.home, self.roots, plan)
        self.assertTrue(old.exists())
        self.assertFalse(second_bmp.exists())

    def test_unrelated_new_gallery_row_and_newly_old_file_are_not_approved(self):
        old = self.bmp(self.old)
        plan = self.inventory()
        second = self.runtime / "Xplanet.112233.png"
        second_bmp = self.bmp(second)
        self.write_gallery(self.old, self.current, second)
        with patch.object(cleanup.time, "time", return_value=self.now):
            cleanup.apply(self.home, self.roots, plan)
        self.assertFalse(old.exists())
        self.assertTrue(second_bmp.exists())

    def test_file_replaced_since_preview_is_not_deleted(self):
        old = self.bmp(self.old)
        plan = self.inventory()
        old.unlink()
        old.write_bytes(b"different file")
        with patch.object(cleanup.time, "time", return_value=self.now):
            cleanup.apply(self.home, self.roots, plan)
        self.assertEqual(old.read_bytes(), b"different file")

    def test_scene_root_is_scoped_to_this_checkout_and_rejects_links(self):
        project = self.home / "checkout"
        (project / "scripts").mkdir(parents=True)
        (project / "scripts/xplanet.sh").touch()
        root = project / ".state/xplanet/desktop-tmp"
        self.assertEqual(cleanup.scene_stage_root(project), root)
        root.mkdir(parents=True)
        scene = root / "Xplanet.A1B2C3" / "wallpaper.png"
        self.write_gallery(self.old, self.current, scene)
        old = self.bmp(scene)
        self.assertEqual(self.inventory()["candidates"], [])
        self.roots.add(cleanup.scene_stage_root(project))
        self.assertEqual([record[1] for record in self.inventory()["candidates"]], [old.name])
        root.rmdir()
        root.symlink_to(self.runtime)
        self.assertIsNone(cleanup.scene_stage_root(project))

    def test_unknown_provider_fails_closed(self):
        self.bmp(self.old)
        self.index.write_bytes(plistlib.dumps({
            "SystemDefault": {"Choices": [{"Provider": "unknown", "Files": []}]},
            "Displays": {}, "Spaces": {},
        }))
        with self.assertRaisesRegex(ValueError, "unrecognized live wallpaper provider"):
            self.inventory()

    def test_new_or_staged_files_are_not_candidates(self):
        old = self.bmp(self.old)
        self.assertEqual(cleanup.inventory(self.home, self.roots, time.time())["candidates"], [])
        self.old.touch()
        self.assertEqual(self.inventory()["candidates"], [])
        self.assertTrue(old.exists())

    def test_png_uses_explicit_copy_url_and_skips_shared_or_live_copies(self):
        old = self.png_cache / "12345678-1234-4321-1234-0123456789AB.png"
        held = self.png_cache / "12345678-1234-4321-1234-0123456789AC.png"
        stray = self.png_cache / "12345678-1234-4321-1234-0123456789AD.png"
        for file in (old, held, stray):
            file.write_bytes(b"png fixture")
        self.write_gallery(self.old, self.current, self.other,
                           copies={self.old: old, self.other: old, self.current: held})
        self.assertEqual(self.inventory()["candidates"], [])
        self.write_gallery(self.old, self.current, self.other,
                           copies={self.old: old, self.current: held})
        plan = self.inventory()
        self.assertEqual([row[:2] for row in plan["candidates"]], [["PNG", old.name]])
        with patch.object(cleanup.time, "time", return_value=self.now):
            cleanup.apply(self.home, self.roots, plan)
        self.assertFalse(old.exists())
        self.assertTrue(held.exists())
        self.assertTrue(stray.exists())

    def test_health_reports_other_stores_when_one_is_missing(self):
        self.bmp(self.old)
        self.png_cache.rmdir()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(cleanup.wallpaper_health(self.home), 0)
        self.assertIn("Your Photos: 3 custom", output.getvalue())
        self.assertIn("PNG cache: unavailable", output.getvalue())
        self.assertIn("BMP cache: 1 file(s)", output.getvalue())

    def test_double_separator_uses_raw_hash_and_canonical_active_path(self):
        raw = self.runtime.as_uri() + "//" + self.old.name
        row = plistlib.dumps({"originalURL": {"relative": raw}}, fmt=plistlib.FMT_BINARY)
        self.gallery.write_bytes(plistlib.dumps({"ChoiceRequests.ImageFiles": [row]}))
        old = self.bmp(cleanup.path_value(raw))
        self.assertEqual([record[1] for record in self.inventory()["candidates"]], [old.name])
        self.write_index(self.old)
        self.assertEqual(self.inventory()["candidates"], [])

    def test_path_traversal_and_remote_urls_are_rejected(self):
        for value in ("file://remote/root/test", "file:///tmp/%2e%2e/test", "//tmp/test", "/tmp/./test", "/tmp/test/"):
            self.assertIsNone(cleanup.path_value(value))


class WallpaperCleanupLauncherTests(unittest.TestCase):
    def test_help_and_noninteractive_rejection(self):
        cli = PROJECT / "scripts/xplanet.sh"
        cases = ((["cleanup", "--help"], 0, "cache"),
                 (["restart", "--cleanup"], 2, "requires terminal"),
                 (["restart", "--dry-run"], 2, "accepts only --cleanup"))
        for args, status, expected in cases:
            with self.subTest(args=args):
                result = subprocess.run([str(cli), *args], stdin=subprocess.DEVNULL,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertIn(expected, (result.stdout + result.stderr).lower())

    def test_stop_failure_prevents_cleanup_and_start(self):
        script = """
script_dir=$PWD/scripts
source scripts/lib/xplanet/display.zsh || exit
desktop_command() { return 0; }
desktop_agent_preflight() { return 0; }
launchctl() { return 1; }
_stop_xplanet() { print stop; return 27; }
_start_xplanet() { print unexpected-start; }
wallpaper_cleanup_python() { print unexpected-cleanup; }
desktop_domain=gui/test
desktop_label=test
_restart_xplanet sample
"""
        result = subprocess.run(["/bin/zsh", "-fc", script], cwd=PROJECT,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 27, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["stop"])

    def test_restart_attempts_start_after_cleanup_failure(self):
        script = """
script_dir=$PWD/scripts
source scripts/lib/xplanet/display.zsh || exit
desktop_command() { return 0; }
desktop_agent_preflight() { return 0; }
launchctl() { return 1; }
_stop_xplanet() { print stop; return 0; }
_start_xplanet() { print start; return 0; }
wallpaper_cleanup_python() { print cleanup; return 1; }
desktop_domain=gui/test
desktop_label=test
_restart_xplanet sample
"""
        result = subprocess.run(["/bin/zsh", "-fc", script], cwd=PROJECT,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["stop", "cleanup", "start"])
        self.assertIn("display restarted", result.stderr)

    def test_cancel_before_any_lifecycle_action(self):
        script = """
source scripts/lib/xplanet/wallpaper-cleanup.zsh
wallpaper_cleanup_python() { print preview; return 4; }
_restart_xplanet() { print unexpected-restart; }
wallpaper_cleanup_transaction restart
"""
        master, slave = pty.openpty()
        try:
            result = subprocess.run(["/bin/zsh", "-fc", script], cwd=PROJECT,
                                    stdin=slave, stderr=slave, stdout=subprocess.PIPE,
                                    text=True, timeout=5)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["preview"])
