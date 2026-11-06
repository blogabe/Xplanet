"""Private draft storage never touches native scenes, providers or selectors."""
import asyncio,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from configurator.recovery import RecoveryStore,raw_fields,pack,head,digest,encoded,metadata,BUDGET
from configurator.workspace import Workspace
from configurator.model import SAMPLE

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.store=RecoveryStore(self.root);self.w=Workspace();self.addCleanup(self.w.close)
        self.baseline=raw_fields(renderer='/local/renderer');self.current={**self.baseline,'latitude':'-x','places_text':'invalid geographic text'}
        self.sessions=[]
        self.addCleanup(lambda:[session.close() for session in self.sessions])
    def session(self):
        session=self.store.new_session();self.sessions.append(session);return session
    def proposal(self,**changes):return pack({**self.current,**changes},self.baseline,SAMPLE.read_bytes(),self.w,'source hint only.conf')

    async def test_entry_is_readonly_and_invalid_draft_roundtrips_without_execution(self):
        self.assertEqual(self.store.entries(),[]);self.assertEqual(list(self.root.iterdir()),[])
        session=self.session();record,blobs=self.proposal(renderer='$(must-not-execute)')
        sha=await session.checkpoint(record,blobs)
        self.assertTrue(self.store.entries()[0]['active'])
        with self.assertRaisesRegex(ValueError,'active'):self.store.load(session.identity)
        session.close();recovered=self.store.load(session.identity)
        self.assertEqual(recovered.record['current'],record['current']);self.assertEqual(recovered.revision,sha)
        self.assertEqual(recovered.record['baseline'],self.baseline);self.assertEqual(recovered.config,SAMPLE.read_bytes())
        self.assertFalse((self.root/'config').exists());self.assertFalse((self.root/'must-not-execute').exists())
        self.assertEqual(self.store.path.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o077==0 for p in self.store.path.rglob('*')))

    async def test_three_writes_keep_two_complete_revisions_and_reuse_objects(self):
        session=self.session();revisions=[]
        for latitude in ('-x','20','30'):
            record,blobs=self.proposal(latitude=latitude);revisions.append(await session.checkpoint(record,blobs))
        with self.store.session(session.identity) as fd:self.assertEqual(head(fd),list(reversed(revisions[-2:])))
        files=list((self.store.path/session.identity).iterdir())
        self.assertEqual(len([p for p in files if p.name.endswith('.json')]),3) # head + two manifests
        self.assertEqual(len([p for p in files if len(p.name)==64]),1) # shared body bytes
        session.close();self.assertEqual(self.store.load(session.identity).record['current']['latitude'],'30')

    async def test_corrupt_latest_falls_back_and_never_repairs_or_deletes(self):
        session=self.session();first=await session.checkpoint(*self.proposal(latitude='10'));second=await session.checkpoint(*self.proposal(latitude='20'));session.close()
        bad=self.store.path/session.identity/(second+'.json');bad.write_bytes(b'broken')
        before={p.name:p.read_bytes() for p in bad.parent.iterdir()}
        recovered=self.store.load(session.identity);self.assertTrue(recovered.fallback);self.assertEqual(recovered.revision,first)
        self.assertEqual(before,{p.name:p.read_bytes() for p in bad.parent.iterdir()})
        with self.assertRaises(ValueError):self.store.discard(session.identity)
        self.assertEqual(bad.read_bytes(),b'broken')

    async def test_failure_before_atomic_head_keeps_previous_complete_checkpoint(self):
        session=self.session();first=await session.checkpoint(*self.proposal())
        with patch('configurator.recovery.os.replace',side_effect=OSError('disk failure')),self.assertRaises(OSError):await session.checkpoint(*self.proposal(latitude='10'))
        session.close();self.assertEqual(self.store.load(session.identity).revision,first)
        self.assertFalse(any(p.name.startswith('.pending-') for p in (self.store.path/session.identity).iterdir()))

    async def test_cancellation_after_commit_does_not_erase_published_revision(self):
        session=self.session();await session.checkpoint(*self.proposal())
        with patch.object(session,'_prune',side_effect=asyncio.CancelledError),self.assertRaises(asyncio.CancelledError):await session.checkpoint(*self.proposal(latitude='25'))
        session.close();self.assertEqual(self.store.load(session.identity).record['current']['latitude'],'25')

    async def test_budget_failure_does_not_evict_another_unsaved_session(self):
        first=self.session();await first.checkpoint(*self.proposal());first.close()
        original={str(p.relative_to(self.store.path)):p.read_bytes() for p in self.store.path.rglob('*') if p.is_file()}
        self.store.budget=1;second=self.session()
        with self.assertRaisesRegex(ValueError,'budget'):await second.checkpoint(*self.proposal(latitude='30'))
        self.assertEqual(self.store.load(first.identity).record['current'],self.current)
        for name,data in original.items():self.assertEqual((self.store.path/name).read_bytes(),data)

    async def test_nonblocking_lock_and_distinct_sessions_preserve_concurrent_editors(self):
        first,second=self.session(),self.session();await first.checkpoint(*self.proposal())
        with self.store.directory() as fd,self.store.lock(fd):
            with self.assertRaisesRegex(ValueError,'busy'):await second.checkpoint(*self.proposal(latitude='40'))
        await second.checkpoint(*self.proposal(latitude='40'))
        self.assertNotEqual(first.identity,second.identity)
        with self.assertRaisesRegex(ValueError,'Active'):self.store.discard(first.identity)
        first.close();second.close();self.assertEqual(len(self.store.entries()),2)
        self.assertEqual(self.store.load(first.identity).record['current']['latitude'],'-x')
        self.assertEqual(self.store.load(second.identity).record['current']['latitude'],'40')

    async def test_links_and_private_permission_violations_refuse_without_chmod(self):
        outside=self.root/'outside';outside.mkdir();(self.root/'.state').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):await self.session().checkpoint(*self.proposal())
        self.assertEqual(list(outside.iterdir()),[]);(self.root/'.state').unlink()
        session=self.session();sha=await session.checkpoint(*self.proposal());session.close()
        parent=self.store.path/session.identity;file=parent/(sha+'.json');file.chmod(0o644)
        with self.assertRaises(ValueError):self.store.load(session.identity)
        self.assertEqual(file.stat().st_mode&0o777,0o644)

    async def test_explicit_discard_removes_only_verified_session_and_refuses_extra_material(self):
        first,second=self.session(),self.session();await first.checkpoint(*self.proposal());await second.checkpoint(*self.proposal(latitude='5'));first.close();second.close()
        extra=self.store.path/first.identity/'personal-note';extra.write_text('keep');extra.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'Unrecognized'):self.store.discard(first.identity)
        self.assertEqual(extra.read_text(),'keep');extra.unlink()
        self.store.discard(first.identity);self.assertFalse((self.store.path/first.identity).exists())
        self.assertEqual(self.store.load(second.identity).record['current']['latitude'],'5')

    async def test_oversized_and_unsupported_fields_are_not_serialized(self):
        for change in ({'projection':'unknown'},{'latitude':'x'*262145},{'renderer':'bad\x1bpath'},{'capture_id':'0'*64}):
            with self.subTest(change=list(change)),self.assertRaises(ValueError):self.proposal(**change)
        self.assertFalse(self.store.path.exists())

    async def test_frozen_cloud_and_observations_recover_after_sources_are_gone(self):
        from tests.configurator.test_configurator import CloudCaptureTests
        from tests.configurator.test_observation_capture import ObservationCaptureTests
        cloud_fixture=CloudCaptureTests();cloud_fixture.setUp();self.addCleanup(cloud_fixture.doCleanups)
        obs_fixture=ObservationCaptureTests();obs_fixture.setUp();self.addCleanup(obs_fixture.doCleanups)
        cloud=cloud_fixture.capture();observed=obs_fixture.capture();self.w.register_capture(cloud);self.w.register_observations(observed)
        session=self.session();record,blobs=self.proposal(capture_id=cloud.identity,clouds='captured',observations_id=observed.identity,storm_layer='captured')
        await session.checkpoint(record,blobs)
        original={p.name:(p.stat().st_mtime_ns,p.read_bytes()) for p in (self.store.path/session.identity).iterdir() if len(p.name)==64}
        newer={**record,'at':record['at']+1,'current':{**record['current'],'latitude':'other-invalid'}}
        await session.checkpoint(newer,blobs)
        for name,(stamp,raw) in original.items():
            path=self.store.path/session.identity/name;self.assertEqual(path.stat().st_mtime_ns,stamp);self.assertEqual(path.read_bytes(),raw)
        session.close();cloud_fixture.tmp.cleanup();obs_fixture.temp.cleanup()
        recovered=self.store.load(session.identity)
        self.assertEqual(recovered.clouds,(cloud,));self.assertEqual(recovered.observations,(observed,))
        stored=b''.join(p.read_bytes() for p in (self.store.path/session.identity).iterdir() if p.name.endswith('.json'))
        self.assertNotIn(b'PrivatePassword',stored);self.assertNotIn(b'PrivateUser',stored)
        self.assertNotIn(str(cloud_fixture.root).encode(),stored);self.assertNotIn(str(obs_fixture.root).encode(),stored)

    async def test_cancelled_blob_write_preserves_old_head_and_external_material(self):
        from tests.configurator.test_configurator import CloudCaptureTests
        fixture=CloudCaptureTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        frozen=fixture.capture();self.w.register_capture(frozen)
        session=self.session();old=await session.checkpoint(*self.proposal())
        record,blobs=self.proposal(capture_id=frozen.identity,clouds='captured')
        old_names={p.name for p in (self.store.path/session.identity).iterdir()}
        task=asyncio.create_task(session.checkpoint(record,blobs))
        new=None
        for _ in range(100):
            await asyncio.sleep(0)
            added=[p for p in (self.store.path/session.identity).iterdir() if p.name not in old_names and len(p.name)==64]
            if added:new=added[0];break
        self.assertIsNotNone(new);new.write_bytes(b'external edit');new.chmod(0o600)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(new.read_bytes(),b'external edit')
        session.close();self.assertEqual(self.store.load(session.identity).revision,old)

    async def test_cancellation_before_commit_cleans_only_owned_partial_bytes(self):
        from tests.configurator.test_configurator import CloudCaptureTests
        fixture=CloudCaptureTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        frozen=fixture.capture();self.w.register_capture(frozen)
        session=self.session();old=await session.checkpoint(*self.proposal())
        record,blobs=self.proposal(capture_id=frozen.identity,clouds='captured')
        original={p.name:p.read_bytes() for p in (self.store.path/session.identity).iterdir()}
        task=asyncio.create_task(session.checkpoint(record,blobs));await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(original,{p.name:p.read_bytes() for p in (self.store.path/session.identity).iterdir()})
        session.close();self.assertEqual(self.store.load(session.identity).revision,old)

    async def test_hash_shaped_unindexed_user_material_is_never_adopted_for_pruning(self):
        session=self.session();await session.checkpoint(*self.proposal(latitude='1'))
        raw=b'private unrelated material';extra=self.store.path/session.identity/(digest(raw)+'.json');extra.write_bytes(raw);extra.chmod(0o600)
        await session.checkpoint(*self.proposal(latitude='2'));await session.checkpoint(*self.proposal(latitude='3'))
        self.assertEqual(extra.read_bytes(),raw);session.close()
        with self.assertRaisesRegex(ValueError,'Unrecognized'):self.store.discard(session.identity)

class DraftSessionTests(unittest.IsolatedAsyncioTestCase):
    setUp=RecoveryTests.setUp
    async def test_debounce_max_delay_flush_and_noop_do_not_rewrite_checkpoint(self):
        from configurator.draft_session import DraftSession
        notices=[];controller=DraftSession(self.root,lambda:(self.current,self.baseline,SAMPLE.read_bytes(),self.w,''),notices.append)
        self.addCleanup(controller.close)
        controller.changed();first=controller.first_pending
        controller.first_pending=first-4.7;controller.changed()
        self.assertLessEqual(controller.timer.when()-asyncio.get_running_loop().time(),.31)
        self.assertTrue(await controller.flush());identity=controller.last_complete
        self.assertTrue(await controller.flush());self.assertEqual(controller.last_complete,identity)
        await controller.discard_current();self.assertFalse((controller.store.path/identity[0]).exists())
        await controller.stop()

    async def test_document_boundary_retains_earlier_complete_session(self):
        from configurator.draft_session import DraftSession
        controller=DraftSession(self.root,lambda:(self.current,self.baseline,SAMPLE.read_bytes(),self.w,''),lambda text:None)
        self.addCleanup(controller.close)
        await controller.flush();old=controller.session.identity;controller.boundary()
        self.current['latitude']='50';await controller.flush();new=controller.session.identity
        self.assertNotEqual(old,new);await controller.stop();controller.close()
        self.assertEqual(controller.store.load(old).record['current']['latitude'],'-x')
        self.assertEqual(controller.store.load(new).record['current']['latitude'],'50')

class RecoveryDirectoryTests(unittest.IsolatedAsyncioTestCase):
    setUp=RecoveryTests.setUp
    session=RecoveryTests.session
    proposal=RecoveryTests.proposal

    async def test_moved_recovery_root_never_writes_replacement_directory(self):
        session=self.session();old=await session.checkpoint(*self.proposal());moved=self.root/'moved-drafts';original=os.replace
        def replace(source,target,*args,**kwargs):
            self.store.path.rename(moved);self.store.path.mkdir(mode=0o700);sentinel=self.store.path/'keep';sentinel.write_bytes(b'concurrent material');sentinel.chmod(0o600)
            return original(source,target,*args,**kwargs)
        with patch('configurator.recovery.os.replace',side_effect=replace),self.assertRaises(ValueError):await session.checkpoint(*self.proposal(latitude='15'))
        self.assertEqual((self.store.path/'keep').read_bytes(),b'concurrent material')
        # Held descriptors wrote only into the moved private recovery namespace.
        import json
        value=json.loads((moved/session.identity/'head.json').read_bytes())
        self.assertTrue(all((moved/session.identity/(sha+'.json')).exists() for sha in value['revisions']))
