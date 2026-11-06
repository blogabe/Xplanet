"""Final-warning retirement using independently downloaded official responses."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.http import Response
from totalmarker.storm_advisory import parse_advisory
from totalmarker.storm_sources import collect_snapshot
from .support import Sandbox
from .test_storm_sources import MappedFetcher, NOW

FIXTURE = Path(__file__).parent / 'fixtures/storm/live-20261106-final-warning'
AT = datetime(2026, 11, 6, 6, 57, tzinfo=timezone.utc).timestamp()


class PublicPacket:
    def __init__(self):
        self.records = json.loads((FIXTURE / 'sources.json').read_text())['responses']
        self.payloads = {r['url']: (FIXTURE / r['file']).read_bytes() for r in self.records}

    def fetch(self, url, **kwargs):
        record = next(r for r in self.records if r['url'] == url)
        return Response(200, {'date': record['date']}, self.payloads[url])


class FinalWarningTests(Sandbox):
    def test_public_packet_integrity_and_retired_warning(self):
        packet = PublicPacket()
        for record in packet.records:
            body = packet.payloads[record['url']]
            self.assertEqual(len(body), record['bytes'])
            self.assertEqual(hashlib.sha256(body).hexdigest(), record['sha256'])
        advisory = parse_advisory((FIXTURE / 'jtwc-abpw.txt').read_bytes(), 'abpw')
        self.assertEqual(advisory.areas[0].warned_codes, ('30W',))
        self.assertEqual(advisory.areas[0].final_codes, ('30W',))
        result = collect_snapshot(packet, now=AT)
        self.assertEqual([s.id for s in result.storms], ['WP992026', 'SH942027'])

    def test_missing_active_warning_still_rejected(self):
        packet = PublicPacket()
        url = next(u for u in packet.payloads if u.endswith('abpwweb.txt'))
        packet.payloads[url] = packet.payloads[url].replace(b'FINAL WARNING', b'WARNING').replace(
            b'FINAL \r\nWARNING', b'WARNING')
        with self.assertRaisesRegex(FeedError, 'warnings disagree'):
            collect_snapshot(packet, now=AT)

    def test_final_reference_must_be_unique_and_explicit(self):
        original = (FIXTURE / 'jtwc-abpw.txt').read_bytes()
        mutations = (
            original.replace(b'NARR/REF A IS', b'NARR/REF C IS'),
            original.replace(b'REF/A/MSG/', b'REF/C/MSG/'),
            original.replace(b'NARR/', b'REF/A/MSG/DUPLICATE//\r\nNARR/'),
            original.replace(b'30W (IN-FA)', b'30W (IN-FA) AND TROPICAL STORM 31W'),
        )
        for body in mutations:
            with self.subTest(body=hashlib.sha256(body).hexdigest()):
                with self.assertRaisesRegex(FeedError, 'final warning reference is ambiguous'):
                    parse_advisory(body, 'abpw')

    def test_one_final_reference_cannot_retire_two_storms(self):
        body = (FIXTURE / 'jtwc-abpw.txt').read_bytes().replace(
            b'(2) NO OTHER TROPICAL CYCLONES.',
            b'(2) TROPICAL STORM 31W. SEE REF A (WTPN31 PGTW 050900) '
            b'FOR THE FINAL WARNING ON THIS SYSTEM.')
        with self.assertRaisesRegex(FeedError, 'final warning reference is ambiguous'):
            parse_advisory(body, 'abpw')

    def test_final_warning_may_still_have_active_rss_product(self):
        packet = MappedFetcher()
        abpw = next(body for url, body in packet.payloads.items() if url.endswith('abpwweb.txt'))
        self.assertEqual(parse_advisory(abpw, 'abpw').areas[1].final_codes, ('01P',))
        result = collect_snapshot(packet, now=NOW)
        self.assertIn('SH012027', [storm.id for storm in result.storms])

    def test_final_warning_does_not_bypass_source_expiry(self):
        with self.assertRaises(FeedError):
            collect_snapshot(PublicPacket(), now=AT + 48 * 3600)

    def test_rejected_transition_preserves_last_good_publication(self):
        settings = self.config('StormCheckIntervalSeconds=0\n')
        self.assertEqual(run(self.fs, settings, fetcher=PublicPacket(), now=AT).outcome, 'changed')
        previous = {p: self.fs.read(p) for p in (settings.storm.marker, settings.storm.arc)}
        bad = PublicPacket()
        url = next(u for u in bad.payloads if u.endswith('abpwweb.txt'))
        bad.payloads[url] = bad.payloads[url].replace(b'NARR/REF A IS', b'NARR/REF C IS')
        failed = run(self.fs, settings, fetcher=bad, now=AT + 1)
        self.assertEqual(failed.outcome, 'failed')
        for path, body in previous.items():
            self.assertEqual(self.fs.read(path), body)
