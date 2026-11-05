"""End-to-end frozen astronomy association without user or provider operations."""
import asyncio
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from configurator.astronomy_capture import capture_existing,FrozenAstronomy,FILES
from configurator.cloud_capture import json_bytes
from configurator.model import View,SAMPLE,parse_saved_view,SCENE_HEADERS
from configurator.library import save_named
from configurator.workspace import Workspace,open_view,configuration_issues,save_view
from configurator.native_inspection import inspect_native,copy_unchanged
from configurator.handoff import create_plan,stage_plan,command
from configurator.selection import stage_revision,read_revision,runtime_files
from configurator.comparison import plan,reason
from configurator.exchange import export_scene
from configurator.recovery import pack,raw_fields,RecoveryStore,encoded,digest,LEGACY_FIELDS
from totalmarker.features import norad,eclipse
from totalmarker.http import Fetcher,Response
from .support import Sandbox,ScriptedTransport
from . import test_astronomy_capture as capture_fixtures
from .test_norad import SAMPLE as TLE,EPOCH


def synthetic_current_tle():
    """Re-epoch the old example ONLY to exercise file plumbing, not real prediction."""
    now=datetime.now(timezone.utc);fraction=int((now.hour*3600+now.minute*60+now.second)/86400*1e8)
    epoch=f'{now:%y}{now.timetuple().tm_yday:03d}.{fraction:08d}'
    lines=TLE.decode().splitlines();lines[0]='SYNTHETIC FILE-PLUMBING FIXTURE'
    body=lines[1][:18]+epoch+lines[1][32:68]
    lines[1]=body+str(sum(int(c) if c.isdigit() else c=='-' for c in body)%10)
    return ('\n'.join(lines)+'\n').encode()


class AstronomySceneTests(Sandbox):
    eclipse=capture_fixtures.AstronomyCaptureTests.eclipse
    def setUp(self):
        super().setUp();(self.root/'config').mkdir();self.workspace=Workspace();self.addCleanup(self.workspace.close)
    def norad_capture(self):
        settings=self.config('NoradEnabled=On\nNoradCatalogIds=25544\n')
        now=datetime.now(timezone.utc).timestamp()
        norad.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(Response(200,{},synthetic_current_tle()))),now=now)
        return capture_existing(self.root.resolve(),'norad','config.ini',now=now)
    def eclipse_capture(self):
        _,path=self.eclipse()
        return capture_existing(self.root.resolve(),'eclipse','config.ini',now=path.start_at-1800)
    def scene(self):
        first=self.norad_capture();second=self.eclipse_capture()
        self.workspace.register_astronomy(first);self.workspace.register_astronomy(second)
        view=View(projection='space',norad_layer='captured',norad_id=first.identity,eclipse_layer='captured',eclipse_id=second.identity,eclipse_window=second.window_token,time_mode='fixed',utc=second.window_token.split('/')[0])
        return view,{'norad':first,'eclipse':second}
    def save(self,view,astronomy,name='event.conf'):
        return save_named(self.root/'config/scenes'/name,view,sys.executable,astronomy=astronomy)

    def test_both_captures_save_reopen_and_native_copy_preserve_inactive_bytes(self):
        view,data=self.scene();source=self.save(view,data);doc=open_view(source)
        self.assertEqual(doc.view,view);self.assertEqual({item.product:item for item in doc.astronomy},data)
        native=dict(doc.native_files);self.assertNotIn(b'satellite_file=',native['event.conf']);self.assertIn(b'marker_file=event.frozen-eclipse.markers',native['event.conf'])
        self.assertIn('event.frozen-norad.satellites.tle',native)
        review=inspect_native(source);self.assertTrue(review.recognized)
        destination=self.root/'copied';copy_unchanged(review,destination)
        self.assertEqual({p.name:p.read_bytes() for p in destination.iterdir()},native)
        self.assertEqual(open_view(destination/'event.conf').view,view)
        off=replace(view,target='mars');saved=save_view(self.root/'inactive',off,sys.executable,astronomy=data)
        self.assertNotIn(b'frozen-',(saved/'xp.conf').read_bytes());self.assertEqual(len(open_view(saved).astronomy),2)

    def test_time_target_inactivity_and_provenance_binding(self):
        view,data=self.scene()
        for changed,expected in ((view,('eclipse',)),(replace(view,time_mode='now'),('norad',)),(replace(view,target='moon'),()),(replace(view,utc='2000-01-01T12:00:00Z'),())):
            self.assertEqual(changed.uses_astronomy(),expected)
            self.assertFalse(changed.astronomy_problem(data))
        self.assertTrue(replace(view,eclipse_window='2027-08-02T11:31:00Z/2027-08-02T11:34:00Z').astronomy_problem(data))
        self.assertTrue(view.astronomy_problem({'norad':data['norad']}))
        self.assertIn('norad_id',replace(view,time_mode='now').active_fields());self.assertIn('eclipse_window',view.active_fields())
        self.assertNotIn('norad_id',view.active_fields())

    def test_parser_rejects_missing_wrong_mutable_or_mismatched_association(self):
        view,data=self.scene();definition=view.definition(sys.executable).encode();body=view.body()
        for astronomy in ((),(None,),list(data.values()),(data['norad'],data['norad'])):
            with self.assertRaises(ValueError):parse_saved_view(definition,body,astronomy=astronomy)
        doc=parse_saved_view(definition,body,astronomy=tuple(data.values()));self.assertEqual(doc.view,view)
        with self.assertRaises(ValueError):parse_saved_view(definition.replace(view.eclipse_id.encode(),b'a'*64),body,astronomy=tuple(data.values()))
        for name in ('norad_id','eclipse_id'):
            with self.assertRaises(ValueError):replace(view,**{name:'not-a-hash'}).validate()

    def test_all_prior_generated_versions_open_without_rewriting(self):
        for header,version in SCENE_HEADERS.items():
            if version==16:continue
            view=View(geometry='800x600') if version<14 else View()
            definition=view.definition(sys.executable,version=version).encode();body=view.body() if version>=3 else SAMPLE.read_bytes()
            doc=parse_saved_view(definition,body);self.assertEqual(doc.view,view)
            self.assertEqual(doc.view.norad_layer,'off');self.assertEqual(doc.view.eclipse_layer,'off')

    def test_stale_active_norad_blocks_preview_save_but_off_keeps_bytes(self):
        view,data=self.scene();active=replace(view,time_mode='now')
        future=data['norad'].metadata['oldest_epoch_at']+data['norad'].metadata['max_age_seconds']+1
        with patch('configurator.astronomy_capture.time.time',return_value=future):
            self.assertTrue(any(issue.severity=='blocking' and issue.field=='norad_layer' for issue in configuration_issues(active,sys.executable,astronomy=data)))
            with self.assertRaises(ValueError):self.save(active,data)
            saved=self.save(replace(active,norad_layer='off'),data)
        self.assertEqual(len(open_view(saved).astronomy),2)

    def test_fixed_eclipse_handoff_freezes_all_files_and_norad_is_refused_centrally(self):
        view,data=self.scene();source=self.save(view,data)
        plan_=create_plan(self.root.resolve(),source,sys.executable,'1920x1080')
        bundle=stage_plan(plan_,self.root/'review');identity=stage_revision(self.root.resolve(),bundle);record=read_revision(self.root.resolve(),identity)
        self.assertEqual(record['proposed_argv'][-2:],['-timewarp','0'])
        self.assertTrue(any('frozen-eclipse.arcs' in name for name in record['native']))
        self.assertTrue(any('frozen-norad.satellites.tle' in name for name in record['native']))
        active=replace(view,time_mode='now');active_source=self.save(active,data,'current.conf');document=open_view(active_source)
        with self.assertRaisesRegex(ValueError,'NORAD desktop handoff'):create_plan(self.root.resolve(),active_source,sys.executable,'1920x1080')
        with self.assertRaisesRegex(ValueError,'NORAD desktop handoff'):runtime_files(record,document)
        with self.assertRaisesRegex(ValueError,'NORAD desktop handoff'):command(active,sys.executable,self.root,active_source,self.root,'1920x1080')


    def test_coherent_forged_norad_revision_is_refused_on_read_not_only_ui(self):
        from configurator import handoff,selection
        view,data=self.scene();active=replace(view,time_mode='now');source=self.save(active,data,'forged-current.conf')
        original=handoff.command
        def malicious_builder(view,*args):
            # Build a hash-consistent attacker fixture by bypassing the guard only
            # during construction. The real reader/guard is restored before use.
            return original(replace(view,norad_layer='off'),*args)
        with patch.object(handoff,'command',side_effect=malicious_builder),patch.object(selection,'command',side_effect=malicious_builder):
            plan_=create_plan(self.root.resolve(),source,sys.executable,'1920x1080')
            bundle=stage_plan(plan_,self.root/'malicious-review');identity=stage_revision(self.root.resolve(),bundle)
        with self.assertRaisesRegex(ValueError,'Invalid or altered scene revision'):read_revision(self.root.resolve(),identity)
        self.assertFalse((self.root/'config/desktop.scene').exists())

    def test_exchange_refuses_even_disabled_frozen_astronomy_without_silent_loss(self):
        view,data=self.scene();source=self.save(replace(view,norad_layer='off',eclipse_layer='off'),data)
        with self.assertRaisesRegex(ValueError,'excludes frozen'):export_scene(source,self.root/'exchange')
        self.assertFalse((self.root/'exchange').exists());self.assertEqual(len(open_view(source).astronomy),2)

    def test_comparisons_preserve_inactive_planetary_choices_and_reject_changed_eligibility(self):
        view,data=self.scene()
        planetary=replace(view,target='mars',time_mode='now');self.assertFalse(reason(planetary));self.assertEqual(plan(planetary).views[0].uses_astronomy(),())
        with self.assertRaisesRegex(ValueError,'NORAD'):plan(replace(view,time_mode='now'))
        eclipse_now=replace(view,norad_layer='off',time_mode='now')
        with self.assertRaisesRegex(ValueError,'eligibility'):plan(eclipse_now,now=datetime.strptime(view.utc,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc))
        self.assertEqual(plan(view).views[0].uses_astronomy(),('eclipse',))

    def test_capture_quota_includes_all_astronomy_without_eviction(self):
        frozen=self.norad_capture()
        with patch('configurator.workspace.CAPTURE_BUDGET',frozen.byte_size-1),self.assertRaisesRegex(ValueError,'128 MiB'):self.workspace.register_astronomy(frozen)
        self.assertFalse(self.workspace.astronomy)
        self.workspace.register_astronomy(frozen)
        with patch('configurator.workspace.CAPTURE_BUDGET',frozen.byte_size):self.workspace.register_astronomy(frozen)
        self.assertEqual(self.workspace.capture_bytes(),frozen.byte_size)


class AstronomyRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.workspace=Workspace();self.addCleanup(self.workspace.close)
        self.fixture=AstronomySceneTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown if hasattr(self.fixture,'tearDown') else lambda:None);self.addCleanup(self.fixture.doCleanups)
        self.view,self.data=self.fixture.scene()
        for frozen in self.data.values():self.workspace.register_astronomy(frozen)
        self.store=RecoveryStore(self.root);self.sessions=[];self.addCleanup(lambda:[s.close() for s in self.sessions])
    def session(self):
        session=self.store.new_session();self.sessions.append(session);return session

    async def test_schema2_roundtrip_preserves_both_baselines_and_invalid_raw_fields(self):
        other_meta=self.data['norad'].metadata;other_meta['captured_at']+=1
        other=FrozenAstronomy(json_bytes(other_meta),self.data['norad'].payload);self.workspace.register_astronomy(other)
        baseline=raw_fields(self.view,sys.executable);current={**baseline,'norad_id':other.identity,'utc':'invalid partial UTC'}
        record,blobs=pack(current,baseline,SAMPLE.read_bytes(),self.workspace);self.assertEqual(len(record['astronomy']),3)
        session=self.session();sha=await session.checkpoint(record,blobs);session.close();loaded=self.store.load(session.identity)
        self.assertEqual(loaded.record['current'],current);self.assertEqual(loaded.record['baseline'],baseline);self.assertEqual(len(loaded.astronomy),3)
        self.assertEqual({f.identity for f in loaded.astronomy},set(record['astronomy']))

    async def test_exact_schema1_legacy_restore_adds_defaults_in_memory_without_rewrite(self):
        fields={key:value for key,value in raw_fields(renderer=sys.executable).items() if key in LEGACY_FIELDS}
        record,blobs=pack(raw_fields(renderer=sys.executable),raw_fields(renderer=sys.executable),SAMPLE.read_bytes(),self.workspace)
        record={**record,'schema':1,'current':fields,'baseline':fields};record.pop('astronomy')
        session=self.session();sha=await session.checkpoint(record,blobs);session.close()
        native=self.store.path/session.identity/(sha+'.json');before=native.read_bytes();loaded=self.store.load(session.identity)
        self.assertEqual(native.read_bytes(),before);self.assertEqual(loaded.record['current']['norad_layer'],'off');self.assertEqual(loaded.astronomy,())
        self.assertEqual(loaded.record['baseline']['eclipse_window'],'')


    async def test_corrupt_new_astronomy_blob_falls_back_without_discarding_evidence(self):
        baseline=raw_fields(self.view,sys.executable);session=self.session()
        first=await session.checkpoint(*pack(baseline,baseline,SAMPLE.read_bytes(),self.workspace))
        meta=self.data['norad'].metadata;meta['captured_at']+=1;other=FrozenAstronomy(json_bytes(meta),self.data['norad'].payload);self.workspace.register_astronomy(other)
        current={**baseline,'norad_id':other.identity}
        second=await session.checkpoint(*pack(current,baseline,SAMPLE.read_bytes(),self.workspace));session.close()
        path=self.store.path/session.identity/digest(other.provenance);path.write_bytes(b'corrupt astronomy fixture')
        recovered=self.store.load(session.identity)
        self.assertTrue(recovered.fallback);self.assertEqual(recovered.revision,first);self.assertEqual(recovered.record['current'],baseline)
        self.assertEqual(path.read_bytes(),b'corrupt astronomy fixture')
        self.assertTrue((self.store.path/session.identity/(second+'.json')).exists())

    async def test_schema1_unknown_fields_and_missing_capture_fail_without_deletion(self):
        fields={key:value for key,value in raw_fields(renderer=sys.executable).items() if key in LEGACY_FIELDS};fields['unknown']='unsafe'
        record,blobs=pack(raw_fields(renderer=sys.executable),raw_fields(renderer=sys.executable),SAMPLE.read_bytes(),self.workspace)
        record={**record,'schema':1,'current':fields,'baseline':fields};record.pop('astronomy')
        from configurator.recovery import metadata
        session=self.session();await session.checkpoint(*pack(raw_fields(renderer=sys.executable),raw_fields(renderer=sys.executable),SAMPLE.read_bytes(),self.workspace))
        raw=encoded(record);sha=digest(raw);folder=self.store.path/session.identity
        path=folder/(sha+'.json');fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        session.close();fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
        try:
            with self.assertRaises(ValueError):metadata(fd,sha)
        finally:os.close(fd)
        self.assertEqual(path.read_bytes(),raw)
        empty=Workspace();self.addCleanup(empty.close)
        with self.assertRaisesRegex(ValueError,'astronomy capture'):pack(raw_fields(self.view,sys.executable),raw_fields(renderer=sys.executable),SAMPLE.read_bytes(),empty)


class AstronomyPreviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture=AstronomySceneTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.view,self.data=self.fixture.scene();self.workspace=self.fixture.workspace
        self.root=self.fixture.root;self.binary=self.root/'finite fixture'
        self.binary.write_text('#!'+sys.executable+'\n'+"import pathlib,sys,struct\n"+"args=sys.argv[1:];config=pathlib.Path(args[args.index('-config')+1]);body=config.read_text()\n"+"assert '-fork' not in args and '-background' not in args and args[args.index('-num_times')+1]=='1'\n"+"for line in body.splitlines():\n if line.startswith(('satellite_file=','marker_file=frozen-eclipse.','arc_file=frozen-eclipse.')):\n  name=line.split('=',1)[1];assert (config.parent/name).is_file()\n  if line.startswith('satellite_file='):assert (config.parent/(name+'.tle')).is_file()\n"+"if pathlib.Path(__file__).with_suffix('.fail').exists(): print('fixture later failure',file=sys.stderr);sys.exit(1)\n"+"out=pathlib.Path(args[args.index('-output')+1]);width,height=map(int,args[args.index('-geometry')+1].split('x'));out.write_bytes(b'\\x89PNG\\r\\n\\x1a\\n'+b'\\0'*4+b'IHDR'+struct.pack('>II',width,height))\n")
        self.binary.chmod(0o700)

    async def test_preview_copies_exact_tle_companion_and_keeps_prior_on_later_failure(self):
        scene=replace(self.view,time_mode='now');await self.workspace.preview(scene,str(self.binary));snapshot=self.workspace.latest
        self.assertEqual([p for p,_ in snapshot.astronomy_provenance],['norad'])
        self.assertTrue(snapshot.matches(scene,str(self.binary),SAMPLE.read_bytes()))
        meta=self.data['norad'].metadata;meta['captured_at']+=1
        other=FrozenAstronomy(json_bytes(meta),self.data['norad'].payload);self.workspace.register_astronomy(other);changed=replace(scene,norad_id=other.identity)
        self.assertNotEqual(scene.render_digest(),changed.render_digest());self.assertFalse(snapshot.matches(changed,str(self.binary),SAMPLE.read_bytes()))
        self.binary.with_suffix('.fail').write_text('owned failure fixture')
        with self.assertRaisesRegex(ValueError,'fixture later failure'):await self.workspace.preview(changed,str(self.binary))
        self.assertIs(self.workspace.latest,snapshot);self.assertTrue(snapshot.path.exists())

    async def test_fixed_eclipse_framing_child_keeps_capture_and_all_three_frames(self):
        from configurator.comparison import render_set
        result=await render_set(self.workspace,plan(self.view),str(self.binary))
        self.assertEqual(len(result.frames),3);self.assertTrue(all(path.exists() for path in result.frames))
        self.assertEqual(result.plan.epoch,self.view.utc)

    async def test_invalid_association_is_health_failure_before_renderer_execution(self):
        issues=configuration_issues(self.view,str(self.binary),astronomy={'norad':None})
        self.assertTrue(any(issue.severity=='blocking' for issue in issues))
        missing=Workspace();self.addCleanup(missing.close)
        with self.assertRaisesRegex(ValueError,'capture is missing'):await missing.preview(self.view,str(self.binary))
        self.assertIsNone(missing.process);self.assertIsNone(missing.latest)

    async def test_norad_expiring_during_renderer_completion_keeps_prior_success(self):
        scene=replace(self.view,time_mode='now');await self.workspace.preview(scene,str(self.binary));prior=self.workspace.latest
        metadata=self.data['norad'].metadata;clock={'now':metadata['oldest_epoch_at']+metadata['max_age_seconds']}
        original=self.workspace._run_child;boundary=clock['now']
        for completion in (boundary+1,float('nan')):
            clock['now']=boundary
            async def advance_after_render(*args,**kwargs):
                code=await original(*args,**kwargs);clock['now']=completion;return code
            with patch('configurator.astronomy_capture.time.time',side_effect=lambda:clock['now']),patch.object(self.workspace,'_run_child',side_effect=advance_after_render):
                with self.assertRaisesRegex(ValueError,'became unavailable during rendering'):await self.workspace.preview(scene,str(self.binary))
            self.assertIs(self.workspace.latest,prior);self.assertTrue(prior.path.exists());self.assertIsNone(self.workspace.process)
        self.assertEqual(self.workspace.last_outcome,'failed');self.assertIn('Last successful preview retained',self.workspace.last_error)
