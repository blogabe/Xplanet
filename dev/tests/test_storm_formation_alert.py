"""Captured JTWC TCFA and advisory layout from 2026-10-20, tested offline."""

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from totalmarker.cli import main as cli_main
from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.storm_advisory import parse_advisory
from totalmarker.storm_model import render_bodies, StormStyle
from totalmarker.storm_sources import (JTWC_RSS, REQUIRED_GROUPS, collect_snapshot,
                                       parse_jtwc_formation_alert, parse_jtwc_rss,
                                       parse_jtwc_warning)
from .support import Sandbox
from .test_storm_sources import JTWC, MappedFetcher


LIVE = Path(__file__).parent / "fixtures/storm/live-20261020"
NOW = datetime(2026, 10, 20, 6, 5, tzinfo=timezone.utc).timestamp()


def live_fetcher():
    fetcher = MappedFetcher()
    for url, name in (
        (JTWC_RSS, "jtwc-rss.xml"),
        (JTWC + "wp2926web.txt", "wp292026-warning.txt"),
        (JTWC + "sh9327web.txt", "sh932027-warning.txt"),
        (JTWC + "abpwweb.txt", "jtwc-abpw-advisory.txt"),
        (JTWC + "abioweb.txt", "jtwc-abio-advisory.txt"),
    ):
        fetcher.payloads[url] = (LIVE / name).read_bytes()
    return fetcher


class FormationAlertTests(Sandbox):
    def test_captured_response_provenance_and_complete_snapshot(self):
        manifest = json.loads((LIVE / "manifest.json").read_text())
        for record in manifest["records"]:
            with self.subTest(path=record["path"]):
                data = (LIVE / record["path"]).read_bytes()
                self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                                 (record["bytes"], record["sha256"]))
        products, times, _ = parse_jtwc_rss((LIVE / "jtwc-rss.xml").read_bytes())
        self.assertEqual([(p.identity, p.kind) for p in products],
                         [("WP292026", "warning"), ("SH932027", "formation_alert")])
        with self.assertRaisesRegex(FeedError, "product type is ambiguous"):
            parse_jtwc_rss((LIVE / "jtwc-rss.xml").read_bytes().replace(
                b"TCFA Text", b"Unknown Text"))
        current, name, _, forecasts, code = parse_jtwc_warning(
            (LIVE / "wp292026-warning.txt").read_bytes(), "WP292026", times["jtwc_west"])
        self.assertEqual((name, code, current.lat, current.lon, len(forecasts)),
                         ("Champi", "29W", 15.9, 135.6, 8))
        alert, code = parse_jtwc_formation_alert(
            (LIVE / "sh932027-warning.txt").read_bytes(),
            "SH932027", times["jtwc_south"])
        self.assertEqual((code, alert.lat, alert.lon), ("93S", -3.9, 55.5))
        abio = parse_advisory((LIVE / "jtwc-abio-advisory.txt").read_bytes(), "abio")
        abpw = parse_advisory((LIVE / "jtwc-abpw-advisory.txt").read_bytes(), "abpw")
        self.assertEqual([(s.id, s.current.lat, s.current.lon) for s in abio.invests],
                         [("SH932027", -3.9, 55.5)])
        self.assertEqual([code for area in abpw.areas for code in area.warned_codes],
                         ["29W"])
        snapshot = collect_snapshot(live_fetcher(), now=NOW)
        self.assertEqual([storm.id for storm in snapshot.storms],
                         ["EP212026", "WP292026", "SH932027"])
        marker, arc = render_bodies(snapshot, StormStyle(), required_groups=REQUIRED_GROUPS)
        self.assertIn(b'"Invest 93S"', marker)
        self.assertNotIn(b'"Invest 93S"', arc)

    def test_formation_alert_identity_basin_and_current_position_are_strict(self):
        rss_at = NOW
        for identity, code, header in (("WP942026", "94W", "WTPN21"),
                                       ("IO962026", "96A", "WTIO21"),
                                       ("IO962026", "96B", "WTIO21"),
                                       ("SH932027", "93S", "WTXS21")):
            with self.subTest(identity=identity):
                body = (f"{header} PGTW 200600\n"
                        f"SUBJ/TROPICAL CYCLONE FORMATION ALERT (INVEST {code})//\n"
                        f"RMKS/INVEST {code} IS NOW LOCATED NEAR 7.2N 143.0E\n").encode()
                current, parsed = parse_jtwc_formation_alert(body, identity, rss_at)
                self.assertEqual((parsed, current.lat, current.lon), (code, 7.2, 143.0))
                with self.assertRaises(FeedError):
                    parse_jtwc_formation_alert(body.replace(b"IS NOW LOCATED NEAR",
                                                            b"WAS PREVIOUSLY NEAR"),
                                               identity, rss_at)

    def test_newer_advisory_fix_supersedes_alert_without_invented_track(self):
        fetcher = live_fetcher()
        path = JTWC + "abioweb.txt"
        fetcher.payloads[path] = (fetcher.payloads[path]
                                  .replace(b"ABIO10 PGTW 192000", b"ABIO10 PGTW 200600")
                                  .replace(b"REISSUED/192000Z-201800ZOCT2026",
                                           b"REISSUED/200600Z-210600ZOCT2026")
                                  .replace(b"IS NOW LOCATED NEAR 3.9S 55.5E",
                                           b"IS NOW LOCATED NEAR 4.0S 55.5E"))
        snapshot = collect_snapshot(fetcher, now=NOW)
        invest = next(storm for storm in snapshot.storms if storm.id == "SH932027")
        self.assertEqual((invest.name, invest.current.at, invest.current.lat,
                          invest.current.lon),
                         ("Invest 93S", datetime(2026, 10, 20, 6,
                                                 tzinfo=timezone.utc).timestamp(), -4.0, 55.5))
        self.assertEqual((invest.history, invest.forecast), ((), ()))

    def test_offline_cli_reports_captured_success_and_failure_truthfully(self):
        self.config("StormCheckIntervalSeconds=0\n")
        output = io.StringIO()
        with patch("totalmarker.cli.run_storm",
                   side_effect=lambda fs, settings: run(fs, settings,
                                                        fetcher=live_fetcher(), now=NOW)):
            with redirect_stdout(output):
                status = cli_main(["--root", str(self.root), "--config", "config.ini", "storm"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "changed")
        settings = self.config("StormCheckIntervalSeconds=0\n")
        original = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        bad = live_fetcher()
        path = JTWC + "sh9327web.txt"
        bad.payloads[path] = bad.payloads[path].replace(
            b"IS NOW LOCATED NEAR 3.9S 55.5E", b"IS NOW LOCATED NEAR 4.9S 55.5E")
        output = io.StringIO()
        with patch("totalmarker.cli.run_storm",
                   side_effect=lambda fs, settings: run(fs, settings,
                                                        fetcher=bad, now=NOW + 60)):
            with redirect_stdout(output):
                status = cli_main(["--root", str(self.root), "--config", "config.ini", "storm"])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "failed")
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)),
                         original)

    def test_mismatch_or_ambiguous_source_preserves_last_good_publication(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=live_fetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        saved = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                 self.fs.read(settings.labels))
        invalid = live_fetcher()
        path = JTWC + "sh9327web.txt"
        invalid.payloads[path] = invalid.payloads[path].replace(
            b"IS NOW LOCATED NEAR 3.9S 55.5E", b"IS NOW LOCATED NEAR 4.9S 55.5E")
        failed = run(self.fs, settings, fetcher=invalid, now=NOW + 60)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("formation alert disagrees", failed.message)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                          self.fs.read(settings.labels)), saved)
        different_suffix = live_fetcher()
        path = JTWC + "sh9327web.txt"
        different_suffix.payloads[path] = (different_suffix.payloads[path]
                                           .replace(b"WTXS21", b"WTPS21")
                                           .replace(b"93S", b"93P"))
        failed = run(self.fs, settings, fetcher=different_suffix, now=NOW + 90)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("formation alert disagrees", failed.message)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                          self.fs.read(settings.labels)), saved)
        older_advisory = live_fetcher()
        older_advisory.payloads[path] = older_advisory.payloads[path].replace(
            b"WTXS21 PGTW 192000", b"WTXS21 PGTW 200000")
        failed = run(self.fs, settings, fetcher=older_advisory, now=NOW + 100)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("formation alert disagrees", failed.message)
        missing = live_fetcher()
        path = JTWC + "abioweb.txt"
        missing.payloads[path] = missing.payloads[path].replace(b"INVEST 93S", b"INVEST 94S")
        failed = run(self.fs, settings, fetcher=missing, now=NOW + 120)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("formation alert disagrees", failed.message)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                          self.fs.read(settings.labels)), saved)
        bad_advisory = (LIVE / "jtwc-abpw-advisory.txt").read_bytes().replace(
            b"PACIFIC OCEANS/200600Z", b"INDIAN OCEAN/200600Z")
        with self.assertRaises(FeedError):
            parse_advisory(bad_advisory, "abpw")


if __name__ == "__main__":
    import unittest
    unittest.main()
