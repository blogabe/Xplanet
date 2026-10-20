"""Archived JTWC North Indian prose warning: source facts and isolated output."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from totalmarker.features.storm import run
from totalmarker.storm_model import Storm, StormSnapshot
from totalmarker.storm_sources import parse_jtwc_warning, REQUIRED_GROUPS
from .support import Sandbox

FIXTURE = Path(__file__).parent / "fixtures/storm/jtwc-io07b-warning-20231117-0300.txt"
SOURCE = FIXTURE.with_suffix(".source.json")
ISSUE = datetime(2023, 11, 17, 3, tzinfo=timezone.utc).timestamp()
ANALYSIS = datetime(2023, 11, 17, 0, tzinfo=timezone.utc).timestamp()


class ArchivedNorthIndianWarningTests(Sandbox):
    def bulletin(self):
        body = FIXTURE.read_bytes()
        manifest = json.loads(SOURCE.read_text())
        self.assertEqual(manifest["source_url"],
                         "https://www.gdacs.org/gts.aspx?eventid=1001034&eventtype=TC")
        self.assertEqual(manifest["bulletin"], "WTIO31 PGTW 170300")
        self.assertEqual(manifest["fixture_bytes"], len(body))
        self.assertEqual(manifest["fixture_sha256"], hashlib.sha256(body).hexdigest())
        return body

    def test_archived_bulletin_analysis_forecasts_and_remarks_are_distinct(self):
        body = self.bulletin()
        self.assertTrue(body.startswith(b"WTIO31 PGTW 170300\n"))
        self.assertIn(b"SUBJ/TROPICAL CYCLONE 07B (SEVEN) WARNING NR 002//", body)
        self.assertIn(b"170000Z --- NEAR 20.3N 88.9E", body)
        self.assertIn(b"171200Z --- 21.9N 90.2E\n   MAX SUSTAINED WINDS - 035 KT", body)
        self.assertIn(b"180000Z --- 23.1N 91.1E\n   MAX SUSTAINED WINDS - 025 KT", body)
        self.assertIn(b"170300Z POSITION NEAR 20.7N 89.2E", body)
        current, name, wind, forecast, code = parse_jtwc_warning(body, "IO072023", ISSUE)
        self.assertEqual((current.at, current.lat, current.lon), (ANALYSIS, 20.3, 88.9))
        self.assertEqual((name, wind, code), ("Seven", 35, "07B"))
        self.assertEqual([(point.lead_hours, point.at, point.lat, point.lon)
                          for point in forecast],
                         [(12, ANALYSIS + 12 * 3600, 21.9, 90.2),
                          (24, ANALYSIS + 24 * 3600, 23.1, 91.1)])

    def test_archived_warning_parses_through_isolated_marker_arc_publication(self):
        current, name, wind, forecast, _ = parse_jtwc_warning(
            self.bulletin(), "IO072023", ISSUE)
        storm = Storm("IO072023", name, "STO", current, wind, (),
                      current, forecast, "issued")
        # Other region times are fixture scaffolding for the publication path,
        # not evidence that those regions had complete feeds in November 2023.
        snapshot = StormSnapshot((storm,), tuple((group, ISSUE)
                                                 for group in sorted(REQUIRED_GROUPS)), True)
        settings = self.config("StormCheckIntervalSeconds=0\n")
        with patch("totalmarker.features.storm.collect_snapshot", return_value=snapshot):
            result = run(self.fs, settings, fetcher=object(), now=ISSUE)
        self.assertEqual((result.outcome, result.count), ("changed", 1))
        marker = self.fs.read(settings.storm.marker).decode()
        arc = self.fs.read(settings.storm.arc).decode()
        self.assertIn('  20.30   88.90 "Seven"', marker)
        self.assertIn('  20.30   88.90   21.90   90.20 color=SkyBlue', arc)
        self.assertIn('  21.90   90.20   23.10   91.10 color=SkyBlue', arc)
        self.assertNotIn('  20.70   89.20', marker + arc)
        self.assertIn("Storm Infomation Last Updated", self.fs.read(settings.labels).decode())
