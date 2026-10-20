"""Guard the private development checkout's current public-file boundary."""
import re
import subprocess
import tomllib
import unittest

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
        for mode, name in self.tracked():
            names.append(name)
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
                self.assertTrue(name.startswith(("dev/tests/", "dev/examples/", "dev/release/")), name)
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
                                       "scripts/run-totalmarker"})
        self.assertFalse(any(name.startswith("dev/examples/") and name.endswith(".ini")
                             for name in names))

    def test_personal_paths_are_ignored_even_if_files_exist(self):
        private = (
            "config/totalmarker.toml", "config/xp.def", "config/xp.conf",
            "scripts/launchd/local.xplanet.start.plist",
            "dev/open-items.txt", "dev/reference/private/file",
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

    def test_public_toml_examples_contain_no_credentials(self):
        examples = [PROJECT / "config/totalmarker.example.toml"]
        examples.extend((PROJECT / "dev/examples").glob("*.example.toml"))
        for path in examples:
            with self.subTest(path=path.name):
                cloud = tomllib.loads(path.read_text())["cloud"]
                for provider in ("xeric", "custom"):
                    for key in ("username", "password"):
                        self.assertEqual(cloud.get(provider, {}).get(key, ""), "")
