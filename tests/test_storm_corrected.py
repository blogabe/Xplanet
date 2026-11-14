"""Authentic corrected JTWC bulletin, including clean-root publication."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.http import Response
from totalmarker.storm_advisory import parse_advisory
from totalmarker.storm_sources import collect_snapshot, _fresh_advisory
from .support import Sandbox
from .test_storm_sources import JTWC

FIXTURE = Path(__file__).parent / 'fixtures/storm/live-20261114-corrected'
AT = datetime(2026, 11, 14, 16, 49, tzinfo=timezone.utc).timestamp()


class Packet:
    def __init__(self):
        self.records = json.loads((FIXTURE / 'sources.json').read_text())['responses']
        self.payloads = {r['url']: (FIXTURE / r['file']).read_bytes() for r in self.records}

    def fetch(self, url, **kwargs):
        record = next(r for r in self.records if r['url'] == url)
        return Response(200, {'date': record['date']}, self.payloads[url])


class CorrectedAdvisoryTests(Sandbox):
    def test_authentic_packet_integrity_and_complete_snapshot(self):
        packet = Packet()
        for record in packet.records:
            body = packet.payloads[record['url']]
            self.assertEqual((len(body), hashlib.sha256(body).hexdigest()),
                             (record['bytes'], record['sha256']))
        snapshot = collect_snapshot(packet, now=AT)
        self.assertEqual({s.id for s in snapshot.storms},
                         {'IO922026', 'SH962027', 'SH952027'})
        invest = next(s for s in snapshot.storms if s.id == 'SH952027')
        self.assertEqual((invest.current.lat, invest.current.lon), (-9.2, -157.1))
        self.assertEqual((invest.history, invest.forecast, invest.forecast_status),
                         ((), (), 'not_issued'))

    def test_correction_preserves_issue_and_validity_guards(self):
        raw = (FIXTURE / 'abpw.txt').read_bytes()
        advisory = parse_advisory(raw, 'abpw')
        start = datetime(2026, 11, 14, 13, tzinfo=timezone.utc).timestamp()
        until = datetime(2026, 11, 15, 6, tzinfo=timezone.utc).timestamp()
        self.assertEqual((advisory.issue_at, advisory.issued_at, advisory.valid_until_at),
                         (start, start, until))
        for at in (start - 3600, start, until):
            _fresh_advisory(advisory, at, 'abpw')
        for at in (start - 3601, until + 1):
            with self.assertRaises(FeedError):
                _fresh_advisory(advisory, at, 'abpw')
        mutations = [
            raw.replace(b'141300 COR', b'141300'),
            raw.replace(b'141300 COR', b'141300 XYZ'),
            raw.replace(b'141300 COR', b'141301 COR'),
            raw.replace(b'CORRECTED/', b'ISSUED/'),
            raw.replace(b'CORRECTED/', b'CORRECTED '),
            raw.replace(b'150600ZNOV2026', b'320600ZNOV2026'),
            raw.replace(b'RMKS/', b'CORRECTED/141300Z-150600ZNOV2026//\r\nRMKS/'),
            raw.replace(b'WESTERN AND SOUTH \r\nPACIFIC OCEANS', b'INDIAN OCEAN'),
            raw.replace(b'C. SUBTROPICAL SYSTEM SUMMARY: NONE.', b'C. SUBTROPICAL SYSTEM SUMMARY: UNKNOWN.'),
            raw.replace(b'B. TROPICAL DISTURBANCE SUMMARY:', b'B. UNRECOGNIZED SUMMARY:', 1),
        ]
        for body in mutations:
            with self.subTest(sha=hashlib.sha256(body).hexdigest()):
                with self.assertRaises(FeedError):
                    parse_advisory(body, 'abpw')

    def test_clean_root_creates_pair_and_failed_refresh_retains_it(self):
        settings = self.config('StormCheckIntervalSeconds=0\n')
        paths = (settings.storm.marker, settings.storm.arc)
        self.assertTrue(all(not (self.root / p).exists() for p in paths))
        malformed = Packet()
        malformed.payloads[JTWC + 'abpwweb.txt'] = b'broken'
        self.assertEqual(run(self.fs, settings, fetcher=malformed, now=AT).outcome, 'failed')
        self.assertTrue(all(not (self.root / p).exists() for p in paths))
        success = run(self.fs, settings, fetcher=Packet(), now=AT + 1)
        self.assertEqual((success.outcome, success.count), ('changed', 3), success.message)
        before = [self.fs.read(p) for p in paths]
        self.assertIn(b'Invest 95P', before[0])
        self.assertNotIn(b'Invest 95P', before[1])
        self.assertEqual(run(self.fs, settings, fetcher=malformed, now=AT + 2).outcome, 'failed')
        self.assertEqual([self.fs.read(p) for p in paths], before)
