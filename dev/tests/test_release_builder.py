"""The local release builder runs only against isolated Git and asset fixtures."""
import json
import os
import subprocess
from unittest.mock import patch

from dev.release import build_candidate as release
from .support import Sandbox


class ReleaseBuilderTests(Sandbox):
    def setUp(self):
        super().setUp()
        (self.root / ".gitignore").write_text("assets/\ndev/release-staging/\nconfig/totalmarker.toml\n")
        scripts = self.root / "scripts"
        scripts.mkdir()
        launcher = scripts / "xplanet.sh"
        launcher.write_text(
            "#!/bin/sh\n"
            "[ \"$1\" = test ] || exit 64\n"
            "printf 'isolated package checks ran\\n'\n"
            "if [ \"${TM_LEAK_PRIVATE:-0}\" = 1 ]; then\n"
            "  mkdir -p config; printf secret > config/totalmarker.toml\n"
            "fi\n"
            "if [ \"${TM_LEAK_NESTED_GIT:-0}\" = 1 ]; then\n"
            "  mkdir -p assets/maps/.git; printf secret > assets/maps/.git/private-history\n"
            "fi\n"
            "[ \"${TM_FAIL_PACKAGE_TESTS:-0}\" != 1 ]\n")
        launcher.chmod(0o755)
        maps = self.root / "assets/maps/default"
        maps.mkdir(parents=True)
        (maps / "map.png").write_bytes(b"public fixture asset")
        (maps / "earth.jpg").symlink_to("/missing/external/earth.jpg")
        (self.root / "assets/private.toml").write_text("not for export")
        nested = self.root / "assets/.git"
        nested.mkdir()
        (nested / "history").write_bytes(b"private history")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("add", ".gitignore", "scripts/xplanet.sh")
        self.git("add", "-f", "assets/maps/default/map.png")
        self.git("commit", "-q", "-m", "fixture")
        self.staging = self.root / "dev/release-staging"
        self.output = self.staging / "candidate-next"
        self.fallback = self.staging / "candidate"
        self.fallback.mkdir(parents=True)
        (self.fallback / "KEEP").write_bytes(b"known good candidate")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def build(self):
        with patch.object(release, "ROOT", self.root), \
             patch.object(release, "STAGING", self.staging), \
             patch.object(release, "OUTPUT", self.output), \
             patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull,
                                     "GIT_CONFIG_NOSYSTEM": "1"}):
            release.build()

    def test_current_committed_tree_matches_exporter_boundary(self):
        # Exercise the actual repository model, not only a synthetic source tree.
        from .support import PROJECT
        entries = release.tree_entries(PROJECT, "HEAD")
        release.check_source_paths(entries)
        self.assertTrue(any(name.startswith("assets/") for name in entries))

    def test_license_notices_export_but_local_working_sources_do_not(self):
        (self.root / 'LICENSE').write_text('fixture license notice\n')
        (self.root / 'docs').mkdir()
        (self.root / 'docs/asset-credits.md').write_text('fixture third-party notice\n')
        with (self.root / '.gitignore').open('a') as stream:
            stream.write('dev/asset-sources-test/\n')
        local = self.root / 'dev/asset-sources-test'
        local.mkdir(parents=True)
        (local / 'source-tile.png').write_bytes(b'local working fixture')
        (local / 'manifest.json').write_text('local restore fixture')
        self.git('add', '.gitignore', 'LICENSE', 'docs/asset-credits.md')
        self.git('commit', '-q', '-m', 'notices and local working-source boundary')
        self.build()
        self.assertEqual((self.output / 'LICENSE').read_bytes(),
                         (self.root / 'LICENSE').read_bytes())
        self.assertEqual((self.output / 'docs/asset-credits.md').read_bytes(),
                         (self.root / 'docs/asset-credits.md').read_bytes())
        self.assertFalse((self.output / 'dev/asset-sources-test').exists())
        self.assertEqual((local / 'source-tile.png').read_bytes(), b'local working fixture')

    def test_force_tracked_local_working_sources_are_rejected(self):
        local = self.root / 'dev/asset-sources-test'
        local.mkdir(parents=True)
        (local / 'manifest.json').write_text('local restore fixture')
        self.git('add', '-f', 'dev/asset-sources-test/manifest.json')
        self.git('commit', '-q', '-m', 'unsafe local preservation material')
        with self.assertRaisesRegex(RuntimeError, 'unsafe source entry'):
            self.build()
        self.assertFalse(self.output.exists())
        self.assertEqual((self.fallback / 'KEEP').read_bytes(), b'known good candidate')

    def test_untracked_regular_asset_is_not_exported(self):
        (self.root / "assets/maps/default/personal.png").write_bytes(b"not committed")
        self.build()
        self.assertFalse((self.output / "assets/maps/default/personal.png").exists())
        manifest = json.loads(next(self.staging.glob("candidate-manifest-*.json")).read_text())
        self.assertIn("assets/maps/default/personal.png", manifest["asset_exclusions"])

    def test_tracked_private_asset_is_rejected_before_staging(self):
        self.git("add", "-f", "assets/private.toml")
        self.git("commit", "-q", "-m", "unsafe tracked asset")
        with self.assertRaisesRegex(RuntimeError, "unsafe source entry"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_hidden_working_asset_change_is_not_exported_as_committed(self):
        self.git("update-index", "--assume-unchanged", "assets/maps/default/map.png")
        (self.root / "assets/maps/default/map.png").write_bytes(b"uncommitted bytes")
        with self.assertRaisesRegex(RuntimeError, "asset bytes differ from source HEAD"):
            self.build()
        self.assertFalse((self.output / ".git").exists())
        self.assertEqual(list(self.staging.glob("candidate-manifest-*.json")), [])

    def test_committed_asset_mode_is_preserved(self):
        self.git("update-index", "--chmod=+x", "assets/maps/default/map.png")
        (self.root / "assets/maps/default/map.png").chmod(0o755)
        self.git("commit", "-q", "-m", "executable fixture asset")
        self.build()
        self.assertTrue(self.git("ls-tree", "HEAD", "assets/maps/default/map.png").startswith("100755"))
        self.assertTrue(subprocess.check_output(
            ["git", "-C", str(self.output), "ls-tree", "HEAD", "assets/maps/default/map.png"],
            text=True).startswith("100755"))

    def test_clean_export_checks_assets_privacy_history_and_package_tests(self):
        self.build()
        manifest_path = next(self.staging.glob("candidate-manifest-*.json"))
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["asset_files_count"], 1)
        self.assertEqual(manifest["asset_bytes"], len(b"public fixture asset"))
        self.assertIn("assets/maps/default/earth.jpg", manifest["asset_exclusions"])
        self.assertIn("assets/private.toml", manifest["asset_exclusions"])
        self.assertIn("assets/.git", manifest["asset_exclusions"])
        self.assertEqual((self.output / "assets/maps/default/map.png").read_bytes(),
                         b"public fixture asset")
        self.assertFalse((self.output / "assets/private.toml").exists())
        self.assertFalse((self.output / "assets/.git").exists())
        self.assertEqual(subprocess.check_output(
            ["git", "-C", str(self.output), "rev-list", "--count", "HEAD"],
            text=True).strip(), "1")
        self.assertEqual(subprocess.check_output(
            ["git", "-C", str(self.output), "remote"], text=True).strip(), "")
        self.assertIn("isolated package checks ran",
                      (self.staging / "candidate-next-test.log").read_text())
        self.assertEqual((self.fallback / "KEEP").read_bytes(), b"known good candidate")

    def test_failed_package_check_preserves_fallback_and_withholds_manifest(self):
        with patch.dict(os.environ, {"TM_FAIL_PACKAGE_TESTS": "1"}):
            with self.assertRaisesRegex(RuntimeError, "exported package tests failed"):
                self.build()
        self.assertTrue(self.output.is_dir())  # Failed staging remains inspectable.
        self.assertEqual(list(self.staging.glob("candidate-manifest-*.json")), [])
        self.assertEqual((self.fallback / "KEEP").read_bytes(), b"known good candidate")
        with self.assertRaises(FileExistsError):
            self.build()

    def test_ignored_private_output_after_tests_withholds_manifest(self):
        with patch.dict(os.environ, {"TM_LEAK_PRIVATE": "1"}):
            with self.assertRaisesRegex(RuntimeError, "candidate checkout has unexpected files"):
                self.build()
        self.assertEqual(list(self.staging.glob("candidate-manifest-*.json")), [])
        self.assertEqual((self.fallback / "KEEP").read_bytes(), b"known good candidate")

    def test_nested_git_history_after_tests_withholds_manifest(self):
        with patch.dict(os.environ, {"TM_LEAK_NESTED_GIT": "1"}):
            with self.assertRaisesRegex(RuntimeError, "candidate checkout has unexpected files"):
                self.build()
        self.assertTrue((self.output / "assets/maps/.git/private-history").is_file())
        self.assertEqual(list(self.staging.glob("candidate-manifest-*.json")), [])
        self.assertEqual((self.fallback / "KEEP").read_bytes(), b"known good candidate")

    def test_tracked_personal_config_is_rejected_before_staging(self):
        personal = self.root / "config/totalmarker.toml"
        personal.parent.mkdir()
        personal.write_text("secret fixture")
        self.git("add", "-f", "config/totalmarker.toml")
        self.git("commit", "-q", "-m", "bad tracked config")
        with self.assertRaisesRegex(RuntimeError, "unsafe source entry"):
            self.build()
        self.assertFalse(self.output.exists())
        self.assertEqual((self.fallback / "KEEP").read_bytes(), b"known good candidate")
