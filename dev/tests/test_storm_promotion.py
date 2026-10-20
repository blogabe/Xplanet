"""Captured official JTWC invest-to-warning transition, tested without live feeds."""
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

from totalmarker.cli import main as cli_main
from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.http import Response
from totalmarker.storm_advisory import parse_advisory
from totalmarker.storm_sources import collect_snapshot, parse_jtwc_rss
from .support import Sandbox
from .test_storm_formation_alert import live_fetcher


CAPTURE = Path(__file__).parent / "fixtures/storm/live-20261020-promotion"
EARLIER = Path(__file__).parent / "fixtures/storm/live-20261020"
NOW = datetime(2026, 10, 20, 16, 5, tzinfo=timezone.utc).timestamp()
EARLIER_AT = datetime(2026, 10, 20, 6, 5, tzinfo=timezone.utc).timestamp()


class CapturedFetcher:
    def __init__(self, *, advisory=None, abpw=None):
        records = json.loads((CAPTURE / "manifest.json").read_text())["records"]
        self.responses = {record["url"]: record for record in records}
        self.advisory = advisory
        self.abpw = abpw
        self.calls = []

    def fetch(self, url, **_kwargs):
        self.calls.append(url)
        record = self.responses[url]
        body = (CAPTURE / record["path"]).read_bytes()
        if record["path"] == "jtwc-abio-advisory.txt" and self.advisory is not None:
            body = self.advisory
        if record["path"] == "jtwc-abpw-advisory.txt" and self.abpw is not None:
            body = self.abpw
        headers = {key.lower(): value for key, value in record["headers"].items()}
        return Response(record["status"], headers, body)


def contradictory_invest_bodies():
    """Synthetic conflict: the captured promotion also lists 93S as active."""
    raw = (CAPTURE / "jtwc-abio-advisory.txt").read_bytes()
    empty = b"(2) NO OTHER SUSPECT AREAS."
    assert raw.count(empty) == 1
    promoted_first = raw.replace(
        empty,
        b"(2) THE AREA OF CONVECTION (INVEST 93S) IS NOW LOCATED NEAR 3.2S 57.1E.")
    start = raw.index(b"(1) THE AREA OF CONVECTION (INVEST 93S)")
    end = raw.index(empty, start)
    promotion = raw[start:end].strip().replace(b"(1)", b"(2)", 1)
    active_first = (raw[:start]
                    + b"(1) THE AREA OF CONVECTION (INVEST 93S) "
                      b"IS NOW LOCATED NEAR 3.2S 57.1E.\r\n      "
                    + promotion + raw[end + len(empty):])
    return promoted_first, active_first


class StormPromotionTests(Sandbox):
    def test_raw_provenance_and_warning_replaces_invest(self):
        manifest = json.loads((CAPTURE / "manifest.json").read_text())
        for record in manifest["records"]:
            with self.subTest(path=record["path"]):
                body = (CAPTURE / record["path"]).read_bytes()
                self.assertEqual((len(body), hashlib.sha256(body).hexdigest()),
                                 (record["bytes"], record["sha256"]))
        products, _, _ = parse_jtwc_rss((CAPTURE / "jtwc-rss.xml").read_bytes())
        self.assertEqual([(item.identity, item.kind) for item in products],
                         [("WP292026", "warning"), ("SH022027", "warning")])
        advisory = parse_advisory((CAPTURE / "jtwc-abio-advisory.txt").read_bytes(), "abio")
        self.assertEqual(advisory.areas[1].warned_codes, ("02S",))
        self.assertEqual(advisory.invests, ())
        snapshot = collect_snapshot(CapturedFetcher(), now=NOW)
        self.assertEqual([storm.id for storm in snapshot.storms],
                         ["WP292026", "SH022027"])
        self.assertEqual(snapshot.storms[1].current.lat, -4.5)
        abpw = parse_advisory((CAPTURE / "jtwc-abpw-advisory.txt").read_bytes(), "abpw")
        after_old_cutoff = datetime(2026, 10, 20, 18, 0, 1, tzinfo=timezone.utc).timestamp()
        self.assertLess(after_old_cutoff, abpw.valid_until_at)
        with self.assertRaisesRegex(FeedError, "ABIO advisory is stale"):
            collect_snapshot(CapturedFetcher(), now=after_old_cutoff)

    def test_upgrade_rechecks_old_cached_deadline_before_successful_time_moves(self):
        settings = self.config("StormCheckIntervalSeconds=1800\n")
        old_abpw = (CAPTURE / "jtwc-abpw-advisory.txt").read_bytes()
        self.assertIn(b"200600Z-210600ZOCT2026", old_abpw)
        reissued_abpw = (old_abpw.replace(b"ABPW10 PGTW 200600", b"ABPW10 PGTW 201700", 1)
                         .replace(b"200600Z-210600ZOCT2026",
                                  b"201700Z-202030ZOCT2026", 1))
        before_expiry = datetime(2026, 10, 20, 17, 59, tzinfo=timezone.utc).timestamp()
        first = run(self.fs, settings, fetcher=CapturedFetcher(abpw=reissued_abpw),
                    now=before_expiry)
        self.assertEqual(first.outcome, "changed", first.message)
        saved = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        style = asdict(settings.storm)
        for name in ("journal", "interval", "timeout", "max_bytes", "warning"):
            style.pop(name)
        for name in ("marker", "arc"):
            style[name] = str(self.fs.resolve(getattr(settings.storm, name), write=True)
                              .relative_to(self.fs.root))
        style["parser_version"] = 5
        style["sources"] = "NHC-ATCF+JTWC-RSS-warning-KMZ-ABPW-ABIO"
        legacy_key = hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()
        record = self.read_state(settings)
        record["products"]["storm"]["source_key"] = legacy_key
        record["products"]["storm"]["source_valid_until_at"] = datetime(
            2026, 10, 20, 20, 30, tzinfo=timezone.utc).timestamp()
        self.fs.write(settings.state, json.dumps(record).encode())
        after_abio_expiry = datetime(2026, 10, 20, 18, 10, tzinfo=timezone.utc).timestamp()
        fetcher = CapturedFetcher(abpw=reissued_abpw)
        failed = run(self.fs, settings, fetcher=fetcher, now=after_abio_expiry)
        self.assertEqual((failed.outcome, failed.successful_at),
                         ("failed", before_expiry))
        self.assertIn("ABIO advisory is stale", failed.message)
        self.assertTrue(fetcher.calls)
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), saved)

    def test_ambiguous_promotion_and_missing_or_multiple_current_fixes_fail(self):
        promoted = (CAPTURE / "jtwc-abio-advisory.txt").read_bytes()
        for body in (promoted.replace(b"2.A.(1)", b"2.A.(2)"),
                     promoted.replace(b"2.A.(1)", b"1.A.(1)"),
                     promoted.replace(b"SEE PARA.", b"SEE UNKNOWN PARA."),
                     promoted.replace(b"FOR FURTHER DETAILS.",
                                      b"FOR FURTHER DETAILS. IS NOW LOCATED NEAR 3.2S 57.1E")):
            with self.subTest(body=body[-100:]):
                with self.assertRaisesRegex(FeedError, "promoted invest reference is ambiguous"):
                    parse_advisory(body, "abio")
        duplicate = promoted.replace(
            b"(2) NO OTHER SUSPECT AREAS.",
            b"(2) THE AREA OF CONVECTION (INVEST 94S) PREVIOUSLY LOCATED NEAR "
            b"3.1S 57.0E IS NOW THE SUBJECT OF A TROPICAL CYCLONE WARNING. "
            b"SEE PARA. 2.A.(1) FOR FURTHER DETAILS.")
        with self.assertRaisesRegex(FeedError, "promoted invests repeat a warning"):
            parse_advisory(duplicate, "abio")
        ordinary = (EARLIER.parent / "jtwc-abio-20261019.txt").read_bytes()
        self.assertIn(b"IS NOW LOCATED NEAR 4.0N 57.0E", ordinary)
        for body in (ordinary.replace(b"IS NOW LOCATED NEAR 4.0N 57.0E",
                                      b"WAS ONCE LOCATED NEAR 4.0N 57.0E"),
                     ordinary.replace(b"IS NOW LOCATED NEAR 4.0N 57.0E",
                                      b"IS NOW LOCATED NEAR 4.0N 57.0E "
                                      b"IS NOW LOCATED NEAR 4.1N 57.1E")):
            with self.subTest(body=body[200:400]):
                with self.assertRaisesRegex(FeedError, "lacks one explicit current position"):
                    parse_advisory(body, "abio")

    def test_promoted_and_active_same_invest_rejects_both_orders(self):
        for body in contradictory_invest_bodies():
            with self.subTest(first_block=body.split(b"(1) THE AREA")[1][:70]):
                with self.assertRaisesRegex(FeedError, "advisory repeats an invest code"):
                    parse_advisory(body, "abio")
                with self.assertRaisesRegex(FeedError, "advisory repeats an invest code"):
                    collect_snapshot(CapturedFetcher(advisory=body), now=NOW)

    def test_duplicate_invest_failure_preserves_last_good_pair(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        initial = run(self.fs, settings, fetcher=CapturedFetcher(), now=NOW)
        self.assertEqual((initial.outcome, initial.count), ("changed", 2))
        saved = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        for index, body in enumerate(contradictory_invest_bodies(), 1):
            with self.subTest(order=index):
                failed = run(self.fs, settings, fetcher=CapturedFetcher(advisory=body),
                             now=NOW + index * 60)
                self.assertEqual((failed.outcome, failed.successful_at), ("failed", NOW))
                self.assertIn("advisory repeats an invest code", failed.message)
                self.assertEqual((self.fs.read(settings.storm.marker),
                                  self.fs.read(settings.storm.arc)), saved)
                self.assertEqual(self.read_state(settings)["products"]["storm"]["count"], 2)

    def test_offline_cli_success_then_ambiguous_reference_retains_last_good(self):
        self.config("StormCheckIntervalSeconds=0\n")
        output = io.StringIO()
        with patch("totalmarker.cli.run_storm",
                   side_effect=lambda fs, settings: run(
                       fs, settings, fetcher=CapturedFetcher(), now=NOW)):
            with redirect_stdout(output):
                status = cli_main(["--root", str(self.root), "--config", "config.ini", "storm"])
        self.assertEqual(status, 0)
        self.assertEqual((json.loads(output.getvalue())["outcome"],
                          json.loads(output.getvalue())["count"]), ("changed", 2))
        settings = self.config("StormCheckIntervalSeconds=0\n")
        marker = self.fs.read(settings.storm.marker)
        arc = self.fs.read(settings.storm.arc)
        self.assertIn(b'"Two"', marker)
        self.assertNotIn(b'"Invest 93S"', marker + arc)
        self.assertIn(b"color=", arc)
        previous = self.read_state(settings)["products"]["storm"]
        broken = (CAPTURE / "jtwc-abio-advisory.txt").read_bytes().replace(
            b"2.A.(1)", b"2.A.(2)")
        output = io.StringIO()
        with patch("totalmarker.cli.run_storm",
                   side_effect=lambda fs, settings: run(
                       fs, settings, fetcher=CapturedFetcher(advisory=broken), now=NOW + 60)):
            with redirect_stdout(output):
                status = cli_main(["--root", str(self.root), "--config", "config.ini", "storm"])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "failed")
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)),
                         (marker, arc))
        current = self.read_state(settings)["products"]["storm"]
        self.assertEqual(current["successful_at"], previous["successful_at"])
        self.assertEqual(current["installed_at"], previous["installed_at"])

    def test_older_last_good_pair_survives_rejected_promotion(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=live_fetcher(), now=EARLIER_AT)
        self.assertEqual(first.outcome, "changed")
        saved = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        bad = (CAPTURE / "jtwc-abio-advisory.txt").read_bytes().replace(
            b"SEE PARA.", b"SEE UNKNOWN PARA.")
        result = run(self.fs, settings, fetcher=CapturedFetcher(advisory=bad), now=NOW)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.successful_at, EARLIER_AT)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)),
                         saved)
        row = next(line for line in self.fs.read(settings.labels).decode().splitlines()
                   if "Storm Infomation" in line)
        self.assertIn("color=Red", row)
