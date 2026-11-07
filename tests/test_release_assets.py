"""Check bundled assets directly against the Git index without exporting files."""
import subprocess
import unittest
import tempfile
from pathlib import Path
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

    def test_map_family_rename_preserves_index_with_explicit_add_despite_ignore_policy(self):
        # A filesystem rename alone is not permission to publish newly named maps.
        with tempfile.TemporaryDirectory(prefix='xplanet-map-index-') as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.STDOUT)
            git('init', '-q')
            (root / '.gitignore').write_bytes((PROJECT / '.gitignore').read_bytes())
            old = root / 'maps/old-family'
            old.mkdir(parents=True)
            for name in ('day.png', 'night.png'):
                (old / name).write_bytes(('fixture ' + name).encode())
            git('add', '.gitignore')
            git('add', '-f', 'maps/old-family')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '-qm', 'fixture maps')
            renamed = root / 'maps/renamed-family'
            old.rename(renamed)
            git('add', '-A')
            self.assertEqual(git('ls-files', '--', 'maps/').decode(), '')
            git('add', '-f', '--', 'maps/renamed-family')
            self.assertEqual(git('ls-files', '--', 'maps/').decode().splitlines(),
                             ['maps/renamed-family/day.png', 'maps/renamed-family/night.png'])
            for name in ('day.png', 'night.png'):
                self.assertEqual(git('show', ':maps/renamed-family/' + name), ('fixture ' + name).encode())
            git('mv', 'maps/renamed-family', 'maps/final-family')
            git('add', '-A')
            self.assertEqual(git('ls-files', '--', 'maps/').decode().splitlines(),
                             ['maps/final-family/day.png', 'maps/final-family/night.png'])
            private = root / 'maps/new-private-family/personal.png'
            private.parent.mkdir(); private.write_bytes(b'not authorized for release')
            git('add', '-A')
            self.assertEqual(git('check-ignore', 'maps/new-private-family/personal.png').strip(),
                             b'maps/new-private-family/personal.png')
            self.assertNotIn('personal.png', git('ls-files').decode())
