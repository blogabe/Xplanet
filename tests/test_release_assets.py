"""Check bundled assets directly against the Git index without exporting files."""
import subprocess
import unittest
from .support import PROJECT
from . import release_policy

class ReleaseAssetsTests(unittest.TestCase):
    def test_tracked_assets_are_regular_and_match_index_bytes_and_modes(self):
        if not (PROJECT / "assets").exists():
            self.skipTest("asset bundle absent from source-only checkout")
        raw = subprocess.check_output(["git", "ls-files", "--stage", "-z", "--", "assets/"], cwd=PROJECT)
        count = 0
        for row in raw.split(b"\0"):
            if not row:
                continue
            metadata, name = row.split(b"\t", 1)
            mode, identity, stage = metadata.decode().split()
            name = name.decode()
            with self.subTest(asset=name):
                release_policy.check_source_paths({name: metadata.decode()})
                path = PROJECT / name
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.is_file())
                self.assertEqual(stage, "0")
                actual = subprocess.check_output(["git", "hash-object", "--no-filters", "--", name], cwd=PROJECT).strip().decode()
                self.assertEqual(actual, identity, "asset bytes differ from index")
                self.assertEqual(bool(path.stat().st_mode & 0o111), mode == "100755")
                count += 1
        self.assertGreater(count, 0, "complete asset directory has no tracked assets")
