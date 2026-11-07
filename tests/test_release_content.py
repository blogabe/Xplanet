"""Guard the private development checkout's current public-file boundary."""
import re
import subprocess
import tomllib
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from .support import PROJECT


class ReleaseContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        check = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=PROJECT,
            text=True, capture_output=True, check=False)
        if check.returncode or check.stdout.strip() != str(PROJECT):
            raise unittest.SkipTest("release index checks require this Git checkout")

    @staticmethod
    def tracked():
        raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"],
                                      cwd=PROJECT)
        for row in raw.split(b"\0"):
            if row:
                metadata, name = row.split(b"\t", 1)
                yield metadata.split(b" ", 1)[0].decode(), name.decode()

    def test_index_excludes_personal_runtime_and_recovery_content(self):
        from . import release_policy as release
        entries = list(self.tracked())
        release.check_source_paths({name: mode + " blob " + "0" * 40
                                    for mode, name in entries})
        names = [name for _, name in entries]
        self.assertIn("scripts/xplanet.sh", names)
        self.assertIn("config/totalmarker.example.toml", names)
        self.assertIn("config/xp.conf.example", names)
        self.assertIn("config/xp.def.example", names)
        entrypoints = {name for name in names if name.startswith("scripts/")
                       and "/" not in name[len("scripts/"):]}
        self.assertEqual(entrypoints, {"scripts/xplanet.sh", "scripts/xp-setup.sh",
                                       "scripts/xp-bootstrap.sh",
                                       "scripts/run-totalmarker", "scripts/run-configurator",
                                       "scripts/import-satellite-icons"})
        self.assertFalse(any(name.startswith("examples/") and name.endswith(".ini")
                             for name in names))

    def test_privacy_policy_rejects_private_names_inside_source_directories(self):
        from . import release_policy as release
        unsafe = (
            "tests/.tmp/capture.json", "tests/configurator/.tmp/session.json",
            "tests/configurator/ui/.tmp/session.json", "tests/.state/state.json",
            "tests/.cache/token.json", "tests/__pycache__/module.pyc",
            "tests/.git/config", "tests/.GiT/config", "tests/.DS_Store",
            "tests/._fixture.json", "tests/.env", "tests/.env.local",
            "tests/.env-data/token.json", "tests/result.log", "tests/private.key",
            "tests/private.pem", "tests/private.ini", "tests/module.pyc",
            "tests/module.pyo", "tests/module.pyd",
            "output/preview/earth-render.png", "output/exports/copy/export.json",
            "output/future-private-file.txt",
        )
        for name in unsafe:
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "unsafe source entry"):
                release.check_source_paths({name: "100644 blob " + "0" * 40})
        safe = (
            "config/totalmarker.example.toml", "examples/custom.example.toml",
            "tests/fixtures/example.toml", "tests/fixtures/example.json",
            "tests/fixtures/cache/response.json", "tests/test_log_trim.py",
            "scripts/launchd/local.xplanet.start.plist.example", ".gitignore",
            ".gitattributes", ".github/workflows/offline-tests.yml",
        )
        for name in safe:
            with self.subTest(name=name):
                release.check_source_paths({name: "100644 blob " + "0" * 40})

    def test_privacy_policy_rejects_force_tracked_private_fixture(self):
        from . import release_policy as release
        for name in ("tests/.env.local", "tests/configurator/ui/.tmp/capture.json",
                     "output/exports/copy/preview.png"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                private = root / name
                private.parent.mkdir(parents=True)
                private.write_bytes(b"private fixture sentinel")
                before = private.read_bytes()
                with self.assertRaisesRegex(RuntimeError, "unsafe source entry"):
                    release.check_source_paths({name: "100644 blob " + "0" * 40})
                self.assertEqual(private.read_bytes(), before)

    def test_personal_paths_are_ignored_even_if_files_exist(self):
        private = (
            "config/totalmarker.toml", "config/xp.def", "config/xp.conf",
            "scripts/launchd/local.xplanet.start.plist",
            "dev/open-items.txt", "dev/configurator-open-items.txt",
            "dev/configurator-foundation-20261102/verification.md",
            "scripts/configurator/__pycache__/module.pyc",
            "scripts/configurator/.env.local", "scripts/configurator/private.key",
            "tests/configurator/ui/.tmp/capture", "tests/configurator/ui/result.log",
            "dev/reference/private/file",
            "dev/recovery/archive", "dev/validation/frame.png",
            "dev/todel/snapshot", "dev/preview/earth-render.png",
            "output/preview/earth-manual.png", "output/preview/earth-render.png",
            "output/exports/copy/export.json", "output/future-private-file.txt",
            "tests/.tmp/capture", "maps/personal.png",
            ".state/totalmarker/state.json", "logs/totalmarker/events.jsonl",
        )
        for path in private:
            with self.subTest(path=path):
                result = subprocess.run(["git", "check-ignore", "-q", path],
                                        cwd=PROJECT, check=False)
                self.assertEqual(result.returncode, 0, path)

    def test_tracked_text_has_no_known_private_identifiers(self):
        forbidden = re.compile(b"|".join((
            rb"/Users/(?!example/)[A-Za-z0-9._-]+/",
            b"Proton" + rb"Drive-[^/\s\"']+",
            rb"libfile_[0-9a-f]{16,}")))
        from .release_policy import index_text
        for name,raw in index_text(PROJECT):
            with self.subTest(path=name):self.assertIsNone(forbidden.search(raw),name)

    def test_readme_monthly_map_example_has_all_shipped_months(self):
        if (not (PROJECT / "maps").exists()
                and not any(name.startswith(("maps/", "assets/")) for _, name in self.tracked())):
            self.skipTest("optional asset bundle absent from source checkout; validate it in the complete checkout")
        readme = (PROJECT / "README.md").read_text()
        match = re.search(r"`EARTH_MAP_PRE=([A-Za-z0-9.]+)/([A-Za-z0-9.]+)`", readme)
        self.assertIsNotNone(match)
        folder, stem = match.groups()
        self.assertIn(f"{folder}/{stem}",
                      (PROJECT / "config/xp.def.example").read_text())
        for month in range(1, 13):
            path = (PROJECT / "maps" / folder /
                    f"{stem}.2004{month:02d}.3x5400x2700.png")
            self.assertTrue(path.is_file() and not path.is_symlink(), path)

    def test_source_only_skip_does_not_hide_an_incomplete_release_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("`EARTH_MAP_PRE=world.topo/world.topo`")
            (root / "config").mkdir()
            (root / "config/xp.def.example").write_text("world.topo/world.topo")
            with patch(__name__ + ".PROJECT", root):
                with patch.object(self, "tracked", return_value=iter(())):
                    with self.assertRaises(unittest.SkipTest):
                        self.test_readme_monthly_map_example_has_all_shipped_months()
                # A packaged bundle containing icons but omitting promised maps
                # must fail rather than inheriting the source-only exemption.
                with patch.object(self, "tracked", return_value=iter((("100644", "assets/icons/example.png"),))):
                    with self.assertRaises(AssertionError):
                        self.test_readme_monthly_map_example_has_all_shipped_months()

    def test_public_toml_examples_contain_no_credentials(self):
        examples = [PROJECT / "config/totalmarker.example.toml"]
        examples.extend((PROJECT / "examples").glob("*.example.toml"))
        for path in examples:
            with self.subTest(path=path.name):
                cloud = tomllib.loads(path.read_text())["cloud"]
                for provider in ("xeric", "custom"):
                    for key in ("username", "password"):
                        self.assertEqual(cloud.get(provider, {}).get(key, ""), "")


    def test_stock_scene_pairs_are_regular_tracked_source_export_inputs(self):
        names={name:mode for mode,name in self.tracked()}
        for stem in ('earth-solar-dawn','earth-september','earth-from-moon','moon-from-earth','jupiter-cloudtops','saturn-rings'):
            for suffix in ('.def','.conf'):
                name='scripts/configurator/samples/scenes/'+stem+suffix
                self.assertEqual(names.get(name),'100644',name)


class IndexedPrivacyTests(unittest.TestCase):
    def test_force_added_output_is_rejected_from_actual_index_without_changing_bytes(self):
        from .release_policy import index_text
        for name in ('output/preview/earth-render.png','output/exports/copy/export.json','output/future.dat'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);subprocess.run(['git','init','-q'],cwd=root,check=True)
                (root/'.gitignore').write_text('/output/\n')
                path=root/name;path.parent.mkdir(parents=True);path.write_bytes(b'private user output')
                subprocess.run(['git','add','-f','--',name],cwd=root,check=True)
                with self.assertRaisesRegex(RuntimeError,'unsafe source entry: '+name):index_text(root)
                self.assertEqual(path.read_bytes(),b'private user output')

    def test_scan_uses_index_bytes_and_checks_all_paths(self):
        from .release_policy import index_text
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            path=root/'README.md';path.write_text('indexed text')
            subprocess.run(['git','add','README.md'],cwd=root,check=True)
            path.write_text('different working bytes')
            self.assertEqual(index_text(root),[('README.md',b'indexed text')])
            (root/'dev').mkdir();(root/'dev/private.bin').write_bytes(b'local')
            subprocess.run(['git','add','dev/private.bin'],cwd=root,check=True)
            with self.assertRaisesRegex(RuntimeError,'unsafe source entry: dev/private.bin'):
                index_text(root)


    def test_provider_text_fixture_suffixes_are_scanned_from_index_bytes(self):
        from .release_policy import index_text
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);subprocess.run(['git','init','-q'],cwd=root,check=True)
            fixtures={'tests/fixtures/feed.dat':b'indexed storm text',
                      'tests/fixtures/feed.geojson':b'{"fixture":"indexed"}'}
            for name,data in fixtures.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                subprocess.run(['git','add','-f','--',name],cwd=root,check=True)
                path.write_bytes(b'changed working bytes')
            self.assertEqual(dict(index_text(root)),fixtures)

    def test_new_text_fixture_suffix_obeys_indexed_text_budget(self):
        from . import release_policy as release
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);subprocess.run(['git','init','-q'],cwd=root,check=True)
            path=root/'feed.geojson';path.write_bytes(b'x'*9)
            subprocess.run(['git','add','feed.geojson'],cwd=root,check=True)
            with patch.object(release,'TEXT_LIMIT',8),self.assertRaisesRegex(RuntimeError,'Indexed text exceeds'):
                release.index_text(root)

    def test_binary_fixture_size_and_total_budgets_fail_closed(self):
        from . import release_policy as release
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);subprocess.run(['git','init','-q'],cwd=root,check=True)
            path=root/'fixture.kmz';path.write_bytes(b'x'*9)
            subprocess.run(['git','add','fixture.kmz'],cwd=root,check=True)
            with patch.object(release,'BINARY_LIMIT',8),self.assertRaisesRegex(RuntimeError,'Indexed binary'):
                release.index_text(root)
            path.write_bytes(b'x'*6);(root/'second.kmz').write_bytes(b'y'*6)
            subprocess.run(['git','add','fixture.kmz','second.kmz'],cwd=root,check=True)
            with patch.object(release,'BINARY_LIMIT',16),patch.object(release,'BINARY_TOTAL_LIMIT',10),self.assertRaisesRegex(RuntimeError,'Indexed binary'):
                release.index_text(root)

    def test_binary_size_guard_does_not_replace_shipped_map_asset_policy(self):
        from . import release_policy as release
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);subprocess.run(['git','init','-q'],cwd=root,check=True)
            path=root/'maps/family/map.png';path.parent.mkdir(parents=True);path.write_bytes(b'x'*20)
            subprocess.run(['git','add','-f','--','maps/family/map.png'],cwd=root,check=True)
            with patch.object(release,'BINARY_LIMIT',8),patch.object(release,'BINARY_TOTAL_LIMIT',10):
                self.assertEqual(release.index_text(root),[])
