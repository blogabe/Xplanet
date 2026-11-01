"""Health probes reuse product validators without changing the installation."""
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from totalmarker import health
from totalmarker.cli import main
from totalmarker.errors import DownloadError
from totalmarker.features.volcano import run as run_volcano
from totalmarker.http import Fetcher, Response
from totalmarker.state import json_bytes
from .support import Sandbox, ScriptedTransport, image_response
from .test_volcano import NOW, cap_response, synthetic_info


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def rows(report):
    return {row['product']: row for row in report['products']}


class HealthTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.settings = self.config('VolcanoCheckIntervalSeconds=0\n')

    def live(self, factory):
        before = snapshot(self.root)
        roots = []
        original_temporary = tempfile.TemporaryDirectory
        def temporary(*args, **kwargs):
            directory = original_temporary(*args, **kwargs)
            roots.append(Path(directory.name).resolve())
            return directory
        with patch('totalmarker.health.tempfile.TemporaryDirectory', side_effect=temporary):
            report = health.check(self.fs, self.settings, live=True, now=NOW,
                                  fetcher_factory=factory)
        self.assertTrue(all(not root.exists() for root in roots))
        self.assertEqual(snapshot(self.root), before)
        return rows(report)

    def test_saved_health_never_fetches_writes_or_resolves_credentials(self):
        with patch('totalmarker.http.HTTPTransport.request', side_effect=AssertionError('network')):
            before = snapshot(self.root)
            report = health.check(self.fs, self.settings, now=NOW)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(rows(report)['volcano']['status'], 'unknown')
        self.assertEqual(rows(report)['volcano']['sources'], [self.settings.volcano.url])
        self.assertEqual(rows(report)['norad']['status'], 'disabled')
        self.assertIsNone(rows(report)['clouds']['last_attempt_at'])
        self.assertEqual(health.exit_status(report), 0)
        missing_auth = replace(self.settings, auth=replace(self.settings.auth, mode='basic'))
        with patch.object(type(missing_auth.auth), 'resolve', side_effect=AssertionError('credentials')):
            health.check(self.fs, missing_auth, now=NOW)
        self.fs.write(self.settings.state, json_bytes({'schema': 1, 'products': {
            'clouds': {'installed_at': NOW, 'timestamp_origin': 'legacy-label'}}}))
        before = snapshot(self.root)
        report = health.check(self.fs, self.settings, now=NOW)
        self.assertIsNone(rows(report)['clouds']['last_success_at'])
        self.assertEqual(snapshot(self.root), before)

    def test_saved_dates_last_error_and_retained_output_are_explicit(self):
        run_volcano(self.fs, self.settings, fetcher=Fetcher(ScriptedTransport(cap_response())), now=NOW)
        state = json.loads(self.fs.read(self.settings.state))
        state['products']['volcano']['last_outcome'] = 'failed'
        self.fs.write(self.settings.state, json_bytes(state))
        self.fs.append(self.settings.log, b'not json\n' + (json.dumps({
            'feature': 'volcano', 'outcome': 'failed', 'time': NOW + 1, 'message': 'Source returned HTTP 403'}) + '\n').encode())
        before = snapshot(self.root)
        report = health.check(self.fs, self.settings, now=NOW + 2)
        row = rows(report)['volcano']
        self.assertEqual(row['last_error']['message'], 'Source returned HTTP 403')
        self.assertEqual(row['last_success_at'], NOW)
        self.assertIsNone(row['last_attempt_at'])  # checked_at is not an HTTP attempt.
        self.assertEqual(row['coverage']['report_period_end'], '2023-11-08')
        self.assertEqual(row['output'], {'present': True, 'verified': True, 'retained': True})
        self.assertEqual(snapshot(self.root), before)
        expired = health.check(self.fs, self.settings, now=NOW + 30 * 86400)
        self.assertEqual(rows(expired)['volcano']['status'], 'stale')
        self.assertTrue(rows(expired)['volcano']['output']['retained'])
        self.assertEqual(health.exit_status(expired), 1)

    def test_saved_missing_or_edited_output_is_not_claimed_verified(self):
        run_volcano(self.fs, self.settings, fetcher=Fetcher(ScriptedTransport(cap_response())), now=NOW)
        self.fs.write(self.settings.volcano.marker, b'user edited marker')
        row = rows(health.check(self.fs, self.settings, now=NOW))['volcano']
        self.assertTrue(row['output']['present'])
        self.assertFalse(row['output']['verified'])
        self.assertEqual(row['status'], 'unknown')

    def test_live_valid_stale_invalid_and_access_failures_use_real_cap_validator(self):
        run_volcano(self.fs, self.settings, fetcher=Fetcher(ScriptedTransport(cap_response())), now=NOW - 1)
        for response, expected in [
                (cap_response(), 'healthy'),
                (cap_response(synthetic_info(period='19 October-25 October 2023')), 'stale'),
                (cap_response(b'<alerts/>'), 'invalid_content'),
                (cap_response(synthetic_info(period='23 November-29 November 2023')), 'invalid_content'),
                (Response(403, {}), 'access_failed'),
                (DownloadError('HTTPS request failed'), 'access_failed')]:
            with self.subTest(expected=expected):
                factory = lambda: Fetcher(ScriptedTransport(response))
                row = self.live(factory)['volcano']
                self.assertEqual(row['status'], expected)
                self.assertEqual(row['probe_attempt_at'], NOW)
                if expected == 'healthy':
                    self.assertEqual(row['probe_coverage']['report_period_end'], '2023-11-08')
                    self.assertEqual(row['message'],
                                     'Isolated probe validated source content; normal output unchanged')
                    self.assertNotIn('published', json.dumps(row).lower())
                    self.assertIn(row['message'], health.format_report({
                        'mode': 'live', 'checked_at': NOW, 'products': [row], 'warning': None}, verbose=True))
                else:
                    self.assertTrue(row['output']['retained'])
                    self.assertEqual(row['message'], row['last_error']['message'])

    def test_live_cloud_unknown_creation_date_is_valid_but_not_current(self):
        report = self.live(lambda: Fetcher(ScriptedTransport(image_response(b'no creation metadata'))))
        self.assertEqual(report['clouds']['content'], 'valid')
        self.assertEqual(report['clouds']['access'], 'ok')
        self.assertEqual(report['clouds']['freshness'], 'unknown')
        self.assertEqual(report['clouds']['status'], 'unknown')

    def test_live_empty_quake_feed_is_legitimate_no_events(self):
        body = json.dumps({'type': 'FeatureCollection', 'metadata': {'generated': NOW * 1000},
                           'features': []}).encode()
        report = self.live(lambda: Fetcher(ScriptedTransport(Response(200, {'content-type': 'application/json'}, body))))
        self.assertEqual(report['quake']['status'], 'no_events')
        self.assertEqual(report['quake']['count'], 0)
        self.assertEqual(report['quake']['freshness'], 'unknown')

    def test_live_probe_cleans_up_temporary_outputs_and_handles_internal_failure(self):
        roots = []
        def fail(fs, settings, **kwargs):
            roots.append(fs.root)
            fs.write(settings.image, b'temporary probe bytes')
            raise RuntimeError('PRIVATE_EXCEPTION')
        with patch.dict(health.RUNNERS, {'clouds': fail}):
            report = self.live(lambda: Fetcher(ScriptedTransport(Response(403, {}))))
        self.assertEqual(report['clouds']['status'], 'error')
        self.assertNotIn('PRIVATE_EXCEPTION', json.dumps(report))
        self.assertTrue(roots)
        self.assertTrue(all(not root.exists() for root in roots))

    def test_disabled_optional_sources_and_norad_cooldown_are_not_probed(self):
        self.settings = replace(self.settings, norad=replace(self.settings.norad, enabled=True))
        self.fs.write(self.settings.state, json_bytes({'schema': 1, 'products': {
            'norad': {'attempted_at': NOW - 1}}}))
        called = []
        def factory():
            called.append(True)
            return Fetcher(ScriptedTransport(Response(403, {})))
        report = self.live(factory)
        self.assertEqual(len(called), 4)
        self.assertEqual(report['norad']['access'], 'not_checked')
        self.assertIn('interval', report['norad']['message'])
        self.assertEqual(report['eclipse']['status'], 'disabled')

    def test_santa_without_provider_is_unsupported(self):
        self.settings = replace(self.settings, santa=replace(self.settings.santa, enabled=True))
        report = health.check(self.fs, self.settings, now=NOW)
        self.assertEqual(rows(report)['santa']['status'], 'unsupported')

    def test_cli_human_json_exit_codes_and_invalid_state_do_not_write(self):
        def invoke(*extra):
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(['--root', str(self.root), '--config', 'config.ini', 'health', *extra])
            return code, output.getvalue()
        before = snapshot(self.root)
        code, text = invoke()
        self.assertEqual(code, 0)
        self.assertIn('TotalMarker saved status (no network check)', text)
        self.assertIn('Volcanoes: no saved output; no successful refresh recorded', text)
        code, text = invoke('--json')
        self.assertEqual(json.loads(text)['mode'], 'saved')
        self.assertEqual(snapshot(self.root), before)
        code, text = invoke('--verbose')
        self.assertEqual(code, 0)
        self.assertIn('Details:', text)
        self.assertIn(self.settings.volcano.url, text)
        self.assertEqual(snapshot(self.root), before)
        with patch('totalmarker.health.time.time', return_value=NOW):
            plain_code, plain_json = invoke('--json')
            verbose_code, verbose_json = invoke('--json', '--verbose')
        self.assertEqual((verbose_code, verbose_json), (plain_code, plain_json))
        self.fs.write(self.settings.state, b'{"schema":999,"products":{}}')
        before = snapshot(self.root)
        code, text = invoke('--json')
        self.assertEqual(code, 2)
        self.assertIn('Unsupported or invalid persistent state', json.loads(text)['message'])
        self.assertEqual(snapshot(self.root), before)

    def test_cli_live_failure_exit_status_is_one(self):
        output = io.StringIO()
        with patch('totalmarker.http.HTTPTransport.request', return_value=Response(403, {})), redirect_stdout(output):
            before = snapshot(self.root)
            code = main(['--root', str(self.root), '--config', 'config.ini', 'health', '--live', '--json'])
        self.assertEqual(code, 1)
        self.assertEqual(rows(json.loads(output.getvalue()))['volcano']['status'], 'access_failed')
        self.assertEqual(snapshot(self.root), before)

        def broken_probe(*args, **kwargs):
            raise RuntimeError('PRIVATE')
        with (patch.dict(health.RUNNERS, {'clouds': broken_probe}),
              patch('totalmarker.http.HTTPTransport.request', return_value=Response(403, {})),
              redirect_stdout(io.StringIO()) as failure_output):
            code = main(['--root', str(self.root), '--config', 'config.ini', 'health', '--live', '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(rows(json.loads(failure_output.getvalue()))['clouds']['status'], 'error')
        self.assertNotIn('PRIVATE', failure_output.getvalue())
        self.assertEqual(snapshot(self.root), before)
