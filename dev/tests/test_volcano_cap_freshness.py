"""CAP activity coverage must remain fresh independently of fetch/sent times."""
from datetime import date, datetime, timezone
import re

from totalmarker.config import load
from totalmarker.errors import FeedError
from totalmarker.features.volcano import run
from totalmarker.http import Fetcher
from totalmarker.labels import legacy_time
from totalmarker.paths import RootFS
from totalmarker.state import json_bytes
from totalmarker.volcano_cap import coverage_end_at, parse_cap, report_period
from .support import Sandbox, ScriptedTransport
from .test_volcano import CAP11, CURRENT, NOW, cap_response, synthetic_info


class CapFreshnessTests(Sandbox):
    def invoke(self, settings, *responses, now=NOW):
        transport = ScriptedTransport(*responses)
        return run(self.fs, settings, fetcher=Fetcher(transport), now=now), transport

    def test_current_coverage_keeps_old_sent_time_and_refresh_label_semantics(self):
        settings = self.config('VolcanoCheckIntervalSeconds=0\n')
        current = CAP11.replace(b'24-30 September 2023', b'2 November-8 November 2023')
        result, _ = self.invoke(settings, cap_response(current))
        self.assertEqual(result.outcome, 'changed')
        self.assertEqual(result.source_report_at,
                         datetime.fromisoformat('2023-10-01T07:50:51-04:00').timestamp())
        self.assertEqual((result.report_period_start, result.report_period_end),
                         ('2023-11-02', '2023-11-08'))
        self.assertEqual(result.coverage_end_at,
                         datetime(2023, 11, 9, tzinfo=timezone.utc).timestamp())
        self.assertEqual(result.successful_at, NOW)
        label = self.fs.read(settings.labels)
        self.assertIn(legacy_time(NOW).encode(), label)
        self.assertIn(b'color=Green', label)

    def test_stale_http_200_with_recent_sent_time_retains_last_good(self):
        settings = self.config('VolcanoCheckIntervalSeconds=0\n')
        self.invoke(settings, cap_response())
        marker = self.fs.read(settings.volcano.marker)
        mtime = self.fs.file_stat(settings.volcano.marker).st_mtime_ns
        stale = synthetic_info(period='19 October-25 October 2023').replace(
            b'<info>', b'<sent>2023-11-14T22:13:20Z</sent><info>')
        result, _ = self.invoke(settings, cap_response(stale), now=NOW + 1)
        self.assertEqual(result.outcome, 'failed')
        self.assertIn('stale', result.message)
        self.assertEqual((result.installed_at, result.successful_at), (NOW, NOW))
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        self.assertEqual(self.fs.file_stat(settings.volcano.marker).st_mtime_ns, mtime)
        self.assertEqual(self.read_state(settings)['products']['volcano']['fetched_at'], NOW)

    def test_cache_and_304_expiry_keep_timestamp_and_age_label(self):
        settings = self.config('VolcanoCheckIntervalSeconds=3600000\n')
        first, _ = self.invoke(settings, cap_response(ETag='"week"'))
        marker = self.fs.read(settings.volcano.marker)
        expired = first.coverage_end_at + 14 * 86400 + 1
        cached, transport = self.invoke(settings, now=expired)
        self.assertEqual(transport.calls, [])
        self.assertEqual(cached.outcome, 'failed')
        self.assertEqual(cached.successful_at, NOW)
        polling = self.config('VolcanoCheckIntervalSeconds=0\n')
        result, transport = self.invoke(polling, cap_response(status=304), now=expired + 1)
        self.assertEqual(result.outcome, 'failed')
        self.assertEqual(transport.calls[0][1]['If-None-Match'], '"week"')
        self.assertEqual((result.installed_at, result.successful_at), (NOW, NOW))
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        self.assertEqual(self.read_state(settings)['products']['volcano']['fetched_at'], NOW)
        label = self.fs.read(settings.labels)
        self.assertIn(legacy_time(NOW).encode(), label)
        self.assertIn(b'color=Red', label)

    def test_missing_malformed_duplicate_and_conflicting_periods_retain_outputs(self):
        settings = self.config('VolcanoCheckIntervalSeconds=0\n')
        self.invoke(settings, cap_response())
        marker = self.fs.read(settings.volcano.marker)
        missing = re.sub(rb'<headline>.*?</headline>', b'', CURRENT)
        conflicting = CURRENT.replace(b'2 November-8 November 2023',
                                      b'26 October-1 November 2023', 1)
        duplicate = CURRENT.replace(b'</headline>', b'</headline><headline>2-8 November 2023</headline>', 1)
        ambiguous = CURRENT.replace(b'2 November-8 November 2023',
                                    b'2-8 November 2023 and 26 October-1 November 2023', 1)
        for body in [missing, conflicting, duplicate, ambiguous,
                     synthetic_info(period='2 November-9 November 2023'),
                     synthetic_info(period='31 February-6 March 2023'),
                     synthetic_info(period='2 Nowember-8 November 2023'),
                     synthetic_info(period='UNKNOWN')]:
            with self.subTest(body=body[:80]):
                result, _ = self.invoke(settings, cap_response(body), now=NOW + 1)
                self.assertEqual(result.outcome, 'failed')
                self.assertEqual(result.successful_at, NOW)
                self.assertEqual(self.fs.read(settings.volcano.marker), marker)

    def test_cap_has_same_exact_utc_expiry_and_future_boundaries_as_html(self):
        cutoff = datetime(2023, 11, 9, tzinfo=timezone.utc).timestamp()
        for index, (now, expected) in enumerate([
                (cutoff + 14 * 86400, 'changed'),
                (cutoff + 14 * 86400 + 1, 'failed'),
                (cutoff - 3600, 'changed'),
                (cutoff - 3601, 'failed')]):
            with self.subTest(now=now):
                root = self.base / f'boundary-{index}'
                root.mkdir()
                fs = RootFS(root)
                (root / 'config.ini').write_text(
                    'CloudProvider=custom\nCloudURL=https://cloud.example.invalid/map.jpg\n')
                settings = load(fs, 'config.ini')
                result = run(fs, settings, fetcher=Fetcher(ScriptedTransport(cap_response())),
                             now=now)
                self.assertEqual(result.outcome, expected)
                if expected == 'failed':
                    self.assertIsNone(result.successful_at)
                    self.assertIsNone(fs.read(settings.volcano.marker))

    def test_old_cache_without_coverage_requires_fresh_body_not_304(self):
        settings = self.config('VolcanoCheckIntervalSeconds=3600000\n')
        self.invoke(settings, cap_response(ETag='"old-week"'))
        state = self.read_state(settings)
        record = state['products']['volcano']
        record['source_key'] = '0' * 64  # Unrecognized pre-upgrade parser identity.
        for key in ['coverage_end_at', 'report_period_start', 'report_period_end']:
            record.pop(key)
        self.fs.write(settings.state, json_bytes(state))
        result, transport = self.invoke(settings, cap_response(status=304), now=NOW + 1)
        self.assertEqual(result.outcome, 'failed')
        self.assertNotIn('If-None-Match', transport.calls[0][1])
        self.assertNotIn('If-Modified-Since', transport.calls[0][1])
        self.assertEqual(result.successful_at, NOW)
        result, transport = self.invoke(settings, cap_response(), now=NOW + 2)
        self.assertEqual(result.outcome, 'unchanged')
        self.assertNotIn('If-None-Match', transport.calls[0][1])
        self.assertNotIn('If-Modified-Since', transport.calls[0][1])
        self.assertEqual(result.report_period_end, '2023-11-08')

    def test_report_period_supports_same_month_leap_day_and_year_rollover(self):
        for text, start, end in [
                ('24-30 September 2023', date(2023, 9, 24), date(2023, 9, 30)),
                ('23 February–29 February 2024', date(2024, 2, 23), date(2024, 2, 29)),
                ('26 December-1 January 2026', date(2025, 12, 26), date(2026, 1, 1)),
                ('26 December 2025-1 January 2026', date(2025, 12, 26), date(2026, 1, 1))]:
            with self.subTest(text=text):
                self.assertEqual(report_period(text), (start, end))
                events = parse_cap(synthetic_info(period=text))
                self.assertEqual((events[0].period_start, events[0].period_end), (start, end))
                self.assertEqual(datetime.fromtimestamp(coverage_end_at(end), timezone.utc).hour, 0)
        with self.assertRaises(FeedError):
            report_period('24-30 September 2023 and 1-7 October 2023')
