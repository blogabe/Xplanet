"""Offline cancellation regressions: retiring an alert does not erase its invest."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.storm_advisory import parse_advisory
from totalmarker.storm_sources import (
    _parse_jtwc_formation_product, collect_snapshot, parse_jtwc_formation_alert,
)
from .support import Sandbox
from .support_storm import JTWC, formation_fetcher

CAPTURE = Path(__file__).parent / 'fixtures/storm/live-20261119-cancellation'
NOW = datetime(2026, 10, 20, 6, 5, tzinfo=timezone.utc).timestamp()


def cancelled_packet():
    packet = formation_fetcher()
    url = JTWC + 'sh9327web.txt'
    raw = packet.payloads[url]
    raw = raw.replace(b'(INVEST 93S)//', b'(INVEST 93S) CANCELLATION//')
    raw = raw.replace(b'RMKS/', b'RMKS/\nTHIS CANCELS REF A. ', 1)
    packet.payloads[url] = raw
    return packet


class CancellationTests(Sandbox):
    def test_authentic_cancellation_and_advisory_bytes_and_fix(self):
        for record in json.loads((CAPTURE / 'sources.json').read_text())['responses']:
            raw = (CAPTURE / record['file']).read_bytes()
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()),
                             (record['bytes'], record['sha256']))
        raw = (CAPTURE / 'sh9627web.txt').read_bytes()
        at = datetime(2026, 11, 19, tzinfo=timezone.utc).timestamp()
        point, code, cancelled = _parse_jtwc_formation_product(raw, 'SH962027', at)
        self.assertEqual((point.lat, point.lon, code, cancelled), (-5.6, 90.2, '96S', True))
        with self.assertRaisesRegex(FeedError, 'is cancelled'):
            parse_jtwc_formation_alert(raw, 'SH962027', at)
        advisory_raw = (CAPTURE / 'abioweb.txt').read_bytes()
        self.assertIn(b'87NOV26', advisory_raw)  # Unused provider narrative typo.
        advisory = parse_advisory(advisory_raw, 'abio')
        invest = next(s for s in advisory.invests if s.id == 'SH962027')
        self.assertEqual(invest.current, point)

    def test_cancellation_requires_unambiguous_identity_date_and_position(self):
        raw = (CAPTURE / 'sh9627web.txt').read_bytes()
        at = datetime(2026, 11, 19, tzinfo=timezone.utc).timestamp()
        for changed in (
            raw.replace(b'CANCELLATION', b'EXPIRED'),
            raw.replace(b'THIS CANCELS REF A', b'THIS EXTENDS REF A'),
            raw.replace(b' CANCELLATION', b''),
            raw.replace(b'(INVEST 96S)', b'(INVEST 95S)', 1),
            raw.replace(b'181800', b'881800', 1),
            raw.replace(b'LOCATED NEAR 5.6S', b'LOCATED NEAR 95.6S'),
            raw + b'\nIS NOW LOCATED NEAR 5.6S 90.2E\n',
        ):
            with self.subTest(changed=changed[:150]):
                with self.assertRaises(FeedError):
                    _parse_jtwc_formation_product(changed, 'SH962027', at)

    def test_cancelled_alert_keeps_independent_invest_without_track(self):
        packet = cancelled_packet()
        snapshot = collect_snapshot(packet, now=NOW)
        invest = next(s for s in snapshot.storms if s.id == 'SH932027')
        self.assertEqual((invest.name, invest.current.lat, invest.current.lon),
                         ('Invest 93S', -3.9, 55.5))
        self.assertEqual((invest.history, invest.forecast, invest.forecast_status),
                         ((), (), 'not_issued'))
        self.assertFalse(any(url.endswith('sh9327.kmz') for url in packet.calls))

    def test_newer_advisory_remains_authoritative_after_cancellation(self):
        packet = cancelled_packet()
        url = JTWC + 'abioweb.txt'
        packet.payloads[url] = (packet.payloads[url]
            .replace(b'ABIO10 PGTW 192000', b'ABIO10 PGTW 200600')
            .replace(b'REISSUED/192000Z-201800ZOCT2026',
                     b'REISSUED/200600Z-210600ZOCT2026')
            .replace(b'IS NOW LOCATED NEAR 3.9S', b'IS NOW LOCATED NEAR 4.0S'))
        snapshot = collect_snapshot(packet, now=NOW)
        invest = next(s for s in snapshot.storms if s.id == 'SH932027')
        self.assertEqual(invest.current.lat, -4.0)
        self.assertEqual(invest.current.at, NOW - 300)
        self.assertEqual((invest.history, invest.forecast), ((), ()))

    def test_contradiction_or_stale_cancellation_preserves_publication(self):
        settings = self.config('StormCheckIntervalSeconds=0\n')
        self.assertEqual(run(self.fs, settings, fetcher=cancelled_packet(),
                             now=NOW).outcome, 'changed')
        paths = (settings.storm.marker, settings.storm.arc)
        previous = [self.fs.read(path) for path in paths]
        for failure in ('position', 'missing_invest', 'newer_alert', 'stale'):
            packet = cancelled_packet()
            url = JTWC + 'sh9327web.txt'
            if failure == 'position':
                packet.payloads[url] = packet.payloads[url].replace(
                    b'IS NOW LOCATED NEAR 3.9S', b'IS NOW LOCATED NEAR 4.9S')
            elif failure == 'missing_invest':
                url = JTWC + 'abioweb.txt'
                packet.payloads[url] = packet.payloads[url].replace(b'INVEST 93S', b'INVEST 94S')
            elif failure == 'newer_alert':
                packet.payloads[url] = packet.payloads[url].replace(b'PGTW 192000', b'PGTW 200000')
            at = NOW + (48 * 3600 if failure == 'stale' else 1)
            with self.subTest(failure=failure):
                result = run(self.fs, settings, fetcher=packet, now=at)
                self.assertEqual(result.outcome, 'failed', result.message)
                self.assertEqual([self.fs.read(path) for path in paths], previous)
