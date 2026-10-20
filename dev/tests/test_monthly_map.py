"""Monthly Earth map selection uses only isolated shell fixtures."""
from datetime import datetime
from pathlib import Path
import shlex
import shutil
import subprocess

from .support import PROJECT, Sandbox


class MonthlyMapTests(Sandbox):
    def test_stock_package_maps_need_no_monthly_link(self):
        original = self.link.readlink()
        self.write_definition("stock")
        result = self.run_earth()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Stock Xplanet maps", result.stdout)
        self.assertEqual(self.link.readlink(), original)

    def setUp(self):
        super().setUp()
        (self.root / "images").mkdir()
        (self.root / "assets/maps/world").mkdir(parents=True)
        (self.root / "config").mkdir()
        scripts = self.root / "scripts"
        scripts.mkdir()
        shutil.copy2(PROJECT / "scripts/xplanet.sh", scripts / "xplanet.sh")
        self.current = datetime.now().month
        self.filename = f"world.2004{self.current:02d}.3x5400x2700.png"
        self.chosen = self.root / "assets/maps/world" / self.filename
        self.chosen.write_bytes(b"selected map fixture")
        self.old = self.root / "assets/maps/world/world.200401.3x5400x2700.png"
        self.old.write_bytes(b"old map fixture")
        self.link = self.root / "images/earth.png"
        self.link.symlink_to("../assets/maps/world/world.200401.3x5400x2700.png")
        self.definition = self.root / "config/xp.def"
        self.write_definition("world/world")

    def write_definition(self, prefix):
        self.definition.write_text("XPLANET_HOME=" + shlex.quote(str(self.root)) +
                                   "\nEARTH_MAP_PRE=" + shlex.quote(prefix) + "\n")

    def run_earth(self):
        return subprocess.run([str(self.root / "scripts/xplanet.sh"), "earth"],
                              cwd=PROJECT, env={"PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True, check=False)

    def test_switches_current_map_and_preserves_source_bytes(self):
        before = self.chosen.read_bytes()
        first = self.run_earth()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.link.readlink(), Path("../assets/maps/world/" + self.filename))
        self.assertEqual(self.chosen.read_bytes(), before)
        self.assertIn("Earth map unchanged", self.run_earth().stdout)

    def test_configured_topographic_pattern_and_missing_month(self):
        selected = self.root / "assets/maps/world.topo.bathy"
        selected.mkdir()
        image = selected / f"world.topo.bathy.2004{self.current:02d}.3x5400x2700.png"
        image.write_bytes(b"bathy fixture")
        self.write_definition("world.topo.bathy/world.topo.bathy")
        done = self.run_earth()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.link.readlink(), Path("../assets/maps/world.topo.bathy/" + image.name))
        image.unlink()
        missing = self.run_earth()
        self.assertEqual(missing.returncode, 2)
        self.assertIn("Monthly map is absent", missing.stderr)
        self.assertEqual(self.link.readlink(), Path("../assets/maps/world.topo.bathy/" + image.name))

    def test_invalid_prefix_and_custom_destination_are_preserved(self):
        original = self.link.readlink()
        for prefix in ("../world", "world/../world", "/world/world", "world/world/extra"):
            with self.subTest(prefix=prefix):
                self.write_definition(prefix)
                self.assertEqual(self.run_earth().returncode, 2)
                self.assertEqual(self.link.readlink(), original)
        self.write_definition("world/world")
        self.link.unlink()
        self.link.write_bytes(b"personal map")
        result = self.run_earth()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a symlink", result.stderr)
        self.assertEqual(self.link.read_bytes(), b"personal map")
        self.link.unlink()
        self.link.symlink_to("../../outside.png")
        result = self.run_earth()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not an internal map link", result.stderr)

    def test_source_symlink_and_linked_parent_are_rejected(self):
        external = self.base / "external.png"
        external.write_bytes(b"outside fixture")
        self.chosen.unlink()
        self.chosen.symlink_to(external)
        result = self.run_earth()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a regular file", result.stderr)
        self.assertEqual(external.read_bytes(), b"outside fixture")
        self.chosen.unlink()
        folder = self.root / "assets/maps/world"
        folder.rename(self.root / "assets/maps/world.saved")
        folder.symlink_to(self.base)
        result = self.run_earth()
        self.assertEqual(result.returncode, 2)
        self.assertIn("real directory", result.stderr)
