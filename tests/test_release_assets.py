"""Check bundled assets directly against the Git index without exporting files."""
import subprocess
import unittest
from .support import PROJECT
from . import release_policy

class ReleaseAssetsTests(unittest.TestCase):
    def test_tracked_assets_are_regular_and_match_index_bytes_and_modes(self):
        if not (PROJECT / "maps").exists():
            self.skipTest("asset bundle absent from source-only checkout")
        raw = subprocess.check_output(["git", "ls-files", "--stage", "-z", "--", "maps/"], cwd=PROJECT)
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

    def test_solar_system_index_references_real_files_and_folder_names(self):
        import re
        solar=PROJECT/'maps/solarsystem'
        self.assertTrue(solar.is_dir())
        indexed=[]
        for line in (solar/'body-maps.txt').read_text().splitlines():
            self.assertTrue(line.startswith('map=/solarsystem/'),line)
            relative=line.removeprefix('map=/solarsystem/')
            self.assertNotIn('..',relative.split('/'))
            path=solar/relative
            self.assertTrue(path.is_file() and not path.is_symlink(),relative)
            folder=relative.split('/')[0]
            self.assertTrue(folder=='celestia-textures' or re.fullmatch(r'\d{2}-\d{2}-[a-z]+',folder),folder)
            indexed.append(relative)
        self.assertGreater(len(indexed),100)
        self.assertEqual(len(indexed),len(set(indexed)))
