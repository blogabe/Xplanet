"""Immutable reviewed scene references; no desktop/service/provider execution."""
from pathlib import Path
import sys,unittest
from tests import test_scene_handoff as fixtures
from configurator.handoff import stage_plan,create_plan
from configurator.library import save_named
from configurator.model import View
from configurator.selection import (SELECTOR,REVISIONS,ARGS,CHECKS,MANIFEST,Selection,
    inspect_selection,apply_bundle,select_revision,restore_selection,read_revision,UncertainSelection)


class SceneSelectionTests(unittest.TestCase):
    setUp_fixture=fixtures.HandoffTests.setUp
    plan=fixtures.HandoffTests.plan

    def setUp(self):
        self.setUp_fixture();stage_plan(self.plan(),self.target)
        self.baseline={p:p.read_bytes() for p in (self.scene,self.scene.with_suffix('.def'),self.asset,self.root/'config/xp.def',self.root/'config/xp.conf')}
        self.guard=self.root/'producer-state';self.guard.write_bytes(b'pending producer intent; do not rewind')

    def preserved(self):
        for path,raw in self.baseline.items():self.assertEqual(path.read_bytes(),raw)
        self.assertEqual(self.guard.read_bytes(),b'pending producer intent; do not rewind')
        self.assertFalse((self.root/'forbidden').exists())

    def apply(self):return apply_bundle(self.root,self.target,inspect_selection(self.root))

    def next_bundle(self):
        source=save_named(self.root/'config/scenes/second.conf',View(),sys.executable)
        bundle=self.root/'second review';stage_plan(create_plan(self.root,source,sys.executable,'1920x1080'),bundle)
        return bundle

    def test_apply_freezes_native_revision_and_changes_only_selector_then_guarded_restore(self):
        self.assertEqual(inspect_selection(self.root),Selection());receipt=self.apply()
        self.assertEqual(receipt.after,inspect_selection(self.root));record=read_revision(self.root,receipt.after.revision)
        folder=self.root/REVISIONS/receipt.after.revision
        self.assertEqual((folder/'lunar.conf').read_bytes(),self.baseline[self.scene])
        self.assertEqual(record['geometry'],'1280x720');self.assertIn(b'-timewarp\n0\n',(folder/ARGS).read_bytes())
        self.assertEqual((self.root/SELECTOR).stat().st_mode&0o777,0o600)
        self.assertEqual(folder.stat().st_mode&0o777,0o700)
        restored=restore_selection(self.root,receipt);self.assertIsNone(restored.after.revision)
        self.assertFalse((self.root/SELECTOR).exists());self.assertTrue(folder.is_dir());self.preserved()

    def test_library_edits_do_not_change_selected_revision_but_new_apply_requires_fresh_review(self):
        receipt=self.apply();self.scene.write_bytes(b'# newer user edit\n')
        self.assertEqual(read_revision(self.root,receipt.after.revision)['scene'],'config/scenes/lunar.conf')
        self.assertEqual((self.root/REVISIONS/receipt.after.revision/'lunar.conf').read_bytes(),self.baseline[self.scene])
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(inspect_selection(self.root),receipt.after)

    def test_repeat_apply_is_idempotent_and_does_not_rewrite_revision_or_reference(self):
        receipt=self.apply();folder=self.root/REVISIONS/receipt.after.revision;before=(folder/MANIFEST).stat()
        again=self.apply();self.assertEqual(again.before,again.after);self.assertEqual(again.after,receipt.after)
        self.assertEqual((folder/MANIFEST).stat().st_ino,before.st_ino);self.preserved()

    def test_two_revisions_restore_previous_reference_without_replacing_either_snapshot(self):
        first=self.apply();second=apply_bundle(self.root,self.next_bundle(),first.after)
        self.assertNotEqual(first.after.revision,second.after.revision)
        restored=restore_selection(self.root,second);self.assertEqual(restored.after.revision,first.after.revision)
        self.assertEqual(len(list((self.root/REVISIONS).iterdir())),2);self.preserved()

    def test_changed_or_replaced_selection_refuses_stale_restore(self):
        first=self.apply();second=apply_bundle(self.root,self.next_bundle(),first.after)
        with self.assertRaisesRegex(ValueError,'changed'):restore_selection(self.root,first)
        self.assertEqual(inspect_selection(self.root),second.after)
        path=self.root/SELECTOR;raw=path.read_bytes();other=path.with_name('new selector');other.write_bytes(raw);other.replace(path)
        with self.assertRaisesRegex(ValueError,'changed'):restore_selection(self.root,second)
        self.assertEqual(path.read_bytes(),raw);self.preserved()

    def test_invalid_selector_or_symlink_never_falls_back_or_overwrites(self):
        path=self.root/SELECTOR
        for raw in (b'',b'legacy\n',b'v1 '+'a'.encode()*64,b'v1 ../bad\n'):
            path.write_bytes(raw)
            with self.assertRaises(ValueError):inspect_selection(self.root)
            with self.assertRaises(ValueError):apply_bundle(self.root,self.target,Selection())
            self.assertEqual(path.read_bytes(),raw)
        path.unlink();path.symlink_to(self.scene)
        with self.assertRaises((ValueError,OSError)):inspect_selection(self.root)
        self.preserved()

    def test_missing_altered_and_symlinked_revision_resources_refuse(self):
        receipt=self.apply();identity=receipt.after.revision;folder=self.root/REVISIONS/identity
        for name in (ARGS,CHECKS,MANIFEST,'lunar.conf'):
            path=folder/name;raw=path.read_bytes();path.write_bytes(raw+b'new')
            with self.assertRaises(ValueError):read_revision(self.root,identity)
            path.write_bytes(raw)
        path=folder/ARGS;raw=path.read_bytes();path.unlink();path.symlink_to(self.scene)
        with self.assertRaises((ValueError,OSError)):read_revision(self.root,identity)
        self.assertEqual(inspect_selection(self.root),receipt.after);self.preserved()

    def test_asset_change_blocks_selection_and_rollback_does_not_restore_assets(self):
        first=self.apply();self.asset.write_bytes(b'new user asset')
        with self.assertRaises(ValueError):read_revision(self.root,first.after.revision)
        restored=restore_selection(self.root,first);self.assertIsNone(restored.after.revision)
        self.assertEqual(self.asset.read_bytes(),b'new user asset');self.assertEqual(self.guard.read_bytes(),b'pending producer intent; do not rewind')

    def test_existing_lock_is_preserved_and_no_reference_is_changed(self):
        receipt=self.apply();lock=self.root/'.state/xplanet/scene-selection.lock.d';lock.mkdir();(lock/'intent').write_bytes(b'unknown')
        with self.assertRaisesRegex(ValueError,'locked'):restore_selection(self.root,receipt)
        self.assertEqual(inspect_selection(self.root),receipt.after);self.assertEqual((lock/'intent').read_bytes(),b'unknown');self.preserved()

    def test_before_publish_failure_preserves_selection_and_cleans_only_own_pending(self):
        receipt=self.apply()
        def fault(point):
            if point=='before-publish':raise OSError('injected pre-publish failure')
        with self.assertRaises(OSError):select_revision(self.root,None,receipt.after,_fault=fault)
        self.assertEqual(inspect_selection(self.root),receipt.after);self.assertFalse((self.root/'.state/xplanet/scene-selection.lock.d').exists());self.preserved()

    def test_after_publish_failure_is_uncertain_without_automatic_rollback(self):
        receipt=self.apply()
        def fault(point):
            if point=='after-publish':raise OSError('injected fsync boundary failure')
        with self.assertRaises(UncertainSelection):select_revision(self.root,None,receipt.after,_fault=fault)
        self.assertIsNone(inspect_selection(self.root).revision);self.preserved()

    def test_external_pending_edit_is_retained_and_concurrent_reference_is_not_overwritten(self):
        first=self.apply();identity=first.after.revision;select_revision(self.root,None,first.after)
        def edit(point):
            if point=='before-publish':next((self.root/'config').glob('.desktop.scene-*.tmp')).write_bytes(b'external material')
        with self.assertRaises(ValueError):select_revision(self.root,identity,Selection(),_fault=edit)
        self.assertFalse((self.root/SELECTOR).exists());self.assertEqual(next((self.root/'config').glob('.desktop.scene-*.tmp')).read_bytes(),b'external material')
        def changed(point):
            if point=='before-publish':(self.root/SELECTOR).write_bytes(('v1 '+identity+'\n').encode())
        with self.assertRaisesRegex(ValueError,'changed'):select_revision(self.root,identity,Selection(),_fault=changed)
        self.assertEqual(inspect_selection(self.root).revision,identity);self.preserved()

    def test_forged_oversize_resource_metadata_is_refused_before_hashing_assets(self):
        import plistlib
        from unittest.mock import patch
        from configurator.handoff import digest
        receipt=self.apply();folder=self.root/REVISIONS/receipt.after.revision;manifest=folder/MANIFEST
        value=plistlib.loads(manifest.read_bytes());next(iter(value['review']['assets'].values()))['size']=1024*1024*1024+1
        raw=plistlib.dumps(value,fmt=plistlib.FMT_XML,sort_keys=True);manifest.write_bytes(raw)
        identity=digest(raw);folder.rename(folder.with_name(identity))
        with patch('configurator.selection.same_bytes',side_effect=AssertionError('must reject metadata before external reads')):
            with self.assertRaises(ValueError):read_revision(self.root,identity)
        self.preserved()

    def test_newer_reference_after_publication_is_preserved_with_uncertain_outcome(self):
        receipt=self.apply()
        def changed(point):
            if point=='after-publish':(self.root/SELECTOR).write_bytes(b'v1 '+b'd'*64+b'\n')
        with self.assertRaises(UncertainSelection):select_revision(self.root,None,receipt.after,_fault=changed)
        self.assertEqual(inspect_selection(self.root).revision,'d'*64);self.preserved()

    def test_revision_durability_failure_preserves_old_selection_and_producer_state(self):
        from unittest.mock import patch
        first=self.apply();bundle=self.next_bundle()
        with patch('configurator.selection.os.fsync',side_effect=OSError('injected durability failure')):
            with self.assertRaises(OSError):apply_bundle(self.root,bundle,first.after)
        self.assertEqual(inspect_selection(self.root),first.after);self.preserved()
