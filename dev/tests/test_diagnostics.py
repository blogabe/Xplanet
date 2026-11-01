"""Saved diagnostics distinguish requests, checks, publications and source facts."""
import copy
from dataclasses import replace
from unittest.mock import patch

from totalmarker import diagnostics, health
from totalmarker.errors import DownloadError, StorageError
from totalmarker.features.clouds import run as run_clouds
from totalmarker.features.volcano import run as run_volcano
from totalmarker.http import Fetcher
from totalmarker.state import load_state, recover_pending, validate_state
from .support import Sandbox, ScriptedTransport, image_response
from .test_volcano import NOW, cap_response


class DiagnosticsTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.settings = replace(self.config('VolcanoCheckIntervalSeconds=100\n'), log=None)

    def run_volcano(self, *responses, now=NOW):
        transport = ScriptedTransport(*responses)
        result = run_volcano(self.fs, self.settings, now=now, fetcher=Fetcher(transport))
        return result, transport.calls

    def record(self, product='volcano'):
        return self.read_state(self.settings)['products'][product]

    def test_actual_attempt_cache_check_and_failure_preserve_distinct_facts(self):
        self.run_volcano(cap_response())
        marker = self.fs.read(self.settings.volcano.marker)
        _, calls = self.run_volcano(now=NOW + 1)
        self.assertEqual(calls, [])
        cached = diagnostics.observation(self.record())
        self.assertEqual((cached['checked_at'], cached['attempted_at'],
                          cached['successful_at'], cached['published_at']),
                         (NOW + 1, NOW, NOW + 1, NOW))
        result, calls = self.run_volcano(DownloadError('HTTPS request failed'), now=NOW + 101)
        self.assertEqual(result.outcome, 'failed')
        self.assertEqual(len(calls), 1)
        failed = diagnostics.observation(self.record())
        self.assertEqual((failed['attempted_at'], failed['successful_at'], failed['published_at']),
                         (NOW + 101, NOW + 1, NOW))
        self.assertEqual(failed['last_error'], {'at': NOW + 101, 'message': 'HTTPS request failed'})
        self.assertEqual(self.fs.read(self.settings.volcano.marker), marker)
        row = next(row for row in health.check(self.fs, self.settings, now=NOW + 101)['products']
                   if row['product'] == 'volcano')
        self.assertEqual(row['last_error'], failed['last_error'])  # Logging was disabled.
        self.assertEqual(row['last_publication_at'], NOW)
        self.assertTrue(row['output']['retained'])

    def test_success_keeps_bounded_historical_error_without_logging(self):
        self.run_volcano(DownloadError(' \n '.join(['failure'] * 200)))
        error = self.record()['last_error']
        self.assertLessEqual(len(error['message']), 500)
        self.assertNotIn('\n', error['message'])
        self.run_volcano(cap_response(), now=NOW + 1)
        self.assertEqual(self.record()['last_error'], error)
        self.assertEqual(self.record()['successful_at'], NOW + 1)

    def test_truncated_error_boundary_remains_valid_for_journal_publication(self):
        self.run_volcano(DownloadError('x' * 499 + ' y'))
        record = self.record()
        self.assertEqual(record['last_error']['message'], 'x' * 499)
        validate_state(self.read_state(self.settings))

    def test_cloud_labels_do_not_become_refresh_success_or_request(self):
        fetcher = Fetcher(ScriptedTransport(image_response()))
        run_clouds(self.fs, self.settings, now=NOW, fetcher=fetcher)
        run_clouds(self.fs, self.settings, now=NOW + 1, label_only=True,
                   fetcher=Fetcher(ScriptedTransport()))
        facts = diagnostics.observation(self.record('clouds'))
        self.assertEqual((facts['checked_at'], facts['attempted_at'], facts['successful_at'],
                          facts['published_at']), (NOW + 1, NOW, NOW, NOW))

    def test_failed_cloud_fetch_does_not_turn_fetch_bookkeeping_into_success(self):
        run_clouds(self.fs, self.settings, now=NOW,
                   fetcher=Fetcher(ScriptedTransport(DownloadError('HTTPS request failed'))))
        facts = diagnostics.observation(self.record('clouds'))
        self.assertEqual(facts['attempted_at'], NOW)
        self.assertIsNone(facts['successful_at'])
        self.assertIsNone(facts['published_at'])

    def test_last_error_survives_journal_recovery_with_its_result(self):
        self.run_volcano(cap_response())
        original = self.fs.write
        def fail_state(path, data, **kwargs):
            if str(path) == self.settings.state:
                raise StorageError('simulated interruption')
            return original(path, data, **kwargs)
        with patch.object(self.fs, 'write', side_effect=fail_state):
            with self.assertRaises(StorageError):
                self.run_volcano(DownloadError('HTTPS request failed'), now=NOW + 101)
        recover_pending(self.fs, self.settings)
        record = load_state(self.fs, self.settings.state)['products']['volcano']
        self.assertEqual(record['last_outcome'], 'failed')
        self.assertEqual(record['attempted_at'], NOW + 101)
        self.assertEqual(record['last_error']['at'], NOW + 101)
        self.assertEqual(record['successful_at'], NOW)
        self.assertIsNone(self.fs.read(self.settings.volcano.journal))

    def test_bad_additive_diagnostics_are_rejected_before_publication_or_recovery(self):
        for values in ({'attempted_at': True}, {'successful_at': float('nan')},
                       {'last_error': {'at': NOW, 'message': 'x' * 501}},
                       {'last_error': {'at': -1, 'message': 'invalid'}},
                       {'last_error': {'at': NOW, 'message': 'line\nbreak'}}):
            with self.subTest(values=values), self.assertRaises(StorageError):
                validate_state({'schema': 1, 'products': {'clouds': values}})

    def test_legacy_projection_does_not_invent_attempt_or_modify_record(self):
        record = {'checked_at': NOW, 'fetched_at': NOW, 'installed_at': NOW - 1,
                  'timestamp_origin': 'legacy-label'}
        before = copy.deepcopy(record)
        facts = diagnostics.observation(record)
        self.assertIsNone(facts['attempted_at'])
        self.assertIsNone(facts['successful_at'])
        self.assertIsNone(facts['published_at'])
        self.assertEqual(record, before)
