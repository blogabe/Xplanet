import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from datetime import datetime
import os
import zlib

from totalmarker.config import load_bytes
from totalmarker.errors import DownloadError, FeedError, StorageError
from totalmarker.features import aurora, clouds
from totalmarker.http import Response
from totalmarker.health import check
from totalmarker.labels import legacy_time
from totalmarker.paths import RootFS

NOW = datetime.fromisoformat("2026-11-25T03:00:00Z").timestamp()


def data():
    return {"Observation Time": "2026-11-25T02:51:00Z",
            "Forecast Time": "2026-11-25T04:13:00Z",
            "Data Format": "[Longitude, Latitude, Aurora]",
            "coordinates": [[x, y, 21 if y == 65 and 170 <= x <= 190 else 0]
                            for x in range(360) for y in range(-90, 91)]}


class AuroraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.dumps(data()).encode()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.fs = RootFS(self.root)
        (self.root / 'images').mkdir()
        (self.root / 'maps').mkdir()
        self.base = self.root / 'maps' / 'base.tiff'
        self.base.write_bytes(b'pristine example map')
        self.selector = self.root / 'images' / 'selected'
        self.selector.symlink_to('../maps/base.tiff')
        self.fetcher = Mock()
        self.fetcher.fetch.return_value = Response(200, {}, self.raw)
        self.compositor = Mock(side_effect=lambda base, overlay: overlay)
        self.config = load_bytes(self.fs, b'[aurora]\nenabled=true\nbase_night_map="images/selected"\n', 'config/a.toml')

    def refresh(self, **kwargs):
        return aurora.run(self.fs, kwargs.pop('settings', self.config),
                          now=kwargs.pop('now', NOW), fetcher=self.fetcher,
                          compositor=self.compositor, **kwargs)

    def test_wrapped_grid_and_transparent_background(self):
        frame = aurora.parse(self.raw, NOW)
        png = aurora.encode(frame)
        pos = 8
        while png[pos+4:pos+8] != b'IDAT':
            pos += 12 + int.from_bytes(png[pos:pos+4], 'big')
        length = int.from_bytes(png[pos:pos+4], 'big')
        rows = zlib.decompress(png[pos+8:pos+8+length])
        stride = 1 + 4 * aurora.WIDTH
        y = 99  # near 65 N; arc crosses the antimeridian
        self.assertGreater(rows[y*stride+4], 0)
        self.assertGreater(rows[(y+1)*stride-1], 0)
        self.assertEqual(rows[y*stride+4+4*(aurora.WIDTH//2)], 0)
        self.assertFalse(any(rows[300*stride:410*stride]))

    def test_duplicate_incomplete_and_stale_reports_rejected(self):
        for failure in ('duplicate', 'incomplete', 'expired', 'lead', 'future', 'bool', 'shape'):
            doc = data()
            if failure == 'duplicate':
                doc['coordinates'][0] = doc['coordinates'][1]
            if failure == 'incomplete':
                doc['coordinates'].pop()
            if failure == 'expired':
                doc['Observation Time'] = doc['Forecast Time'] = "2026-11-24T22:00:00Z"
            if failure == 'lead':
                doc['Forecast Time'] = "2026-11-25T09:00:00Z"
            if failure == 'future':
                doc['Observation Time'] = "2026-11-25T03:30:00Z"
            if failure == 'bool':
                doc['coordinates'][0][2] = True
            if failure == 'shape':
                doc['coordinates'][0].append(1)
            with self.subTest(failure=failure), self.assertRaises(FeedError):
                aurora.parse(json.dumps(doc).encode(), NOW)

    def test_headless_does_not_inspect_or_use_base(self):
        self.selector.unlink()
        r = self.refresh(overlay_only=True)
        self.assertEqual(r['outcome'], 'changed')
        self.assertTrue((self.root / aurora.OVERLAY).is_file())
        self.assertFalse((self.root / aurora.CURRENT).exists())
        self.compositor.assert_not_called()

    def test_prepare_refresh_base_swap_disable_and_expiry(self):
        self.assertEqual(self.refresh(prepare=True)['outcome'], 'ready')
        current = self.root / aurora.CURRENT
        self.assertEqual(current.readlink(), self.selector)
        self.fetcher.fetch.assert_not_called()
        self.assertEqual(self.refresh()['outcome'], 'changed')
        self.assertEqual(current.readlink(), self.root / aurora.COMPOSITE)
        self.assertEqual(self.base.read_bytes(), b'pristine example map')
        selected2 = self.root / 'maps' / 'other.png'
        selected2.write_bytes(b'another pristine map')
        self.selector.unlink()
        self.selector.symlink_to('../maps/other.png')
        self.refresh(prepare=True)
        self.assertEqual(current.resolve(), selected2)
        self.refresh(now=NOW+10)
        self.assertEqual(current.readlink(), self.root / aurora.COMPOSITE)
        self.assertEqual(self.compositor.call_args.args[0], b'another pristine map')
        self.assertEqual(self.fetcher.fetch.call_count, 1)
        self.fetcher.fetch.side_effect = DownloadError('NOAA unavailable')
        self.assertEqual(self.refresh(now=NOW+60*120)['outcome'], 'failed')
        self.assertEqual(current.resolve(), selected2)
        disabled = load_bytes(self.fs, b'[aurora]\nenabled=false\nbase_night_map="images/selected"\n', 'a.toml')
        self.assertEqual(self.refresh(settings=disabled)['outcome'], 'disabled')
        self.assertEqual(self.fetcher.fetch.call_count, 2)
        self.assertEqual(os.readlink(self.selector), '../maps/other.png')

    def test_refuses_overwrite_or_base_cycle(self):
        current = self.root / aurora.CURRENT
        current.parent.mkdir(parents=True)
        current.write_text('leave me alone')
        with self.assertRaises(StorageError):
            self.refresh(prepare=True)
        self.assertEqual(current.read_text(), 'leave me alone')
        self.fetcher.fetch.assert_not_called()

    def test_existing_config_without_aurora_is_off(self):
        settings = load_bytes(self.fs, b'', 'legacy.ini')
        self.assertFalse(settings.aurora.enabled)
        self.assertEqual(self.refresh(settings=settings)['outcome'], 'disabled')
        self.fetcher.fetch.assert_not_called()

    def test_saved_health_tracks_forecast_without_network(self):
        self.refresh(overlay_only=True)
        current = check(self.fs, self.config, now=NOW)
        later = check(self.fs, self.config, now=NOW+120*60)
        row = next(r for r in current["products"] if r["product"] == "aurora")
        self.assertEqual(row["freshness"], "current")
        self.assertTrue(row["output"]["verified"])
        row = next(r for r in later["products"] if r["product"] == "aurora")
        self.assertEqual(row["status"], "stale")
        self.assertEqual(self.fetcher.fetch.call_count, 1)

    def test_desktop_label_tracks_quiet_forecast_and_expires_without_an_aurora_fetch(self):
        cloud = '-53 -13 "Cloud Map Last Updated UNKNOWN" color=Red image=none position=pixel\n'
        quake = '-68 -13 "Earthquake Information Last Updated UNKNOWN" color=Red image=none position=pixel\n'
        personal = '-113 -74 "Personal marker" image=none position=pixel\n'
        self.fs.write(self.config.labels, (cloud + quake + personal).encode())
        quiet = data()
        for point in quiet["coordinates"]:
            point[2] = 0
        self.fetcher.fetch.return_value = Response(200, {}, json.dumps(quiet).encode())
        first = self.refresh()
        self.assertEqual(first["outcome"], "changed")
        name = f'Aurora Forecast Valid Until {legacy_time(first["expires_at"])}'
        green = f'-68 -13 "{name}" color=Green image=none position=pixel\n'
        expected = cloud + green + quake.replace("-68", "-83", 1) + personal
        self.assertEqual(self.fs.read(self.config.labels).decode(), expected)
        self.fetcher.fetch.side_effect = DownloadError("NOAA unavailable")
        self.assertEqual(self.refresh(now=NOW+300)["outcome"], "failed")
        self.assertEqual(self.fs.read(self.config.labels).decode(), expected)
        clouds.run(self.fs, self.config, label_only=True, now=first["expires_at"])
        self.assertIn(green.replace("Green", "Yellow"), self.fs.read(self.config.labels).decode())
        self.assertEqual(self.fetcher.fetch.call_count, 2)
        off = load_bytes(self.fs, b'[aurora]\nenabled=false\nbase_night_map="images/selected"\n', 'a.toml')
        self.assertEqual(self.refresh(settings=off, prepare=True)["outcome"], "disabled")
        self.assertEqual(self.fs.read(self.config.labels).decode(), expected.replace(green, ""))

    def test_unknown_forecast_keeps_custom_label_coordinates_and_headless_leaves_labels_alone(self):
        initial = ('-53 -13 "Cloud Map Last Updated UNKNOWN" color=Red image=none position=pixel\n'
                   '-68 -20 "Custom annotation" color=Green position=pixel\n')
        self.fs.write(self.config.labels, initial.encode())
        self.refresh(overlay_only=True)
        self.assertEqual(self.fs.read(self.config.labels).decode(), initial)
        (self.root / aurora.OVERLAY).unlink()
        self.fetcher.fetch.side_effect = DownloadError("NOAA unavailable")
        self.assertEqual(self.refresh()["outcome"], "failed")
        rows = self.fs.read(self.config.labels).decode().splitlines()
        self.assertEqual(rows[0], initial.splitlines()[0])
        self.assertEqual(rows[2], initial.splitlines()[1])
        self.assertEqual(rows[1], '-83 -13 "Aurora Forecast Valid Until UNKNOWN" '
                                  'color=Red image=none position=pixel')

    def test_later_cloud_row_puts_aurora_below_it_without_duplicate_rows(self):
        self.refresh()
        original = self.fs.read(self.config.labels).decode()
        self.assertTrue(original.startswith('-53 -13 "Aurora'))
        clouds.run(self.fs, self.config, label_only=True, now=NOW)
        lines = self.fs.read(self.config.labels).decode().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("Cloud Map", lines[0])
        self.assertIn("Aurora Forecast", lines[1])
        self.assertGreater(int(lines[0].split()[0]), int(lines[1].split()[0]))

    def test_compositor_error_selects_base(self):
        self.compositor.side_effect = FeedError('test image failure')
        self.assertEqual(self.refresh()['outcome'], 'failed')
        self.assertEqual((self.root / aurora.CURRENT).readlink(), self.selector)
        self.assertFalse((self.root / aurora.COMPOSITE).exists())
