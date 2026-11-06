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
        names = []
        from . import release_policy as release
        for mode, name in self.tracked():
            names.append(name)
            self.assertFalse(release.private_source_path(name), name)
            self.assertNotEqual(mode, "120000", f"tracked symlink: {name}")
            parts = name.split("/")
            self.assertFalse({".git", ".state", "__pycache__"} & set(parts), name)
            self.assertNotIn(".DS_Store", parts, name)
            if name.startswith("config/"):
                self.assertIn(name, {"config/earth.example",
                                     "config/totalmarker.example.toml",
                                     "config/xp.conf.example", "config/xp.def.example"})
            if name.startswith("scripts/launchd/"):
                self.assertTrue(name.endswith(".plist.example"), name)
            if name.startswith("dev/"):
                self.assertTrue(name.startswith(("dev/tests/", "dev/examples/")), name)
                self.assertNotIn(".tmp", parts, name)
            if name.startswith("assets/"):
                self.assertFalse(any(part in {".DS_Store", "__MACOSX", "Thumbs.db",
                                              "desktop.ini"} or part.startswith("._")
                                     for part in parts), name)
            self.assertFalse(name.startswith(("images/", "markers/",
                                              "arcs/", "satellites/", "logs/")), name)
        self.assertIn("scripts/xplanet.sh", names)
        self.assertIn("config/totalmarker.example.toml", names)
        self.assertIn("config/xp.conf.example", names)
        self.assertIn("config/xp.def.example", names)
        entrypoints = {name for name in names if name.startswith("scripts/")
                       and "/" not in name[len("scripts/"):]}
        self.assertEqual(entrypoints, {"scripts/xplanet.sh", "scripts/xp-setup.sh",
                                       "scripts/xp-bootstrap.sh",
                                       "scripts/run-totalmarker", "scripts/run-configurator"})
        self.assertFalse(any(name.startswith("dev/examples/") and name.endswith(".ini")
                             for name in names))

    def test_privacy_policy_rejects_private_names_inside_source_directories(self):
        from . import release_policy as release
        unsafe = (
            "dev/tests/.tmp/capture.json", "dev/tests/configurator/.tmp/session.json",
            "dev/tests/configurator/ui/.tmp/session.json", "dev/tests/.state/state.json",
            "dev/tests/.cache/token.json", "dev/tests/__pycache__/module.pyc",
            "dev/tests/.git/config", "dev/tests/.GiT/config", "dev/tests/.DS_Store",
            "dev/tests/._fixture.json", "dev/tests/.env", "dev/tests/.env.local",
            "dev/tests/.env-data/token.json", "dev/tests/result.log", "dev/tests/private.key",
            "dev/tests/private.pem", "dev/tests/private.ini", "dev/tests/module.pyc",
            "dev/tests/module.pyo", "dev/tests/module.pyd",
        )
        for name in unsafe:
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "unsafe source entry"):
                release.check_source_paths({name: "100644 blob " + "0" * 40})
        safe = (
            "config/totalmarker.example.toml", "dev/examples/custom.example.toml",
            "dev/tests/fixtures/example.toml", "dev/tests/fixtures/example.json",
            "dev/tests/fixtures/cache/response.json", "dev/tests/test_log_trim.py",
            "scripts/launchd/local.xplanet.start.plist.example", ".gitignore",
            ".gitattributes", ".github/workflows/offline-tests.yml",
        )
        for name in safe:
            with self.subTest(name=name):
                release.check_source_paths({name: "100644 blob " + "0" * 40})

    def test_privacy_policy_rejects_force_tracked_private_fixture(self):
        from . import release_policy as release
        for name in ("dev/tests/.env.local", "dev/tests/configurator/ui/.tmp/capture.json"):
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
            "dev/tests/configurator/ui/.tmp/capture", "dev/tests/configurator/ui/result.log",
            "dev/reference/private/file",
            "dev/recovery/archive", "dev/validation/frame.png",
            "dev/todel/snapshot", "dev/preview/earth-render.png",
            "dev/tests/.tmp/capture", "assets/maps/personal.png",
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
        for _, name in self.tracked():
            path = PROJECT / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 5_000_000:
                continue
            with self.subTest(path=name):
                self.assertIsNone(forbidden.search(path.read_bytes()), name)

    def test_readme_monthly_map_example_has_all_shipped_months(self):
        if (not (PROJECT / "assets/maps").exists()
                and not any(name.startswith("assets/") for _, name in self.tracked())):
            self.skipTest("optional asset bundle absent from source checkout; validate it in the complete checkout")
        readme = (PROJECT / "README.md").read_text()
        match = re.search(r"`EARTH_MAP_PRE=([A-Za-z0-9.]+)/([A-Za-z0-9.]+)`", readme)
        self.assertIsNotNone(match)
        folder, stem = match.groups()
        self.assertIn(f"{folder}/{stem}",
                      (PROJECT / "config/xp.def.example").read_text())
        for month in range(1, 13):
            path = (PROJECT / "assets/maps" / folder /
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
        examples.extend((PROJECT / "dev/examples").glob("*.example.toml"))
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
