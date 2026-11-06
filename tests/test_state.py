"""Blocked recovery retains intent and never rolls back unrelated last-good state."""
from dataclasses import replace
from unittest.mock import patch

from totalmarker.errors import StorageError
from totalmarker.features.clouds import run as clouds
from totalmarker.features.quake import run as quake
from totalmarker.state import PairPublisher, json_bytes, recover_pending
from .support import Sandbox
from .test_health import snapshot


class RecoveryBlockageTests(Sandbox):
    def test_mismatched_disabled_journal_blocks_runs_without_changing_any_bytes(self):
        settings = self.config()
        self.fs.write(settings.state, json_bytes({'schema': 1, 'products': {}}))
        self.fs.write(settings.labels, b'last-good labels')
        self.fs.write(settings.quake.marker, b'last-good quake')
        old = replace(settings, eclipse=replace(settings.eclipse, marker='markers/old-eclipse'))
        publisher = PairPublisher(self.fs, old, 'eclipse', old.eclipse.marker,
                                  old.eclipse.arc, 'marker_sha256', 'arc_sha256')
        self.fs.write(settings.eclipse.journal, json_bytes({
            'schema': 1, 'product': 'eclipse', 'paths': publisher.paths(),
            'state': {'schema': 1, 'products': {}}, 'label': None,
            'first': None, 'second': None}))
        # Establish the coordination inode before comparing retained data.
        with self.fs.lock(settings.lock):
            pass
        before = snapshot(self.root)
        with patch('totalmarker.http.HTTPTransport.request', side_effect=AssertionError('network')):
            for run, kwargs in ((clouds, {'label_only': True}), (clouds, {}), (quake, {})):
                with self.assertRaisesRegex(StorageError, 'preserve the journal.*original configuration'):
                    run(self.fs, settings, now=1700000000, **kwargs)
                self.assertEqual(snapshot(self.root), before)

    def test_multiple_pending_journals_require_inspection_and_remain_intact(self):
        settings = self.config()
        self.fs.write(settings.journal, b'cloud intent')
        self.fs.write(settings.eclipse.journal, b'eclipse intent')
        before = snapshot(self.root)
        with self.assertRaisesRegex(StorageError, 'Multiple pending.*preserve all journals'):
            recover_pending(self.fs, settings)
        self.assertEqual(snapshot(self.root), before)
