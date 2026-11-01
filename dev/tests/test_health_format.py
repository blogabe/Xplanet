"""Human summaries distinguish saved evidence from live validation."""
from copy import deepcopy
import unittest

from totalmarker.health import exit_status, format_report

NOW = 1793509200


def product(name, **changes):
    row = {'product': name, 'sources': ['https://example.invalid/feed'],
           'status': 'unknown', 'access': 'not_checked', 'content': 'unknown',
           'freshness': 'unknown', 'last_check_at': NOW - 60,
           'last_attempt_at': None, 'last_success_at': NOW - 3600,
           'last_outcome': 'changed', 'source_at': None,
           'coverage': {'report_period_start': None, 'report_period_end': None,
                        'coverage_end_at': None}, 'last_error': None, 'count': None,
           'output': {'present': True, 'verified': True, 'retained': False}}
    row.update(changes)
    return row


def report(mode, *rows):
    return {'mode': mode, 'checked_at': NOW, 'warning': None, 'products': list(rows)}


class HealthFormatTests(unittest.TestCase):
    def test_saved_summary_is_compact_and_never_claims_live_access(self):
        saved = report('saved', product('clouds', freshness='current'), product('quake'),
                       product('storm', freshness='current', last_error={
                           'at': NOW - 7200, 'message': 'Old contradictory JTWC source'}),
                       product('volcano'),
                       *(product(name, status='disabled') for name in ('norad', 'eclipse', 'santa')))
        before = deepcopy(saved)
        self.assertEqual(format_report(saved), '''TotalMarker saved status (no network check)
Clouds: saved output current; last success 1h ago
Earthquakes: saved output; freshness not assessed; last success 1h ago
Storms: saved output current; last success 1h ago
Volcanoes: saved output; freshness not assessed; last success 1h ago
Disabled: Satellites, Eclipses, Santa''')
        self.assertEqual(saved, before)
        self.assertEqual(exit_status(saved), 0)
        verbose = format_report(saved, verbose=True)
        self.assertIn('https://example.invalid/feed', verbose)
        self.assertIn('before last success: Old contradictory JTWC source', verbose)
        self.assertNotIn('recovered', verbose)

    def test_live_valid_quake_and_stale_volcano_remain_truthful(self):
        live = report('live', product('quake', access='ok', content='valid'),
                      product('storm', access='ok', content='valid', status='healthy', freshness='current',
                              last_error={'at': NOW - 7200, 'message': 'Old HTTP 403; Server: hidden'}),
                      product('volcano', access='ok', content='invalid', status='stale', freshness='stale',
                              message='GVP weekly reporting period is stale',
                              output={'present': True, 'verified': True, 'retained': True}))
        before = deepcopy(live)
        self.assertEqual(format_report(live), '''TotalMarker live check (normal output unchanged)
Earthquakes: validation passed; freshness not assessed; last success 1h ago
Storms: validation passed; current; last success 1h ago
Volcanoes: reachable; report parsed; coverage stale; last success 1h ago; prior output retained''')
        self.assertEqual(live, before)  # JSON statuses/content remain unchanged.
        self.assertEqual(exit_status(live), 1)
        self.assertNotIn('Old HTTP', format_report(live))
        self.assertIn('content invalid; freshness stale', format_report(live, verbose=True))

    def test_current_failure_has_short_detail_and_verbose_keeps_headers(self):
        error = {'at': NOW - 30, 'message': 'Source returned HTTP 403; Server: example; Retry-After: 60'}
        saved = report('saved', product('volcano', last_outcome='failed', last_error=error,
                                       output={'present': True, 'verified': True, 'retained': True}))
        self.assertEqual(format_report(saved), '''TotalMarker saved status (no network check)
Volcanoes: refresh failed; last success 1h ago — Source returned HTTP 403; prior output retained''')
        self.assertIn(error['message'], format_report(saved, verbose=True))
        # An undated log entry does not prove it describes the current failure.
        saved['products'][0]['last_error']['at'] = None
        self.assertNotIn('HTTP 403', format_report(saved))

    def test_missing_data_no_events_and_unprobed_sources(self):
        live = report('live', product('quake', access='ok', content='valid', status='no_events', count=0),
                      product('norad', message='Saved NORAD provider interval has not elapsed; no probe attempted',
                              last_success_at=None))
        text = format_report(live)
        self.assertIn('Earthquakes: validation passed; no events;', text)
        self.assertIn('Satellites: not probed; no successful refresh recorded', text)
        saved = report('saved', product('clouds', last_success_at=None,
                                        output={'present': False, 'verified': False, 'retained': False}))
        self.assertIn('Clouds: no saved output; no successful refresh recorded', format_report(saved))
        self.assertEqual(exit_status(live), 0)

    def test_saved_stale_coverage_and_current_live_error(self):
        saved = report('saved', product('volcano', freshness='stale', status='stale', last_outcome='failed'))
        self.assertIn('Volcanoes: coverage stale;', format_report(saved))
        live = report('live', product('clouds', status='access_failed', access='failed',
                                     message='Source returned HTTP 403; Server: example'))
        self.assertIn('Clouds: access failed; last success 1h ago — Source returned HTTP 403', format_report(live))
        self.assertNotIn('Server:', format_report(live))
        self.assertEqual(exit_status(live), 1)
