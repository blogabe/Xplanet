"""Authentic combined no-warning RSS is not an empty advisory dataset."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from totalmarker.errors import FeedError
from totalmarker.features.storm import run
from totalmarker.http import Response
from totalmarker.storm_sources import collect_snapshot, parse_jtwc_rss, JTWC_RSS
from .support import Sandbox
from .test_storm_sources import JTWC, empty_rss, empty_advisory

FIXTURE = Path(__file__).parent / 'fixtures/storm/live-20261113-no-warnings'
AT = datetime(2026, 11, 13, 4, 9, tzinfo=timezone.utc).timestamp()


class PublicPacket:
    def __init__(self):
        self.records = json.loads((FIXTURE / 'sources.json').read_text())['responses']
        self.payloads = {r['url']: (FIXTURE / r['file']).read_bytes() for r in self.records}
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        record = next(r for r in self.records if r['url'] == url)
        return Response(200, {'date': record['date']}, self.payloads[url])


class WorldwideNoWarningTests(Sandbox):
    def test_public_packet_integrity_and_advisory_invests(self):
        packet = PublicPacket()
        manifest = json.loads((FIXTURE / 'sources.json').read_text())
        for record in manifest['responses'] + [manifest['rejected_response']]:
            body = (FIXTURE / record['file']).read_bytes()
            self.assertEqual(len(body), record['bytes'])
            self.assertEqual(hashlib.sha256(body).hexdigest(), record['sha256'])
        products, times, advisories = parse_jtwc_rss(packet.payloads[JTWC_RSS])
        self.assertEqual(products, ())
        self.assertEqual(set(times), {'jtwc_west', 'jtwc_indian', 'jtwc_south'})
        self.assertEqual(len(set(times.values())), 1)
        self.assertEqual(set(advisories), {'abpw', 'abio'})
        snapshot = collect_snapshot(packet, now=AT)
        self.assertEqual({s.id for s in snapshot.storms}, {'IO922026', 'SH952027'})
        self.assertTrue(all(s.forecast_status == 'not_issued' for s in snapshot.storms))
        self.assertEqual(set(packet.calls), set(packet.payloads))

    def test_original_rejected_response_now_parses_without_suppressing_advisories(self):
        packet = PublicPacket()
        packet.payloads[JTWC_RSS] = (FIXTURE / 'rejected-jtwc-rss.xml').read_bytes()
        snapshot = collect_snapshot(packet, now=AT)
        self.assertEqual({s.id for s in snapshot.storms}, {'IO922026', 'SH952027'})

    def test_combined_and_regional_categories_cannot_overlap_in_either_order(self):
        original = ET.fromstring(PublicPacket().payloads[JTWC_RSS])
        regional = ET.fromstring(empty_rss()).findall('./channel/item')[:2]
        combined = original.find('./channel/item')
        for item in regional + [combined]:
            for first in (True, False):
                root = deepcopy(original)
                channel = root.find('channel')
                channel.insert(0 if first else len(channel), deepcopy(item))
                with self.subTest(title=item.findtext('title'), first=first):
                    with self.assertRaisesRegex(FeedError, 'duplicates a coverage category'):
                        parse_jtwc_rss(ET.tostring(root))

    def test_incomplete_or_ambiguous_combined_declaration_rejected(self):
        original = PublicPacket().payloads[JTWC_RSS]
        mutations = [
            original.replace(b', or Southern Hemisphere</title>', b'</title>'),
            original.replace(b'No Active Tropical Warnings in', b'Current Tropical Systems in'),
            original.replace(b'There are no active tropical warnings', b'Unknown warning status'),
            original.replace(b', or Southern Hemisphere at this time.', b' at this time.'),
            original.replace(b'at this time.', b'at this time. Except a current warning.'),
            original.replace(b'at this time.', b'at this time. <a href="https://www.metoc.navy.mil/jtwc/products/wp3126web.txt">TC Warning Text</a>'),
            original.replace(b'abioweb.txt', b'missing.txt'),
            original[:len(original)//2],
        ]
        for body in mutations:
            with self.subTest(sha=hashlib.sha256(body).hexdigest()):
                with self.assertRaises(FeedError):
                    parse_jtwc_rss(body)
        for field in ('pubDate', 'description'):
            root = ET.fromstring(original)
            item = root.find('./channel/item')
            item.remove(item.find(field))
            with self.assertRaises(FeedError):
                parse_jtwc_rss(ET.tostring(root))

    def test_combined_timestamp_still_enforces_freshness(self):
        for timestamp in ('Thu, 12 Nov 26 03:00:00 +0000',
                          'Sat, 14 Nov 26 04:00:00 +0000', 'invalid'):
            packet = PublicPacket()
            root = ET.fromstring(packet.payloads[JTWC_RSS])
            root.find('./channel/item/pubDate').text = timestamp
            packet.payloads[JTWC_RSS] = ET.tostring(root)
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(FeedError):
                    collect_snapshot(packet, now=AT)

    def test_advisory_warning_disagreement_and_reissue_still_rejected(self):
        packet = PublicPacket()
        body = packet.payloads[JTWC + 'abioweb.txt']
        packet.payloads[JTWC + 'abioweb.txt'] = body.replace(
            b'TROPICAL CYCLONE SUMMARY: NONE.',
            b'TROPICAL CYCLONE SUMMARY:\r\n(1) TROPICAL CYCLONE 01B.', 1)
        with self.assertRaisesRegex(FeedError, 'warnings disagree'):
            collect_snapshot(packet, now=AT)
        packet = PublicPacket()
        packet.payloads[JTWC + 'abioweb.txt'] = packet.payloads[JTWC + 'abioweb.txt'].replace(
            b'ABIO10 PGTW 130000', b'ABIO10 PGTW 130100')
        with self.assertRaisesRegex(FeedError, 'reissue disagrees'):
            collect_snapshot(packet, now=AT)

    def test_advisories_still_required_and_failures_retain_last_good(self):
        settings = self.config('StormCheckIntervalSeconds=0\n')
        self.assertEqual(run(self.fs, settings, fetcher=PublicPacket(), now=AT).outcome, 'changed')
        paths = (settings.storm.marker, settings.storm.arc)
        previous = [self.fs.read(p) for p in paths]
        for kind in ('abio', 'abpw'):
            packet = PublicPacket()
            packet.payloads[JTWC + kind + 'web.txt'] = b'broken'
            failed = run(self.fs, settings, fetcher=packet, now=AT + 1)
            self.assertEqual(failed.outcome, 'failed')
            self.assertEqual([self.fs.read(p) for p in paths], previous)
        with self.assertRaisesRegex(FeedError, 'advisory is stale'):
            collect_snapshot(PublicPacket(), now=AT + 9 * 3600)

    def test_synthetic_empty_advisories_allow_truly_empty_snapshot(self):
        # Deliberately synthetic: the real captured advisories contain invests.
        packet = PublicPacket()
        for kind in ('abio', 'abpw'):
            packet.payloads[JTWC + kind + 'web.txt'] = empty_advisory(kind).replace(
                b'190900', b'130000').replace(b'200600', b'140000').replace(b'OCT2026', b'NOV2026')
        snapshot = collect_snapshot(packet, now=AT)
        self.assertEqual(snapshot.storms, ())
