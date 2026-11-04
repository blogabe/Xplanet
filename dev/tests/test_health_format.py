"""Human summaries distinguish saved evidence from live validation."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from totalmarker.cli import main
import unittest

from totalmarker.health import exit_status, format_report, format_dashboard

NOW = 1793509200


def product(name, **changes):
    row = {'product': name, 'sources': ['https://example.invalid/feed'],
           'status': 'unknown', 'access': 'not_checked', 'content': 'unknown',
           'freshness': 'unknown', 'last_check_at': NOW - 60,
           'last_attempt_at': None, 'last_success_at': NOW - 3600,
           'last_publication_at': NOW - 7200,
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
        self.assertIn('success 2026-11-01 04:00Z; publication 2026-11-01 03:00Z', verbose)
        self.assertNotIn('publication', format_report(saved))

    def test_source_colors_follow_saved_and_live_facts_without_changing_text(self):
        saved = report('saved', product('clouds', freshness='current'), product('quake'),
                       product('storm', status='stale', freshness='stale'),
                       product('volcano', status='stale', freshness='stale', last_outcome='failed'),
                       product('norad', status='disabled'))
        text = format_report(saved, color=True)
        self.assertIn('\033[32mClouds\033[0m: saved output current', text)
        self.assertIn('\nEarthquakes: saved output; freshness not assessed', text)
        self.assertIn('\033[33mStorms\033[0m:', text)
        self.assertIn('\033[31mVolcanoes\033[0m:', text)
        self.assertIn('\033[2mDisabled: Satellites\033[0m', text)
        self.assertNotIn('\033[', format_report(saved))
        live = report('live', product('clouds', status='access_failed', access='failed'),
                      product('volcano', status='healthy', content='valid', freshness='current',
                              last_outcome='failed'))
        text = format_report(live, color=True)
        self.assertIn('\033[31mClouds\033[0m:', text)
        self.assertIn('\033[32mVolcanoes\033[0m:', text)
        self.assertEqual(exit_status(saved), 1)
        self.assertEqual(exit_status(live), 1)

    def test_cli_colors_only_terminal_text_and_preserves_json_and_no_color(self):
        saved = report('saved', product('clouds', freshness='current'))
        class Output(io.StringIO):
            terminal = True
            def isatty(self):
                return self.terminal
        cases = [(True, {'TERM': 'xterm'}, False, True),
                 (False, {'TERM': 'xterm'}, False, False),
                 (True, {'TERM': 'xterm', 'NO_COLOR': ''}, False, False),
                 (True, {'TERM': 'dumb'}, False, False),
                 (True, {'TERM': 'xterm'}, True, False)]
        with tempfile.TemporaryDirectory() as root:
            for tty, env, as_json, colored in cases:
                output = Output()
                output.terminal = tty
                with (patch('totalmarker.cli.load', return_value=object()),
                      patch('totalmarker.cli.check_health', return_value=saved),
                      patch('sys.stdout', output), patch.dict(os.environ, env, clear=True)):
                    status = main(['--root', str(Path(root).resolve()), 'health', *(['--json'] if as_json else [])])
                self.assertEqual(status, 0, output.getvalue())
                self.assertEqual('\033[' in output.getvalue(), colored)
                if as_json:
                    self.assertEqual(json.loads(output.getvalue()), saved)

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


class DashboardFormatTests(unittest.TestCase):
    def test_dashboard_uses_shared_semantics_and_never_exposes_provider_paths(self):
        rows=[product('clouds',freshness='current'),product('quake'),
              product('storm',freshness='stale'),product('volcano',last_outcome='failed',last_error={'at':NOW,'message':'secret-path; hidden'}),
              product('norad',status='disabled')]
        data=format_dashboard(report('saved',*rows))
        self.assertIn('snapshot\t2026-',data)
        self.assertIn('good\tClouds\tsaved output current',data)
        self.assertIn('unknown\tEarthquakes\tsaved output; freshness not assessed',data)
        self.assertIn('warning\tStorms\tsaved data stale',data)
        self.assertIn('error\tVolcanoes\trefresh failed',data)
        self.assertIn('disabled\tSatellites\tdisabled',data)
        self.assertIn('secret-path',data);self.assertNotIn('example.invalid',data);self.assertNotIn('\033',data)
        warned=report('saved',*rows);warned['warning']='log unreadable\n\033 problem'
        note=format_dashboard(warned).splitlines()[-1]
        self.assertTrue(note.startswith('note\t'));self.assertNotIn('\033',note)
        with self.assertRaises(ValueError):format_dashboard(report('live',*rows))

    def test_dashboard_flag_cannot_be_combined_with_live_json_or_nonhealth(self):
        for argv in (['health','--dashboard','--live'],['health','--dashboard','--json'],['clouds','--dashboard']):
            with self.subTest(argv=argv),patch('sys.stderr',io.StringIO()),self.assertRaises(SystemExit):main(['--root','/unused',*argv])
