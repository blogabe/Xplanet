"""Monthly Earth map selection uses only isolated shell fixtures."""
from pathlib import Path
import shlex
import subprocess
import sys

from .support import PROJECT, Sandbox, copy_launcher


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
        (self.root / "maps/world").mkdir(parents=True)
        (self.root / "config").mkdir()
        scripts = self.root / "scripts"
        scripts.mkdir()
        copy_launcher(scripts / "xplanet.sh")
        # A fixed command clock keeps fixture choice independent of host month/TZ.
        self.bin = self.base / "bin"
        self.bin.mkdir()
        date = self.bin / "date"
        date.write_text(f"#!{sys.executable}\n"
                        "import os, sys, time\n"
                        "if sys.argv[1:] != ['+%m']: raise SystemExit(97)\n"
                        "if hasattr(time, 'tzset'): time.tzset()\n"
                        "epoch = os.environ.get('TEST_DATE_EPOCH')\n"
                        "print(time.strftime('%m', time.localtime(int(epoch))) if epoch else os.environ['TEST_MONTH'])\n")
        date.chmod(0o700)
        self.current = 6
        self.filename = f"world.2004{self.current:02d}.3x5400x2700.png"
        self.chosen = self.root / "maps/world" / self.filename
        self.chosen.write_bytes(b"selected map fixture")
        self.old = self.root / "maps/world/world.200401.3x5400x2700.png"
        self.old.write_bytes(b"old map fixture")
        self.link = self.root / "images/earth.png"
        self.link.symlink_to("../maps/world/world.200401.3x5400x2700.png")
        self.definition = self.root / "config/xp.def"
        self.write_definition("world/world")

    def write_definition(self, prefix):
        self.definition.write_text("XPLANET_HOME=" + shlex.quote(str(self.root)) +
                                   "\nEARTH_MAP_PRE=" + shlex.quote(prefix) + "\n")

    def run_earth(self, *, month=None, timezone="UTC", epoch=""):
        return subprocess.run([str(self.root / "scripts/xplanet.sh"), "earth"],
                              cwd=PROJECT, env={"PATH": f"{self.bin}:/usr/bin:/bin", "TZ": timezone,
                                   "TEST_MONTH": f"{month or self.current:02d}",
                                   "TEST_DATE_EPOCH": str(epoch)},
                              capture_output=True, text=True, check=False)

    def test_existing_lock_is_preserved_with_recovery_guidance(self):
        lock = self.root / ".state/totalmarker/map.lock.d"
        lock.mkdir(parents=True)
        before = self.link.readlink()
        result = self.run_earth()
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(lock), result.stderr)
        self.assertIn("If none is running", result.stderr)
        self.assertIn("rmdir", result.stderr)
        self.assertTrue(lock.is_dir())
        self.assertEqual(self.link.readlink(), before)

    def test_term_releases_owned_lock_without_changing_map(self):
        ln = self.bin / "ln"
        ln.write_text('#!/bin/sh\nkill -TERM "$PPID"\nexit 0\n')
        ln.chmod(0o700)
        before = self.link.readlink()
        result = self.run_earth()
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertFalse((self.root / ".state/totalmarker/map.lock.d").exists())
        self.assertEqual(self.link.readlink(), before)

    def test_switches_current_map_and_preserves_source_bytes(self):
        before = self.chosen.read_bytes()
        first = self.run_earth()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.link.readlink(), Path("../maps/world/" + self.filename))
        self.assertEqual(self.chosen.read_bytes(), before)
        self.assertIn("Earth map unchanged", self.run_earth().stdout)

    def test_preflight_unchanged_map_needs_no_write_permission(self):
        self.link.unlink()
        self.link.symlink_to('../maps/world/' + self.filename)
        images = self.root / 'images'
        command = ('project_root=' + shlex.quote(str(self.root)) +
                   '; script_dir=' + shlex.quote(str(self.root / 'scripts')) +
                   '; fail() { print -u2 -- "$*"; exit 2; }; ' +
                   'source "$script_dir/lib/xplanet/display.zsh"; select_earth_map --check')
        images.chmod(0o500)
        try:
            result = subprocess.run(['/bin/zsh', '-f', '-c', command],
                                    env={'PATH': f'{self.bin}:/usr/bin:/bin',
                                         'TEST_MONTH': f'{self.current:02d}'},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Earth map unchanged', result.stdout)
            self.assertFalse((self.root / '.state').exists())
        finally:
            images.chmod(0o700)

    def test_all_calendar_months_select_their_own_map(self):
        for month in range(1, 13):
            with self.subTest(month=month):
                filename = f"world.2004{month:02d}.3x5400x2700.png"
                image = self.root / "maps/world" / filename
                image.write_bytes(f"month {month}".encode())
                result = self.run_earth(month=month)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.link.readlink(), Path("../maps/world/" + filename))
                self.assertEqual(image.read_bytes(), f"month {month}".encode())

    def test_map_month_follows_local_calendar_at_utc_year_boundary(self):
        # 2024-01-01 00:30 UTC is still December on the US Pacific coast.
        for timezone, month in (("UTC", 1), ("America/Los_Angeles", 12)):
            with self.subTest(timezone=timezone):
                filename = f"world.2004{month:02d}.3x5400x2700.png"
                (self.root / "maps/world" / filename).write_bytes(b"boundary map")
                result = self.run_earth(timezone=timezone, epoch=1704069000)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.link.readlink(), Path("../maps/world/" + filename))

    def test_configured_topographic_pattern_and_missing_month(self):
        selected = self.root / "maps/world.topo.bathy"
        selected.mkdir()
        image = selected / f"world.topo.bathy.2004{self.current:02d}.3x5400x2700.png"
        image.write_bytes(b"bathy fixture")
        self.write_definition("world.topo.bathy/world.topo.bathy")
        done = self.run_earth()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.link.readlink(), Path("../maps/world.topo.bathy/" + image.name))
        image.unlink()
        missing = self.run_earth()
        self.assertEqual(missing.returncode, 2)
        self.assertIn("Monthly map is absent", missing.stderr)
        self.assertEqual(self.link.readlink(), Path("../maps/world.topo.bathy/" + image.name))

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
        folder = self.root / "maps/world"
        folder.rename(self.root / "maps/world.saved")
        folder.symlink_to(self.base)
        result = self.run_earth()
        self.assertEqual(result.returncode, 2)
        self.assertIn("real directory", result.stderr)

    def test_known_old_map_link_moves_to_current_layout_during_normal_selection(self):
        self.link.unlink();self.link.symlink_to('../assets/maps/world/world.200401.3x5400x2700.png')
        result=self.run_earth()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.link.readlink(),Path('../maps/world/'+self.filename))
        self.assertEqual(self.link.read_bytes(),b'selected map fixture')
        self.assertEqual(self.old.read_bytes(),b'old map fixture')

    def test_unknown_old_custom_map_link_is_not_silently_relocated(self):
        old='../assets/maps/bathymetry/custom.png'
        self.link.unlink();self.link.symlink_to(old)
        result=self.run_earth()
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('unrecognized old map link',result.stderr)
        self.assertEqual(str(self.link.readlink()),old)
