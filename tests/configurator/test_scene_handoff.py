"""Review/export never evaluates legacy or selects/starts a desktop scene."""
from dataclasses import replace
from pathlib import Path
import json,os,sys,tempfile,unittest
from unittest.mock import patch
from configurator.model import View,PLANET_MAPS
from configurator.library import save_named
from configurator.handoff import create_plan,stage_plan,check_bundle,recheck,HandoffPlan,canonical,digest,MANIFEST
from configurator.fileio import OwnedFiles

class HandoffTests(unittest.TestCase):
    def setUp(self):
        # Identity-sensitive fixtures stay outside sync-managed suite TMPDIR.
        # Metadata-only changes are deliberately rejected in the regression below.
        self.temp=tempfile.TemporaryDirectory(prefix="xp handoff '$() ",dir="/tmp");self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
        self.legacy={'config/xp.def':b'XPLANET_BIN=$(touch forbidden)\nsource do-not-execute\n','config/xp.conf':b'[earth]\n# preserve\nunknown=first\nunknown=again\n'}
        for name,data in self.legacy.items():(self.root/name).write_bytes(data)
        self.asset=self.root/PLANET_MAPS['moon'];self.asset.parent.mkdir(parents=True);self.asset.write_bytes(b'Known fixture bytes; image decoding is NOT certified')
        self.scene=save_named(self.root/'config/scenes/lunar.conf',View(target='moon',projection='space',observer='earth',time_mode='fixed'),sys.executable)
        self.target=self.root/'new review bundle'

    def plan(self):return create_plan(self.root,self.scene,sys.executable,'1280x720')

    def test_review_only_plan_freezes_correct_scene_argv_and_opaque_legacy_hashes(self):
        before={name:(self.root/name).read_bytes() for name in self.legacy};plan=self.plan();data=plan.metadata
        self.assertFalse(data['activation_ready']);self.assertNotIn('activate',dir(plan))
        self.assertEqual(data['scene'],'config/scenes/lunar.conf');self.assertEqual(data['preview_geometry'],'1920x1080')
        self.assertNotIn('-projection',data['proposed_argv']);self.assertEqual(data['proposed_argv'][-2:],['-timewarp','0'])
        self.assertEqual(data['proposed_argv'][data['proposed_argv'].index('-body')+1],'moon')
        self.assertNotIn('touch forbidden',plan.record.decode());self.assertNotIn('unknown=first',plan.record.decode())
        self.assertEqual(before,{name:(self.root/name).read_bytes() for name in self.legacy})
        self.assertFalse((self.root/'forbidden').exists());self.assertFalse(self.target.exists())

    def test_snapshot_export_is_new_private_exact_and_not_a_selection(self):
        plan=self.plan();stage_plan(plan,self.target);self.assertEqual(check_bundle(self.root,self.target),plan.metadata)
        for name,data in plan.native:self.assertEqual((self.target/name).read_bytes(),data)
        self.assertEqual(self.target.stat().st_mode&0o777,0o700)
        manifest=json.loads((self.target/MANIFEST).read_bytes());args=manifest['compiled_argv']
        self.assertEqual(args[args.index('-config')+1],str(self.target/'lunar.conf'));self.assertIn(str(self.root),args)
        self.assertNotIn('-fork',args);self.assertNotIn('-output',args)
        self.assertFalse((self.root/'config/xplanet.scene').exists());self.assertFalse((self.root/'.state').exists())

    def test_missing_legacy_creation_and_same_byte_file_replacement_invalidate_review(self):
        (self.root/'config/xp.def').unlink();plan=self.plan();self.assertFalse(plan.metadata['legacy']['config/xp.def']['present'])
        (self.root/'config/xp.def').write_bytes(b'new user config')
        with self.assertRaisesRegex(ValueError,'changed'):stage_plan(plan,self.target)
        self.assertFalse(self.target.exists());plan=self.plan()
        raw=self.scene.read_bytes();temporary=self.scene.with_name('new.conf');temporary.write_bytes(raw);temporary.replace(self.scene)
        with self.assertRaisesRegex(ValueError,'changed'):recheck(plan)

    def test_metadata_only_change_invalidates_review_without_weakening_identity(self):
        plan=self.plan();before=self.scene.stat();raw=self.scene.read_bytes()
        os.utime(self.scene,ns=(before.st_atime_ns,before.st_mtime_ns))
        self.assertNotEqual(self.scene.stat().st_ctime_ns,before.st_ctime_ns)
        self.assertEqual(self.scene.read_bytes(),raw)
        with self.assertRaisesRegex(ValueError,'changed'):recheck(plan)
        self.assertFalse(self.target.exists())

    def test_asset_and_renderer_changes_refuse_without_output(self):
        plan=self.plan();self.asset.write_bytes(b'external asset replacement')
        with self.assertRaises(ValueError):stage_plan(plan,self.target)
        self.assertFalse(self.target.exists())
        binary=self.root/'explicit binary';binary.write_text('#!/bin/sh\ntouch forbidden\n');binary.chmod(0o700)
        plan=create_plan(self.root,self.scene,binary,'1280x720');binary.write_text('#!/bin/sh\nexit 1\n')
        with self.assertRaises(ValueError):stage_plan(plan,self.target)
        self.assertFalse((self.root/'forbidden').exists())
        with self.asset.open('wb') as stream:stream.truncate(512*1024*1024+1)
        with self.assertRaises(ValueError):self.plan()

    def test_changed_legacy_during_stage_rolls_back_owned_output_only(self):
        plan=self.plan();write=OwnedFiles.write;changed=False
        def publishing(owner,name,data):
            nonlocal changed
            write(owner,name,data)
            if not changed:(self.root/'config/xp.conf').write_bytes(b'new user content');changed=True
        with patch.object(OwnedFiles,'write',autospec=True,side_effect=publishing),self.assertRaises(ValueError):stage_plan(plan,self.target)
        self.assertFalse(self.target.exists());self.assertEqual((self.root/'config/xp.conf').read_bytes(),b'new user content')

    def test_write_failure_and_interrupt_remove_only_owned_unchanged_partial_files(self):
        plan=self.plan();write=OwnedFiles.write
        for failure in (OSError('injected disk failure'),KeyboardInterrupt()):
            def publishing(owner,name,data):write(owner,name,data);raise failure
            with patch.object(OwnedFiles,'write',autospec=True,side_effect=publishing),self.assertRaises(type(failure)):stage_plan(plan,self.target)
            self.assertFalse(self.target.exists())
        self.assertTrue(all((self.root/name).read_bytes()==data for name,data in self.legacy.items()))

    def test_external_partial_output_is_retained_with_diagnostic(self):
        plan=self.plan();write=OwnedFiles.write
        def publishing(owner,name,data):
            write(owner,name,data);(self.target/name).write_bytes(b'external edit');raise OSError('injected failure')
        with patch.object(OwnedFiles,'write',autospec=True,side_effect=publishing),self.assertRaises(OSError) as caught:stage_plan(plan,self.target)
        self.assertTrue(self.target.exists());self.assertTrue(any('Partial review output remains' in note for note in caught.exception.__notes__))
        self.assertEqual(next(self.target.iterdir()).read_bytes(),b'external edit')

    def test_existing_destinations_symlinks_unsupported_sources_and_geometry_decline(self):
        plan=self.plan();self.target.mkdir();(self.target/'keep').write_bytes(b'keep')
        with self.assertRaises(FileExistsError):stage_plan(plan,self.target)
        self.assertEqual((self.target/'keep').read_bytes(),b'keep')
        link=self.root/'alias';link.symlink_to(self.target,target_is_directory=True)
        with self.assertRaises((ValueError,OSError)):stage_plan(plan,link/'child')
        for value in ('','001280x720','199x720','20000x720','1280x720+1+2',None):
            with self.subTest(value=value),self.assertRaises(ValueError):create_plan(self.root,self.scene,sys.executable,value)
        foreign=save_named(self.root/'foreign.conf',View(),sys.executable)
        with self.assertRaises(ValueError):create_plan(self.root,foreign,sys.executable,'1280x720')
        self.scene.write_bytes(b'[moon]\nunknown=preserve\n')
        with self.assertRaises(ValueError):self.plan()
        self.assertFalse((self.root/'forbidden').exists())

    def test_stock_dependencies_and_framing_limit_are_disclosed(self):
        scene=save_named(self.root/'config/scenes/earth.conf',View(),sys.executable)
        plan=create_plan(self.root,scene,sys.executable,'1920x1080')
        self.assertEqual(plan.metadata['unbound_stock_lookups'],['earth.jpg','night.jpg'])
        self.assertEqual(plan.metadata['assets'],{});self.assertFalse(plan.metadata['activation_ready'])
        self.assertTrue(any('saved preview geometry 1920x1080' in note for note in plan.metadata['notes']))

    def test_altered_manifest_injected_commands_snapshot_edits_and_extra_files_refuse(self):
        plan=self.plan();stage_plan(plan,self.target);path=self.target/MANIFEST;original=path.read_bytes()
        data=json.loads(original);data['compiled_argv']+=['-prev_command','touch forbidden'];path.write_bytes(canonical(data))
        with self.assertRaises(ValueError):check_bundle(self.root,self.target)
        data=json.loads(original);data['plan']['activation_ready']=True;unsigned={k:v for k,v in data['plan'].items() if k!='id'};data['plan']['id']=digest(canonical(unsigned));path.write_bytes(canonical(data))
        with self.assertRaises(ValueError):check_bundle(self.root,self.target)
        path.write_bytes(original);(self.target/'unexpected').write_text('not read')
        with self.assertRaises(ValueError):check_bundle(self.root,self.target)
        (self.target/'unexpected').unlink();(self.target/'lunar.conf').write_bytes(b'new data')
        with self.assertRaises(ValueError):check_bundle(self.root,self.target)
        self.assertFalse((self.root/'forbidden').exists())

    def test_forged_plan_cannot_expand_legacy_read_scope_or_write_paths(self):
        plan=self.plan();data=plan.metadata;data['legacy']['dev/ABE-CFG']='never read'
        forged=HandoffPlan(canonical(data),plan.native)
        with self.assertRaises(ValueError):stage_plan(forged,self.target)
        self.assertFalse(self.target.exists())

    def test_previous_map_layout_requires_save_copy_before_handoff(self):
        original=self.scene.read_bytes().replace(b'=maps/',b'=assets/maps/')
        self.scene.write_bytes(original)
        with self.assertRaisesRegex(ValueError,'Save a new copy'):
            self.plan()
        self.assertEqual(self.scene.read_bytes(),original)
        self.assertFalse(self.target.exists())
