from pathlib import Path
import os
from unittest.mock import patch

from totalmarker.errors import ImageError, StorageError
from totalmarker.image import validate_jpeg
from totalmarker.labels import (color_for, legacy_time, render_cloud, render_quake,
                                cloud_timestamp)
from .support import Sandbox, jpeg


class LabelTests(Sandbox):
    def test_new_product_skips_occupied_row_without_moving_existing_rows(self):
        old = ('-53 -12 "Cloud Map Last Updated UNKNOWN" color=Green\n'
               '-83 -13 "Storm Infomation Last Updated UNKNOWN" color=Green\n')
        result = render_quake(old, 100, 100, 21600,
                              ("Green", "Yellow", "Red"))
        self.assertTrue(result.startswith(old))
        self.assertIn('-98 -13 "Earthquake Infomation Last Updated ', result)
        self.assertEqual(result.count('-83 -13 "'), 1)

    def test_strict_aging_boundaries_and_future_clock(self):
        colors = ("Green", "Yellow", "Red")
        for age, expected in [(0, "Green"), (21600, "Green"), (21601, "Yellow"),
                              (43200, "Yellow"), (43201, "Red"), (-100, "Red")]:
            self.assertEqual(color_for(100000, 100000 + age, 21600, colors), expected)
        self.assertEqual(color_for(None, 100000, 21600, colors), "Red")

    def test_local_time_uses_legacy_names(self):
        import time
        stamp = time.struct_time((2020, 6, 23, 18, 50, 1, 1, 175, -1))
        with patch("totalmarker.labels.time.localtime", return_value=stamp):
            self.assertEqual(legacy_time(0), "Tues 23 June 2020,18:50:01")

    def test_existing_rows_coordinates_options_and_order(self):
        timestamp = 100000
        other = ('# unchanged comment\n'
                 '-53 -13 "Earthquake Infomation Last Updated Mon 1 Jan 2020,00:00:00" '
                 'color=Red image=none position=pixel\n')
        cloud = f'-83 -12 "Cloud Map Last Updated {legacy_time(timestamp)}" color=Green image=none position=pixel\n'
        tail = '-98 -13 "Volcano Infomation Last Updated Mon 1 Jan 2020,00:00:00" color=Yellow image=none position=pixel\n'
        result = render_cloud(other + cloud + tail, timestamp, timestamp + 21601,
                              21600, ("Green", "Yellow", "Red"))
        self.assertTrue(result.startswith(other))
        self.assertTrue(result.endswith(tail))
        self.assertIn('-83 -12 "Cloud Map Last Updated', result)
        self.assertIn('color=Yellow image=none position=pixel', result)
        self.assertEqual(cloud_timestamp(result), timestamp)

    def test_new_cloud_offset_and_row_count(self):
        other = '# header\n-53 -13 "Earthquake Infomation Last Updated UNKNOWN" color=Red\n'
        text = render_cloud(other, None, 100, 21600, ("Green", "Yellow", "Red"))
        self.assertIn('-68 -12 "Cloud Map Last Updated UNKNOWN" color=Red', text)
        self.assertTrue(text.startswith(other))
        self.assertEqual(render_cloud(other, None, 100, 10, ("Green", "Yellow", "Red"),
                                      append=False), other)


class ImageAndPathTests(Sandbox):
    def test_real_minimal_jpeg_and_variant(self):
        for body in [jpeg(), jpeg(b"second edition")]:
            info = validate_jpeg(body)
            self.assertEqual((info.width, info.height), (2, 1))
        with self.assertRaises(ImageError):
            validate_jpeg(jpeg(), expected_width=4096)

    def test_invalid_and_truncated_data(self):
        for body in [b"<html>HTTP error</html>", jpeg()[:-2], jpeg()[:30],
                     b"\xff\xd8\xff\xd9", jpeg() + b"trailing"]:
            with self.assertRaises(ImageError):
                validate_jpeg(body)

    def test_internal_file_and_parent_links_survive(self):
        target = self.root / "images" / "data" / "current.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"before")
        alias = self.root / "images" / "current.jpg"
        alias.symlink_to("data/current.jpg")
        self.fs.write("images/current.jpg", b"after")
        self.assertTrue(alias.is_symlink())
        self.assertEqual(target.read_bytes(), b"after")
        parent_alias = self.root / "images" / "current"
        parent_alias.symlink_to("data", target_is_directory=True)
        self.fs.write("images/current/new.jpg", b"new")
        self.assertTrue(parent_alias.is_symlink())
        self.assertEqual((target.parent / "new.jpg").read_bytes(), b"new")

    def test_outside_target_and_parent_are_rejected_without_touching(self):
        # Outside this RootFS sandbox, still inside the approved project's test tree.
        outside = self.base / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_bytes(b"untouched fixture")
        (self.root / "escape").symlink_to(outside, target_is_directory=True)
        (self.root / "file-link").symlink_to(sentinel)
        for path in ["escape/new.jpg", "file-link"]:
            with self.assertRaises(StorageError):
                self.fs.write(path, b"must not escape")
            with self.assertRaises(StorageError):
                self.fs.read(path)
        self.assertEqual(sentinel.read_bytes(), b"untouched fixture")
        self.assertFalse((outside / "new.jpg").exists())

    def test_symlink_loop_and_protected_reference(self):
        (self.root / "loop").symlink_to("loop")
        with self.assertRaises(StorageError):
            self.fs.read("loop")
        with self.assertRaises(StorageError):
            self.fs.write("reference/original.pl", b"forbidden")
        self.assertFalse((self.root / "reference").exists())

    def test_runtime_inputs_and_internal_aliases_are_read_only(self):
        for directory in ("config", "scripts", "assets/maps"):
            source = self.root / directory / "source"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"preserve input")
            with self.subTest(directory=directory):
                with self.assertRaises(StorageError):
                    self.fs.write(f"{directory}/new", b"forbidden")
                with self.assertRaises(StorageError):
                    self.fs.append(f"{directory}/source", b"forbidden")
                with self.assertRaises(StorageError):
                    self.fs.unlink(f"{directory}/source")
                with self.assertRaises(StorageError):
                    with self.fs.lock(f"{directory}/job.lock"):
                        pass
                self.assertEqual(source.read_bytes(), b"preserve input")
                self.assertFalse((self.root / directory / "new").exists())
        (self.root / "images").mkdir()
        (self.root / "markers").mkdir()
        map_link = self.root / "images" / "earth.jpg"
        city_link = self.root / "markers" / "earth"
        map_link.symlink_to("../assets/maps/source")
        city_link.symlink_to("../config/source")
        for alias in ("images/earth.jpg", "markers/earth"):
            with self.subTest(alias=alias), self.assertRaises(StorageError):
                self.fs.write(alias, b"forbidden")
        self.assertEqual((self.root / "assets/maps/source").read_bytes(), b"preserve input")
        self.assertEqual((self.root / "config/source").read_bytes(), b"preserve input")
        self.assertEqual(map_link.readlink(), Path("../assets/maps/source"))
        self.assertEqual(city_link.readlink(), Path("../config/source"))

    def test_case_aliases_and_unapproved_output_areas_are_rejected(self):
        # Fixture paths only: never call the writer on the real project inputs.
        for directory, name in (("config", "earth"), (".git", "config")):
            protected = self.root / directory / name
            protected.parent.mkdir()
            protected.write_bytes(b"preserve protected fixture")
            alias = directory.upper() + "/" + name
            with self.subTest(alias=alias), self.assertRaises(StorageError):
                self.fs.resolve(alias, write=True)
            self.assertEqual(protected.read_bytes(), b"preserve protected fixture")
        (self.root / "images").mkdir()
        (self.root / "config" / "output-alias").symlink_to("../images/cloud.jpg")
        with self.assertRaises(StorageError):
            self.fs.resolve("config/output-alias", write=True)
        for path in ("runtime/job.lock", "scratch/data", "logs/other/events.jsonl",
                     ".state/other/state.json", "images", "README.md"):
            with self.subTest(path=path), self.assertRaises(StorageError):
                self.fs.resolve(path, write=True)
        for path in ("images/clouds.jpg", "markers/storm", "arcs/storm",
                     "logs/totalmarker/events.jsonl", ".state/totalmarker/job.lock"):
            with self.subTest(path=path):
                self.assertEqual(self.fs.resolve(path, write=True), self.root / path)

    def test_case_variant_runtime_outputs_cannot_collide(self):
        from totalmarker.config import load
        from totalmarker.errors import ConfigError
        with self.assertRaisesRegex(ConfigError, "distinct"):
            self.config("LabelOutput=markers/QUAKE\n")
        (self.root / "images").mkdir()
        (self.root / "images" / "config.ini").write_text(
            "CloudOutput=images/CONFIG.ini\n")
        with self.assertRaisesRegex(ConfigError, "configuration file"):
            load(self.fs, "images/config.ini")

    def test_lock_visibility_retry_is_bounded_and_safe(self):
        original = os.open
        simulated = False
        def delayed(path, flags, *args, **kwargs):
            nonlocal simulated
            if path == "race.lock" and flags & os.O_CREAT and not simulated:
                simulated = True
                raise FileNotFoundError(2, "Simulated file-provider visibility race")
            return original(path, flags, *args, **kwargs)
        with patch("os.open", side_effect=delayed):
            with self.fs.lock(".state/totalmarker/race.lock"):
                self.assertTrue(simulated)

    def test_separate_process_cannot_bypass_lock(self):
        import subprocess
        import sys
        from .support import PROJECT
        code = """from totalmarker.paths import RootFS
from totalmarker.errors import StorageError
import sys
try:
    with RootFS(sys.argv[1]).lock('.state/totalmarker/process.lock', timeout=0.1):
        print('incorrectly acquired')
except StorageError:
    print('blocked')
"""
        with self.fs.lock(".state/totalmarker/process.lock"):
            child = subprocess.run([sys.executable, "-B", "-c", code, str(self.root)],
                                   cwd=PROJECT, env={**os.environ, "PYTHONPATH": str(PROJECT / "scripts"), "PYTHONDONTWRITEBYTECODE": "1"},
                                   text=True, capture_output=True, timeout=5)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(child.stdout.strip(), "blocked")

    def test_invalid_legacy_calendar_date_is_not_imported(self):
        text = '-53 -12 "Cloud Map Last Updated Tues 31 Feb 2020,18:50:01" color=Green\n'
        self.assertIsNone(cloud_timestamp(text))

    def test_project_entrypoint_and_docs_cannot_be_output_targets(self):
        for name in ["README.md", ".gitignore"]:
            with self.assertRaises(StorageError):
                self.fs.write(name, b"must not overwrite project work")
