"""Inspect the next-start selection without assuming a live renderer or editing it."""
from pathlib import Path
import unittest
from unittest.mock import patch
from tests.configurator import test_scene_selection as fixtures
from configurator.selection_info import inspect_selected
from configurator.selection import inspect_selection,SELECTOR,REVISIONS


class SelectedInfoTests(unittest.TestCase):
    setUp=fixtures.SceneSelectionTests.setUp
    setUp_fixture=fixtures.SceneSelectionTests.setUp_fixture
    plan=fixtures.SceneSelectionTests.plan
    apply=fixtures.SceneSelectionTests.apply
    preserved=fixtures.SceneSelectionTests.preserved

    def test_legacy_inspection_does_not_read_or_execute_personal_definitions(self):
        from configurator import selection_info
        with patch.object(selection_info,'open_view',side_effect=AssertionError('must not load legacy')):
            info=inspect_selected(self.root)
        self.assertIsNone(info.native_path);self.assertIsNone(info.selection.revision)
        self.assertIn('custom configuration default','\n'.join(info.sections()));self.preserved()

    def test_selected_report_separates_native_and_deployment_geometry_and_is_readonly(self):
        receipt=self.apply();before=inspect_selection(self.root)
        with patch('subprocess.run',side_effect=AssertionError('no process execution')):info=inspect_selected(self.root)
        text='\n'.join(info.sections());self.assertIn('NEXT explicit start/restart',text)
        self.assertIn('not a claim about the running renderer',text)
        self.assertIn('desktop geometry: 1280x720',text);self.assertIn('preview geometry: 1920x1080',text)
        self.assertEqual(info.native_path,self.root/REVISIONS/receipt.after.revision/'lunar.conf')
        self.assertEqual(before,inspect_selection(self.root));self.preserved()

    def test_edited_library_does_not_change_reported_frozen_revision(self):
        receipt=self.apply();self.scene.write_bytes(b'new unrelated user content')
        info=inspect_selected(self.root);self.assertEqual(info.selection,receipt.after)
        self.assertEqual(info.document.view.target,'moon');self.assertEqual(self.scene.read_bytes(),b'new unrelated user content')

    def test_bad_selector_or_revision_never_masquerades_as_legacy(self):
        self.apply();path=self.root/SELECTOR;raw=path.read_bytes();path.write_bytes(b'unknown')
        with self.assertRaises(ValueError):inspect_selected(self.root)
        self.assertEqual(path.read_bytes(),b'unknown');path.write_bytes(raw)
        revision=inspect_selection(self.root).revision;(self.root/REVISIONS/revision/'lunar.conf').write_bytes(b'edited')
        with self.assertRaises(ValueError):inspect_selected(self.root)
        self.assertEqual(path.read_bytes(),raw)
