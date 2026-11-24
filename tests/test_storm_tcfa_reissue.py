"""Captured JTWC TCFA reissue and offline advisory reconciliation."""
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path

from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.storm_sources import (
    JTWC_RSS, collect_snapshot, parse_jtwc_formation_alert, parse_jtwc_rss,
)
from .support import Sandbox
from .support_storm import JTWC, ReceiptPacket, empty_advisory

FIXTURE = Path(__file__).parent / "fixtures/storm/live-20261124-tcfa-reissued"
ALERT_URL = JTWC + "sh9827web.txt"
AT = datetime(2026, 11, 24, 4, tzinfo=timezone.utc).timestamp()
NOW = AT + 11 * 60


def replay(*, advisory_time=b"240330", position=b"8.9S 78.6E"):
    packet = ReceiptPacket(FIXTURE, default_date=formatdate(NOW, usegmt=True))
    # This earlier authentic ABPW still has the exact stamp in the new RSS.
    packet.payloads[JTWC + "abpwweb.txt"] = (
        FIXTURE.parent / "live-20261124-early-reissue/abpw.txt").read_bytes()
    # No new ABIO was captured; construct dated variants. The 03:30 variant
    # uses the original RSS; the 04:00 variant pairs with a synthetic RSS update.
    abio = (empty_advisory("abio")
            .replace(b"ABIO10 PGTW 190900", b"ABIO10 PGTW " + advisory_time)
            .replace(b"ISSUED/190900Z-200600ZOCT2026",
                     b"REISSUED/" + advisory_time + b"Z-241800ZNOV2026"))
    head, tail = abio.rsplit(b"B. TROPICAL DISTURBANCE SUMMARY: NONE.", 1)
    packet.payloads[JTWC + "abioweb.txt"] = (
        head + b"B. TROPICAL DISTURBANCE SUMMARY:\n"
        b"      (1) THE AREA OF CONVECTION (INVEST 98S) HAS PERSISTED NEAR " + position + b"." + tail)
    if advisory_time != b"240330":
        packet.payloads[JTWC_RSS] = packet.payloads[JTWC_RSS].replace(
            b"Reissued at 24/0330Z", b"Reissued at 24/" + advisory_time[2:] + b"Z")
    return packet


class FormationReissueTests(Sandbox):
    def test_captured_rss_and_alert_agree_on_identity_date_and_fix(self):
        packet = replay()
        packet.assert_integrity(self)
        products, source_times, advisory_links = parse_jtwc_rss(packet.payloads[JTWC_RSS])
        product, = products
        self.assertEqual((product.identity, product.warning_url, product.kind),
                         ("SH982027", ALERT_URL, "formation_alert"))
        self.assertEqual(advisory_links["abio"][1], ("Reissued", "24/0330Z"))
        fix, code = parse_jtwc_formation_alert(packet.payloads[ALERT_URL], product.identity,
                                              source_times[product.group])
        self.assertEqual((fix.at, fix.lat, fix.lon, code), (AT, -8.9, 78.6, "98S"))

    def test_reissue_does_not_bypass_identity_date_and_cancellation_guards(self):
        raw = replay().payloads[ALERT_URL]
        for body, identity, message in (
            (raw.replace(b" REISSUED//", b" EXPIRED//"), "SH982027", "identity disagrees"),
            (raw.replace(b" REISSUED//", b" REISSUED CANCELLATION//"), "SH982027", "identity disagrees"),
            (raw, "SH972027", "identity disagrees"),
            (raw, "SH982026", "season disagrees"),
            (raw.replace(b"PGTW 240400", b"PGTW 210400"), "SH982027", "date disagrees"),
            (raw.replace(b"PGTW 240400", b"PGTW 880400"), "SH982027", "date is invalid"),
            (raw.replace(b"RMKS/", b"RMKS/\r\nTHIS CANCELS REF A."), "SH982027", "cancellation is ambiguous"),
            (raw + b"\r\nIS NOW LOCATED NEAR 8.9S 78.6E\r\n", "SH982027", "one current position"),
        ):
            with self.subTest(identity=identity, message=message):
                with self.assertRaisesRegex(FeedError, message):
                    parse_jtwc_formation_alert(body, identity, NOW)

    def test_needs_current_advisory_and_preserves_last_good_when_sources_disagree(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        current = replay(advisory_time=b"240400")
        snapshot = collect_snapshot(current, now=NOW)
        invest, = snapshot.storms
        self.assertEqual((invest.id, invest.history, invest.forecast, invest.forecast_status),
                         ("SH982027", (), (), "not_issued"))
        self.assertNotIn(JTWC + "sh9827.kmz", current.calls)
        success = run(self.fs, settings, fetcher=current, now=NOW)
        self.assertEqual((success.outcome, success.count), ("changed", 1), success.message)
        marker, arc = self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)
        self.assertIn(b"Invest 98S", marker)
        self.assertNotIn(b"Invest 98S", arc)
        for failed, reason in ((replay(), "is newer than ABIO advisory fix"),
                               (replay(advisory_time=b"240400", position=b"9.9S 78.6E"),
                                "conflicting same-time position")):
            result = run(self.fs, settings, fetcher=failed, now=NOW + 1)
            self.assertEqual(result.outcome, "failed", result.message)
            self.assertIn(reason, result.message)
            self.assertEqual(result.successful_at, NOW)
            self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)),
                             (marker, arc))
