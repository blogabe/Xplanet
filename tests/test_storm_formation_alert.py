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
from .support_storm import JTWC, formation_fetcher


LIVE = Path(__file__).parent / "fixtures/storm/live-20261020"
NOW = datetime(2026, 10, 20, 6, 5, tzinfo=timezone.utc).timestamp()


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
        snapshot = collect_snapshot(formation_fetcher(), now=NOW)
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
        fetcher = formation_fetcher()
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
                                                        fetcher=formation_fetcher(), now=NOW)):
            with redirect_stdout(output):
                status = cli_main(["--root", str(self.root), "--config", "config.ini", "storm"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "changed")
        settings = self.config("StormCheckIntervalSeconds=0\n")
        original = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        bad = formation_fetcher()
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
        first = run(self.fs, settings, fetcher=formation_fetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        saved = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                 self.fs.read(settings.labels))
        invalid = formation_fetcher()
        path = JTWC + "sh9327web.txt"
        invalid.payloads[path] = invalid.payloads[path].replace(
            b"IS NOW LOCATED NEAR 3.9S 55.5E", b"IS NOW LOCATED NEAR 4.9S 55.5E")
        failed = run(self.fs, settings, fetcher=invalid, now=NOW + 60)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("conflicting same-time position", failed.message)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                          self.fs.read(settings.labels)), saved)
        different_suffix = formation_fetcher()
        path = JTWC + "sh9327web.txt"
        different_suffix.payloads[path] = (different_suffix.payloads[path]
                                           .replace(b"WTXS21", b"WTPS21")
                                           .replace(b"93S", b"93P"))
        failed = run(self.fs, settings, fetcher=different_suffix, now=NOW + 90)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("has a different advisory invest code", failed.message)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                          self.fs.read(settings.labels)), saved)
        older_advisory = formation_fetcher()
        older_advisory.payloads[path] = older_advisory.payloads[path].replace(
            b"WTXS21 PGTW 192000", b"WTXS21 PGTW 200000")
        failed = run(self.fs, settings, fetcher=older_advisory, now=NOW + 100)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("is newer than ABIO advisory fix", failed.message)
        self.assertIn("SH932027 (93S)", failed.message)
        self.assertIn("2026-10-20T00:00:00+00:00 > 2026-10-19T20:00:00+00:00", failed.message)
        missing = formation_fetcher()
        path = JTWC + "abioweb.txt"
        missing.payloads[path] = missing.payloads[path].replace(b"INVEST 93S", b"INVEST 94S")
        failed = run(self.fs, settings, fetcher=missing, now=NOW + 120)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("has no active advisory invest", failed.message)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc),
                          self.fs.read(settings.labels)), saved)
        bad_advisory = (LIVE / "jtwc-abpw-advisory.txt").read_bytes().replace(
            b"PACIFIC OCEANS/200600Z", b"INDIAN OCEAN/200600Z")
        with self.assertRaises(FeedError):
            parse_advisory(bad_advisory, "abpw")


class TracklessFormationAlertTests(Sandbox):
    """Authentic 96S TCFA without a KMZ alongside two tracked cyclone warnings."""

    capture = Path(__file__).parent / 'fixtures/storm/live-20261118-tcfa'
    at = datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc).timestamp()

    def packet(self):
        from .support_storm import ReceiptPacket
        return ReceiptPacket(self.capture)

    def test_captured_packet_integrity_and_complete_snapshot(self):
        packet = self.packet()
        packet.assert_integrity(self)
        products, _, _ = parse_jtwc_rss(packet.payloads[JTWC_RSS])
        alert = next(p for p in products if p.kind == 'formation_alert')
        self.assertEqual(alert.identity, 'SH962027')
        self.assertIsNone(alert.kmz_url)
        snapshot = collect_snapshot(packet, now=self.at)
        self.assertEqual({s.id for s in snapshot.storms},
                         {'IO052026', 'SH042027', 'SH962027'})
        for storm in snapshot.storms:
            if storm.id == alert.identity:
                self.assertEqual((storm.current.lat, storm.current.lon), (-5.6, 90.2))
                self.assertEqual((storm.history, storm.forecast, storm.forecast_status),
                                 ((), (), 'not_issued'))
            else:
                self.assertTrue(storm.history)
                self.assertTrue(storm.forecast)
                self.assertEqual(storm.forecast_status, 'issued')
        self.assertEqual(set(packet.calls), set(packet.payloads))
        self.assertFalse(any(url.endswith('sh9627.kmz') for url in packet.calls))

    def test_numbered_warnings_still_require_their_own_kmz(self):
        raw = self.packet().payloads[JTWC_RSS]
        for name in (b'io0526.kmz', b'sh0427.kmz'):
            with self.subTest(product=name):
                changed = raw.replace(name, b'unrelated.kmz')
                self.assertNotEqual(raw, changed)
                with self.assertRaisesRegex(FeedError, 'warning lacks a KMZ track'):
                    parse_jtwc_rss(changed)
        with self.assertRaisesRegex(FeedError, 'product type is ambiguous'):
            parse_jtwc_rss(raw.replace(b'TCFA Text', b'Unknown Text'))

    def test_subject_spacing_does_not_weaken_identity_validation(self):
        raw = self.packet().payloads[JTWC + 'sh9627web.txt']
        self.assertIn(b'ALERT(INVEST 96S)', raw)
        for spacing in (b'', b' ', b'  ', b'\t'):
            with self.subTest(spacing=spacing):
                point, code = parse_jtwc_formation_alert(
                    raw.replace(b'ALERT(INVEST', b'ALERT' + spacing + b'(INVEST'),
                    'SH962027', self.at)
                self.assertEqual((point.lat, point.lon, code), (-5.6, 90.2, '96S'))
        for changed in (
            raw.replace(b'(INVEST 96S)', b'(INVEST 95S)', 1),
            raw.replace(b'(INVEST 96S)', b'(INVEST 96W)', 1),
            raw.replace(b'ALERT(INVEST', b'ALERT EXTRA(INVEST'),
            raw.replace(b'ALERT(INVEST', b'ALERT\n(INVEST'),
            raw.replace(b'ALERT(INVEST', b'ALERT( INVEST'),
        ):
            with self.subTest(subject=changed.splitlines()[2]):
                with self.assertRaises(FeedError):
                    parse_jtwc_formation_alert(changed, 'SH962027', self.at)

    def test_failed_refresh_preserves_last_good_tracked_publication(self):
        settings = self.config('StormCheckIntervalSeconds=0\n')
        result = run(self.fs, settings, fetcher=self.packet(), now=self.at)
        self.assertEqual((result.outcome, result.count), ('changed', 3), result.message)
        paths = (settings.storm.marker, settings.storm.arc, settings.labels)
        previous = [self.fs.read(path) for path in paths]
        for failure in ('missing_warning_track', 'conflicting_invest', 'stale'):
            packet = self.packet()
            if failure == 'missing_warning_track':
                packet.payloads[JTWC_RSS] = packet.payloads[JTWC_RSS].replace(
                    b'io0526.kmz', b'unrelated.kmz')
            elif failure == 'conflicting_invest':
                url = JTWC + 'sh9627web.txt'
                packet.payloads[url] = packet.payloads[url].replace(
                    b'IS NOW LOCATED NEAR 5.6S', b'IS NOW LOCATED NEAR 6.6S')
            at = self.at + (48 * 3600 if failure == 'stale' else 1)
            with self.subTest(failure=failure):
                failed = run(self.fs, settings, fetcher=packet, now=at)
                self.assertEqual(failed.outcome, 'failed')
                self.assertEqual([self.fs.read(path) for path in paths[:2]], previous[:2])
                if failure != 'stale':
                    self.assertEqual(self.fs.read(settings.labels), previous[2])
                else:
                    self.assertIn(b'color=Red', self.fs.read(settings.labels))


if __name__ == "__main__":
    import unittest
    unittest.main()
