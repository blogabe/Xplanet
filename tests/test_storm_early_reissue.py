"""Replay the captured JTWC ABPW early reissue without external requests."""
from datetime import datetime, timezone
from email.utils import formatdate
import hashlib
import json
from pathlib import Path

from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.http import Response
from totalmarker.storm_advisory import parse_advisory
from totalmarker.storm_sources import (
    JTWC_RSS, collect_snapshot, parse_jtwc_rss, _fresh_advisory,
)
from .support import Sandbox
from .support_storm import JTWC, empty_advisory

FIXTURE = Path(__file__).parent / "fixtures/storm/live-20261124-early-reissue"
ABPW_URL = JTWC + "abpwweb.txt"
ABIO_URL = JTWC + "abioweb.txt"
MATCH = ("Reissued", "23/1200Z")
HEADER = b"ABPW10 PGTW 231200"
INTERVAL = b"231300Z-240600ZNOV2026"
NOW = datetime(2026, 11, 24, 1, 10, 5, tzinfo=timezone.utc).timestamp()
ISSUED = datetime(2026, 11, 23, 12, tzinfo=timezone.utc).timestamp()
START = ISSUED + 3600
END = datetime(2026, 11, 24, 6, tzinfo=timezone.utc).timestamp()


class EarlyPacket:
    def __init__(self):
        self.records = json.loads((FIXTURE / "sources.json").read_text())["responses"]
        self.payloads = {r["url"]: (FIXTURE / r["file"]).read_bytes() for r in self.records}
        # Old code stopped on ABPW before it fetched ABIO. This separate,
        # synthetic 18Z bulletin corroborates the captured active 98S TCFA.
        abio = (empty_advisory("abio")
                .replace(b"ABIO10 PGTW 190900", b"ABIO10 PGTW 231800")
                .replace(b"190900Z-200600ZOCT2026", b"231800Z-241800ZNOV2026"))
        end = abio.rfind(b"B. TROPICAL DISTURBANCE SUMMARY: NONE.")
        self.payloads[ABIO_URL] = abio[:end] + abio[end:].replace(
            b"B. TROPICAL DISTURBANCE SUMMARY: NONE.",
            b"B. TROPICAL DISTURBANCE SUMMARY:\n"
            b"      (1) THE AREA OF CONVECTION (INVEST 98S) HAS PERSISTED NEAR 7.6S 76.8E.", 1)

    def fetch(self, url, **kwargs):
        if url not in self.payloads:
            raise AssertionError("Unexpected offline storm request: " + url)
        # Empty NHC index needs a Date; original rejection capture omits headers.
        return Response(200, {"date": formatdate(NOW, usegmt=True)}, self.payloads[url])


class EarlyReissueTests(Sandbox):
    def test_receipted_response_collects_and_publishes_without_retired_xavier(self):
        packet = EarlyPacket()
        for record in packet.records:
            raw = packet.payloads[record["url"]]
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()),
                             (record["bytes"], record["sha256"]))
        _, _, links = parse_jtwc_rss(packet.payloads[JTWC_RSS])
        self.assertEqual(links["abpw"], (ABPW_URL, MATCH))
        advisory = parse_advisory(packet.payloads[ABPW_URL], "abpw", rss_issue=MATCH)
        self.assertEqual((advisory.issued_at, advisory.issue_at, advisory.valid_until_at),
                         (ISSUED, START, END))
        self.assertTrue(all(a.cyclone_none for a in advisory.areas))
        snapshot = collect_snapshot(packet, now=NOW)
        self.assertEqual(tuple(storm.id for storm in snapshot.storms), ("SH982027",))
        self.assertEqual(snapshot.storms[0].history, ())
        self.assertEqual(snapshot.storms[0].forecast, ())
        self.assertEqual(dict(snapshot.source_times)["jtwc_west"], ISSUED)

        settings = self.config("StormCheckIntervalSeconds=0\n")
        result = run(self.fs, settings, fetcher=packet, now=NOW)
        self.assertEqual((result.outcome, result.count), ("changed", 1), result.message)
        marker = self.fs.read(settings.storm.marker)
        arc = self.fs.read(settings.storm.arc)
        self.assertIn(b"Invest 98S", marker)
        self.assertNotIn(b"Xavier", marker + arc)
        self.assertNotIn(b"Invest 98S", arc)
        for bad in (b"Reissued at 23/1300Z", b"Reissued at 23/1201Z",
                    b"Issued at 23/1200Z", b"No issue time",
                    b"Reissued at 23/1200Z Reissued at 23/1200Z"):
            with self.subTest(rss=bad):
                wrong = EarlyPacket()
                rss = wrong.payloads[JTWC_RSS]
                self.assertEqual(rss.count(b"Reissued at 23/1200Z"), 1)
                wrong.payloads[JTWC_RSS] = rss.replace(b"Reissued at 23/1200Z", bad)
                result = run(self.fs, settings, fetcher=wrong, now=NOW + 1)
                self.assertEqual(result.outcome, "failed", result.message)
                self.assertEqual(result.successful_at, NOW)
                self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)),
                                 (marker, arc))

    def test_early_window_is_bounded_and_regular_correction_and_indian_stay_strict(self):
        raw = EarlyPacket().payloads[ABPW_URL]
        for label, body, match in (
            ("no RSS", raw, None),
            ("61 minutes early", raw.replace(HEADER, b"ABPW10 PGTW 231159"), ("Reissued", "23/1159Z")),
            ("duplicate WMO", raw.replace(HEADER, HEADER + b"\r\n" + HEADER), MATCH),
            ("issue not reissue", raw.replace(b"REISSUED/", b"ISSUED/"), MATCH),
            ("ordinary subject", raw.replace(b" REISSUED/", b"/"), MATCH),
            ("correction", raw.replace(b"REISSUED/", b"CORRECTED/").replace(HEADER, HEADER + b" COR"), MATCH),
            ("expiry", raw.replace(HEADER, b"ABPW10 PGTW 240600"), ("Reissued", "24/0600Z")),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(FeedError, "header disagrees"):
                    parse_advisory(body, "abpw", rss_issue=match)
        abio = EarlyPacket().payloads[ABIO_URL].replace(b"ISSUED/", b"REISSUED/")
        abio = abio.replace(b"ABIO10 PGTW 231800", b"ABIO10 PGTW 231700")
        with self.assertRaisesRegex(FeedError, "header disagrees"):
            parse_advisory(abio, "abio", rss_issue=("Reissued", "23/1700Z"))

        within = raw.replace(HEADER, b"ABPW10 PGTW 231201")
        advisory = parse_advisory(within, "abpw", rss_issue=("Reissued", "23/1201Z"))
        self.assertEqual(advisory.issued_at, ISSUED + 60)
        self.assertEqual(advisory.valid_until_at, END)
        _fresh_advisory(advisory, END, "abpw")
        _fresh_advisory(advisory, START - 3600, "abpw")
        with self.assertRaisesRegex(FeedError, "ABPW advisory is future-dated"):
            _fresh_advisory(advisory, START - 3601, "abpw")
        with self.assertRaisesRegex(FeedError, "ABPW advisory is stale"):
            _fresh_advisory(advisory, END + 1, "abpw")
        with self.assertRaisesRegex(FeedError, "ABPW advisory is future-dated"):
            _fresh_advisory(advisory, advisory.issued_at - 3601, "abpw")

    def test_early_reissue_uses_observation_proxy_across_season_rollover(self):
        raw = EarlyPacket().payloads[ABPW_URL].replace(HEADER, b"ABPW10 PGTW 302330")
        raw = raw.replace(INTERVAL, b"010030Z-010600ZJUL2026")
        end = raw.rfind(b"B. TROPICAL DISTURBANCE SUMMARY: NONE.")
        raw = raw[:end] + raw[end:].replace(
            b"B. TROPICAL DISTURBANCE SUMMARY: NONE.",
            b"B. TROPICAL DISTURBANCE SUMMARY:\r\n"
            b"      (1) THE AREA OF CONVECTION (INVEST 99P) HAS PERSISTED NEAR 9.0S 160.0W.", 1)
        advisory = parse_advisory(raw, "abpw", rss_issue=("Reissued", "30/2330Z"))
        early = datetime(2026, 6, 30, 23, 30, tzinfo=timezone.utc).timestamp()
        self.assertEqual((advisory.issued_at, advisory.issue_at, advisory.position_at),
                         (early, early + 3600, early))
        invest, = advisory.invests
        self.assertEqual((invest.id, invest.current.at), ("SH992026", early))
