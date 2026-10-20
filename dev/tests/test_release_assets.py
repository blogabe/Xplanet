"""Offline checks for the candidate asset boundary and byte copying."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .support import PROJECT


SPEC = importlib.util.spec_from_file_location(
    "build_candidate", PROJECT / "dev/release/build_candidate.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseAssetsTests(unittest.TestCase):
    def test_regular_bytes_export_without_following_links_or_private_clutter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = root / "assets/maps"
            assets.mkdir(parents=True)
            original = assets / "earth.png"
            original.write_bytes(b"\x89PNG\r\nexample asset bytes")
            (assets / "earth.zip").write_bytes(b"unconverted archive")
            (assets / ".DS_Store").write_bytes(b"clutter")
            (assets / "secret.ini").write_bytes(b"private config")
            outside = root / "external.png"
            outside.write_bytes(b"external")
            (assets / "linked.png").symlink_to(outside)
            (assets / "linked-dir").symlink_to(root, target_is_directory=True)
            with patch.object(release, "ROOT", root):
                included, excluded = release.asset_inventory(root / "assets")
                self.assertEqual([p.name for p in included], ["earth.png", "earth.zip"])
                self.assertEqual(set(excluded), {
                    "assets/maps/.DS_Store", "assets/maps/secret.ini",
                    "assets/maps/linked.png", "assets/maps/linked-dir"})
                record = release.copy_asset(original, root / "candidate/assets/maps/earth.png")
                self.assertEqual(record["bytes"], original.stat().st_size)
                self.assertEqual((root / "candidate/assets/maps/earth.png").read_bytes(),
                                 original.read_bytes())


if __name__ == "__main__":
    unittest.main()
