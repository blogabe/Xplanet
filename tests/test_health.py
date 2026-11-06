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
from totalmarker.features.storm import run as run_storm, REJECT_CAPTURE
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
        self.assertEqual(row['last_attempt_at'], NOW)  # Actual request provenance is saved.
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
        self.assertEqual(report['quake']['freshness'], 'current')

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

    def test_live_rejected_storm_capture_stays_inside_disposable_probe(self):
        # Keep normal evidence byte-for-byte intact while proving the real
        # failing runner creates bounded evidence only inside its probe root.
        original_capture = b'{"existing": "normal rejection evidence"}\n'
        self.fs.write(REJECT_CAPTURE, original_capture)
        captures = []
        def observed_run(fs, settings, **kwargs):
            result = run_storm(fs, settings, **kwargs)
            raw = fs.read(REJECT_CAPTURE)
            self.assertIsNotNone(raw)
            self.assertLessEqual(len(raw), 384 * 1024)
            data = json.loads(raw)
            self.assertEqual(data['responses'][0]['source'], 'nhc/CurrentStorms.json')
            self.assertEqual(data['responses'][0]['bytes'], len(b'not-json'))
            captures.append(fs.root)
            self.assertNotEqual(fs.root, self.root)
            return result
        with patch.dict(health.RUNNERS, {'storm': observed_run}):
            report = self.live(lambda: Fetcher(ScriptedTransport(Response(200, {}, b'not-json'))))
        self.assertEqual(report['storm']['status'], 'invalid_content')
        self.assertEqual(report['storm']['message'], 'Storm NHC active index is invalid JSON')
        self.assertTrue(captures)
        self.assertTrue(all(not root.exists() for root in captures))
        self.assertEqual(self.fs.read(REJECT_CAPTURE), original_capture)

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
        self.assertIn('last_publication_at', json.loads(text)['products'][0])
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


    def test_oversize_saved_cloud_is_a_per_product_error_in_saved_and_live_modes(self):
        self.settings = replace(self.settings, max_bytes=1024)
        self.fs.write(self.settings.image, b'x' * 1025)
        for live in (False, True):
            before = snapshot(self.root)
            report = health.check(self.fs, self.settings, live=live, now=NOW,
                                  fetcher_factory=lambda: Fetcher(ScriptedTransport(Response(403, {}))))
            products = rows(report)
            self.assertEqual(len(products), 7)
            self.assertEqual(products['clouds']['status'], 'error')
            self.assertTrue(products['clouds']['output']['present'])
            self.assertFalse(products['clouds']['output']['verified'])
            self.assertIn('size limit', products['clouds']['output']['error'])
            self.assertIn('Clouds: saved output unreadable', health.format_report(report))
            self.assertEqual(products['quake']['status'], 'access_failed' if live else 'unknown')
            self.assertEqual(health.exit_status(report), 2)
            self.assertEqual(snapshot(self.root), before)

    def test_disabled_product_unreadable_output_does_not_abort_other_rows(self):
        from totalmarker.errors import StorageError
        original = self.fs.read
        def read(path, *args, **kwargs):
            if path == self.settings.norad.satellite:
                raise StorageError('Contained file read failed')
            return original(path, *args, **kwargs)
        before = snapshot(self.root)
        with patch.object(self.fs, 'read', side_effect=read):
            report = health.check(self.fs, self.settings, now=NOW)
        self.assertEqual(len(report['products']), 7)
        self.assertEqual(rows(report)['norad']['status'], 'error')
        self.assertEqual(rows(report)['quake']['status'], 'unknown')
        self.assertIn('Satellites: saved output unreadable', health.format_report(report))
        self.assertEqual(health.exit_status(report), 2)
        self.assertEqual(snapshot(self.root), before)

    def test_saved_failed_refresh_is_nonzero_until_an_actual_success(self):
        for product in ('clouds', 'quake', 'storm', 'volcano', 'norad', 'eclipse'):
            settings = self.settings
            if product in ('norad', 'eclipse'):
                settings = replace(settings, **{product: replace(getattr(settings, product), enabled=True)})
            self.fs.write(settings.state, json_bytes({'schema': 1, 'products': {product: {
                'successful_at': NOW - 100, 'last_outcome': 'failed',
                'last_error': {'at': NOW - 1, 'message': 'Source unavailable'}}}}))
            before = snapshot(self.root)
            report = health.check(self.fs, settings, now=NOW)
            self.assertEqual(rows(report)[product]['status'], 'refresh_failed')
            self.assertEqual(health.exit_status(report), 1)
            self.assertIn('refresh failed', health.format_report(report))
            self.assertEqual(snapshot(self.root), before)
        # A completed isolated live probe reports its own result, not the saved failure.
        report = health.check(self.fs, settings, live=True, now=NOW,
                              fetcher_factory=lambda: Fetcher(ScriptedTransport(Response(403, {}))))
        self.assertEqual(rows(report)['eclipse']['status'], 'access_failed')

    def test_pending_disabled_publication_is_visible_without_replaying_it(self):
        self.fs.write(self.settings.eclipse.journal, b'preserve even an invalid journal')
        before = snapshot(self.root)
        report = health.check(self.fs, self.settings, now=NOW)
        self.assertEqual(rows(report)['eclipse']['status'], 'error')
        self.assertIn('original configuration', rows(report)['eclipse']['recovery_error'])
        self.assertIn('publication recovery required', health.format_report(report))
        self.assertIn('  publication recovery: Pending publication requires recovery',
                      health.format_report(report, verbose=True))
        self.assertEqual(health.exit_status(report), 2)
        self.assertEqual(snapshot(self.root), before)

    def test_one_live_probe_setup_error_does_not_hide_other_products(self):
        from totalmarker.errors import StorageError
        original = health._live
        def probe(fs, settings, product, *args):
            if product == 'quake':
                raise StorageError('Contained file read failed')
            return original(fs, settings, product, *args)
        before = snapshot(self.root)
        with patch('totalmarker.health._live', side_effect=probe):
            report = health.check(self.fs, self.settings, live=True, now=NOW,
                                  fetcher_factory=lambda: Fetcher(ScriptedTransport(Response(403, {}))))
        self.assertEqual(rows(report)['quake']['status'], 'error')
        self.assertEqual(rows(report)['clouds']['status'], 'access_failed')
        self.assertEqual(len(report['products']), 7)
        self.assertEqual(snapshot(self.root), before)


class FreshnessPolicyTests(Sandbox):
    def setUp(self):
        super().setUp();self.settings=self.config();self.now=1700000000

    def test_quake_uses_generation_and_original_refresh_policy_not_event_or_success_time(self):
        settings=replace(self.settings,quake=replace(self.settings.quake,interval=3600))
        record={'feed_generated_at':self.now-1800,'latest_origin_at':1,'successful_at':self.now}
        self.assertEqual(health._freshness('quake',record,settings,self.now),'current')
        for age,expected in ((7200,'current'),(7201,'stale'),(-60,'current'),(-61,'unknown')):
            record['feed_generated_at']=self.now-age
            self.assertEqual(health._freshness('quake',record,settings,self.now),expected)
        for generated in (None,float('nan'),True):
            record['feed_generated_at']=generated
            self.assertEqual(health._freshness('quake',record,settings,self.now),'unknown')
        self.assertEqual(health.observational_freshness('quake',{'feed_generated_at':self.now},self.now),'unknown')

    def test_quake_zero_interval_keeps_five_minute_floor(self):
        settings=replace(self.settings,quake=replace(self.settings.quake,interval=0))
        for age,expected in ((300,'current'),(301,'stale')):
            self.assertEqual(health._freshness('quake',{'feed_generated_at':self.now-age},settings,self.now),expected)

    def test_empty_live_quake_feed_does_not_mask_stale_generation(self):
        body=json.dumps({'type':'FeatureCollection','metadata':{'generated':(self.now-5000)*1000},'features':[]}).encode()
        before=snapshot(self.root)
        report=health.check(self.fs,self.settings,live=True,now=self.now,
            fetcher_factory=lambda:Fetcher(ScriptedTransport(Response(200,{'content-type':'application/json'},body))))
        quake_row=rows(report)['quake']
        self.assertEqual(quake_row['count'],0);self.assertEqual(quake_row['freshness'],'stale')
        self.assertEqual(quake_row['status'],'stale');self.assertEqual(snapshot(self.root),before)

    def test_eclipse_event_phase_is_distinct_from_display_and_failure(self):
        record={'start_at':self.now,'end_at':self.now+120,'active':False}
        for when,phase in ((self.now-1,'upcoming'),(self.now,'active'),(self.now+120,'active'),(self.now+121,'ended')):
            event=health.eclipse_relevance(record,when)
            self.assertEqual(event['phase'],phase);self.assertEqual(event['overlay'],'hidden')
        self.assertEqual(health.eclipse_relevance({},self.now)['phase'],'unknown')

    def test_saved_norad_revalidates_real_cached_tles_without_network_or_writes(self):
        from tests.test_norad import SAMPLE, EPOCH
        from totalmarker.features.norad import run as update
        settings=replace(self.settings,norad=replace(self.settings.norad,enabled=True,catalog_ids=(25544,)))
        # The standard fixture epoch and deterministic time are shared with its producer tests.
        when = EPOCH + 100
        update(self.fs,settings,now=when,fetcher=Fetcher(ScriptedTransport(Response(200,{},SAMPLE))))
        before=snapshot(self.root)
        with patch('totalmarker.http.HTTPTransport.request',side_effect=AssertionError('network')):
            report=health.check(self.fs,settings,now=when)
            row=rows(report)['norad'];self.assertEqual(row['freshness'],'current')
            later=health.check(self.fs,settings,now=when+settings.norad.max_age+2*86400)
            self.assertEqual(rows(later)['norad']['freshness'],'stale')
        self.assertEqual(snapshot(self.root),before)

    def test_live_quake_uses_original_interval_and_saved_failure_remains_red(self):
        from totalmarker.features.quake import run as update
        settings=replace(self.settings,quake=replace(self.settings.quake,interval=3600))
        body=json.dumps({'type':'FeatureCollection','metadata':{'generated':(self.now-1800)*1000},'features':[]}).encode()
        def client():return Fetcher(ScriptedTransport(Response(200,{'content-type':'application/json'},body)))
        live=rows(health.check(self.fs,settings,live=True,now=self.now,fetcher_factory=client))['quake']
        self.assertEqual(live['freshness'],'current')
        update(self.fs,settings,now=self.now,fetcher=client())
        before=snapshot(self.root)
        saved=rows(health.check(self.fs,settings,now=self.now))['quake']
        self.assertEqual(saved['freshness'],'current');self.assertEqual(saved['freshness_tolerance_seconds'],7200)
        changed=replace(settings,quake=replace(settings.quake,minimum=7))
        self.assertEqual(rows(health.check(self.fs,changed,now=self.now))['quake']['freshness'],'unknown')
        self.assertEqual(snapshot(self.root),before)
        state=json.loads(self.fs.read(settings.state));state['products']['quake']['last_outcome']='failed'
        self.fs.write(settings.state,json_bytes(state))
        failed=rows(health.check(self.fs,settings,now=self.now))['quake']
        self.assertEqual(failed['freshness'],'current');self.assertEqual(failed['status'],'refresh_failed')
        self.assertEqual(health._report_tone(failed,False),'error')

    def test_saved_norad_epoch_metadata_alone_cannot_establish_current(self):
        settings=replace(self.settings,norad=replace(self.settings.norad,enabled=True))
        record={'oldest_epoch_at':self.now,'source_key':'not-matching'}
        self.assertEqual(health.saved_norad_freshness(self.fs,settings,record,{'verified':True},self.now),'unknown')
        self.assertEqual(health.saved_norad_freshness(self.fs,settings,record,{'verified':False},self.now),'unknown')
        record['oldest_epoch_at']=self.now+86401
        self.assertEqual(health.saved_norad_freshness(self.fs,settings,record,{'verified':True},self.now),'unknown')
