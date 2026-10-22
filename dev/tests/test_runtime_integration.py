"""Offline runtime-path contract; independent of copy-versus-link staging."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from .support import PROJECT, Sandbox, jpeg


CLOUD_DRIVER = """
import base64
import os
import sys
from unittest.mock import patch
from totalmarker.cli import main
from totalmarker.http import HTTPTransport, Response
body = base64.b64decode(os.environ["TM_TEST_JPEG"])
with patch.object(HTTPTransport, "request",
                  return_value=Response(200, {"content-type": "image/jpeg"}, body)) as request:
    status = main(["--root", sys.argv[1], "--config",
                   "config/totalmarker.toml", "clouds"])
    assert request.call_count == 1
raise SystemExit(status)
"""


def snapshot(path):
    return {
        str(p.relative_to(path)): (
            "link", os.readlink(p)
        ) if p.is_symlink() else (
            "file", p.read_bytes()
        ) if p.is_file() else ("dir", "")
        for p in path.rglob("*")
    }


class RuntimeFixture(Sandbox):
    def setUp(self):
        super().setUp()
        for name in ("config", "assets/maps", "images", "markers"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "config/totalmarker.toml").write_bytes(
            (PROJECT / "dev/examples/custom.example.toml").read_bytes())
        (self.root / "config/earth").write_text(
            '# User-selected cities and optional dates\n'
            '# 12 34 "A commented city"\n'
            '56 78 "A selected city" # 2020-06-23\n')
        (self.root / "config/xp.conf").write_text("cloud_map=clouds-4096.jpg\n")
        (self.root / "config/xp.def").write_text("XPLANET_HOME=fixture\n")
        (self.root / "assets/maps/earth.jpg").write_bytes(b"synthetic static map")
        (self.root / "images/earth.jpg").symlink_to("../assets/maps/earth.jpg")
        (self.root / "markers/earth").symlink_to("../config/earth")
        self.elsewhere = self.base / "unrelated-cwd"
        self.elsewhere.mkdir()
        tmp = self.base / "temp"
        tmp.mkdir()
        self.env = os.environ.copy()
        self.env.update({
            "PYTHONPATH": str(PROJECT / "scripts"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(tmp),
            "XDG_CACHE_HOME": str(tmp / "cache"),
            "TM_TEST_JPEG": base64.b64encode(jpeg(width=4096)).decode(),
        })

    def command(self, argv):
        return subprocess.run(
            [sys.executable, "-B", *argv], cwd=self.elsewhere,
            env=self.env, text=True, capture_output=True, timeout=10)

class RuntimePathIntegrationTests(RuntimeFixture):
    def test_single_source_launcher_help_from_unrelated_directory(self):
        launcher = PROJECT / "scripts/run-totalmarker"
        environment = {**self.env, "PYTHONPATH": ""}
        result = subprocess.run(
            [str(launcher), "--help"], cwd=self.elsewhere,
            env=environment, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("clouds", result.stdout)
        self.assertIn("labels", result.stdout)
        self.assertTrue((PROJECT / "scripts/totalmarker/__main__.py").is_file())
        self.assertFalse((PROJECT / "totalmarker").exists())
        self.assertFalse((PROJECT / "runtime").exists())

    def test_cloud_and_label_commands_obey_agreed_root_layout(self):
        input_before = snapshot(self.root / "config")
        asset_before = snapshot(self.root / "assets")
        map_link = os.readlink(self.root / "images/earth.jpg")
        city_link = os.readlink(self.root / "markers/earth")
        cloud = self.command(["-c", CLOUD_DRIVER, str(self.root)])
        self.assertEqual(cloud.returncode, 0, cloud.stderr + cloud.stdout)
        self.assertEqual(json.loads(cloud.stdout)["outcome"], "changed")
        image = self.root / "images/clouds-4096.jpg"
        self.assertTrue(image.is_file())
        self.assertFalse(image.is_symlink())
        self.assertEqual(image.read_bytes(), jpeg(width=4096))
        label = self.root / "markers/updatelabel"
        self.assertIn('-53 -12 "Cloud Map Last Updated', label.read_text())
        before_label = label.read_bytes()
        labels = self.command([
            "-m", "totalmarker", "--root", str(self.root),
            "--config", "config/totalmarker.toml", "labels"])
        self.assertEqual(labels.returncode, 0, labels.stderr + labels.stdout)
        self.assertEqual(json.loads(labels.stdout)["outcome"], "unchanged")
        self.assertEqual(label.read_bytes(), before_label)
        self.assertEqual(snapshot(self.root / "config"), input_before)
        self.assertEqual(snapshot(self.root / "assets"), asset_before)
        self.assertEqual(os.readlink(self.root / "images/earth.jpg"), map_link)
        self.assertEqual(os.readlink(self.root / "markers/earth"), city_link)
        self.assertEqual((self.root / "markers/earth").read_text(),
                         (self.root / "config/earth").read_text())
        self.assertTrue((self.root / ".state/totalmarker/state.json").is_file())
        self.assertTrue((self.root / ".state/totalmarker/job.lock").is_file())
        self.assertFalse((self.root / ".state/totalmarker/pending.json").exists())
        self.assertEqual(
            len((self.root / "logs/totalmarker/events.jsonl").read_text().splitlines()), 2)
        self.assertFalse((self.root / "config/.state").exists())
        self.assertFalse((self.root / "config/logs").exists())


QUAKE_DRIVER = """
import sys
from pathlib import Path
from unittest.mock import patch
from totalmarker.cli import main
from totalmarker.http import Fetcher, HTTPTransport, Response
from tests.support import ScriptedTransport
body = Path(sys.argv[2]).read_bytes()
transport = ScriptedTransport(Response(200, {"content-type": "application/geo+json"}, body))
with (patch("totalmarker.features.quake.Fetcher", return_value=Fetcher(transport)),
      patch.object(HTTPTransport, "request", side_effect=AssertionError("network used"))):
    status = main(["--root", sys.argv[1], "--config", "config/totalmarker.toml", "quake"])
assert len(transport.calls) == 1
raise SystemExit(status)
"""


STORM_DRIVER = """
import sys
from unittest.mock import patch
from totalmarker.cli import main
from totalmarker.http import HTTPTransport
from tests.test_storm_sources import MappedFetcher, JTWC, LIVE_ABIO, LIVE_NOW
fetcher = MappedFetcher()
fetcher.payloads[JTWC + "abioweb.txt"] = LIVE_ABIO.read_bytes()
with (patch("totalmarker.features.storm.Fetcher", return_value=fetcher),
      patch("totalmarker.features.storm.time.time", return_value=LIVE_NOW),
      patch.object(HTTPTransport, "request", side_effect=AssertionError("network used"))):
    status = main(["--root", sys.argv[1], "--config", "config/totalmarker.toml", "storm"])
assert len(fetcher.calls) >= 4
raise SystemExit(status)
"""


class ProductCliIntegrationTests(RuntimeFixture):
    def setUp(self):
        super().setUp()
        self.env["PYTHONPATH"] = os.pathsep.join((str(PROJECT / "scripts"),
                                                    str(PROJECT / "dev")))

    def test_quake_cli_uses_fixture_transport_from_unrelated_directory(self):
        fixture = PROJECT / "dev/tests/fixtures/usgs_quake_selected_20261019.geojson"
        before_config = snapshot(self.root / "config")
        result = self.command(["-c", QUAKE_DRIVER, str(self.root), str(fixture)])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["count"], 5)
        self.assertIn(b'"6.0"', (self.root / "markers/quake").read_bytes())
        self.assertIn('Earthquake Information Last Updated',
                      (self.root / "markers/updatelabel").read_text())
        self.assertEqual(snapshot(self.root / "config"), before_config)

    def test_storm_cli_uses_fixture_transport_from_unrelated_directory(self):
        before_config = snapshot(self.root / "config")
        result = self.command(["-c", STORM_DRIVER, str(self.root)])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["count"], 4)
        marker = (self.root / "markers/storm").read_text()
        arc = (self.root / "arcs/storm").read_text()
        self.assertIn('"Invest 93S"', marker)
        self.assertIn('"Champi"', marker)
        self.assertIn('color=Blue', arc)
        self.assertIn('color=SkyBlue', arc)
        self.assertIn('Storm Information Last Updated',
                      (self.root / "markers/updatelabel").read_text())
        self.assertEqual(snapshot(self.root / "config"), before_config)
