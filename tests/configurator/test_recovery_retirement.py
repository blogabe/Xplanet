"""Finder metadata and owned retirement preserve unrelated/session data."""
import asyncio,os,stat,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
from configurator import recovery
from configurator.draft_session import DraftSession
from configurator.model import SAMPLE
from configurator.owned_io import checkpoint
from tests.configurator.support_recovery import RecoveryFixture

async def event_seen(event):
    async def poll():
        while not event.is_set():await asyncio.sleep(.005)
    await asyncio.wait_for(poll(),3)

class FinderMetadataTests(RecoveryFixture,unittest.IsolatedAsyncioTestCase):
    async def test_owned_regular_session_metadata_is_counted_preserved_and_explicitly_discardable(self):
        session=self.session();await session.checkpoint(*self.proposal());folder=self.store.path/session.identity
        with self.store.directory() as fd:before=self.store.usage(fd)
        root_meta=self.store.path/'.DS_Store';inside=folder/'.DS_Store'
        for path in (root_meta,inside):path.write_bytes(b'Finder metadata');path.chmod(0o644)
        with self.store.directory() as fd:self.assertEqual(self.store.usage(fd),before+2*len(b'Finder metadata'))
        await session.checkpoint(*self.proposal(latitude='30'))
        for path in (root_meta,inside):self.assertEqual(path.read_bytes(),b'Finder metadata');self.assertEqual(path.stat().st_mode&0o777,0o644)
        session.close();self.store.discard(session.identity)
        self.assertFalse(folder.exists());self.assertEqual(root_meta.read_bytes(),b'Finder metadata')

    async def test_linked_finder_metadata_names_exact_path_and_manual_remedy_without_following(self):
        session=self.session();await session.checkpoint(*self.proposal());folder=self.store.path/session.identity
        target=self.root/'unrelated';target.write_bytes(b'do not touch');link=folder/'.DS_Store';link.symlink_to(target)
        head=(folder/'head.json').read_bytes()
        with self.assertRaises(ValueError) as caught:await session.checkpoint(*self.proposal(latitude='30'))
        message=str(caught.exception);self.assertIn(str(link),message);self.assertIn('Inspect this path manually',message);self.assertIn('No permissions were changed',message)
        self.assertEqual(target.read_bytes(),b'do not touch');self.assertTrue(link.is_symlink());self.assertEqual((folder/'head.json').read_bytes(),head)
        session.close()
        with self.assertRaises(ValueError) as caught:self.store.discard(session.identity)
        self.assertIn(str(link),str(caught.exception));self.assertTrue(folder.exists());self.assertEqual(target.read_bytes(),b'do not touch')

    async def test_only_finder_name_gets_permission_exception_and_unknown_discard_is_informative(self):
        session=self.session();await session.checkpoint(*self.proposal());folder=self.store.path/session.identity
        note=folder/'notes';note.write_bytes(b'preserve me');note.chmod(0o644)
        with self.store.directory() as fd,self.assertRaises(ValueError) as caught:self.store.usage(fd)
        self.assertIn(str(note),str(caught.exception));self.assertIn('manually',str(caught.exception));self.assertEqual(note.stat().st_mode&0o777,0o644)
        note.chmod(0o600);session.close()
        with self.assertRaises(ValueError) as caught:self.store.discard(session.identity)
        self.assertIn(str(note),str(caught.exception));self.assertIn('Unrecognized recovery material',str(caught.exception));self.assertEqual(note.read_bytes(),b'preserve me')

    def test_foreign_or_nonregular_finder_metadata_is_not_exempt(self):
        for mode,uid in ((stat.S_IFREG|0o644,os.geteuid()+1),(stat.S_IFDIR|0o700,os.geteuid()),(stat.S_IFLNK|0o777,os.geteuid())):
            with self.subTest(mode=mode,uid=uid),self.assertRaises(ValueError):recovery.finder_regular(SimpleNamespace(st_mode=mode,st_uid=uid))

class RetirementTests(RecoveryFixture,unittest.IsolatedAsyncioTestCase):
    async def controller(self):
        notices=[];controller=DraftSession(self.root,lambda:(self.current,self.baseline,SAMPLE.read_bytes(),self.w,''),notices.append)
        self.addCleanup(controller.close);self.assertTrue(await controller.flush());return controller,notices

    async def test_stop_waits_for_cancelled_verification_and_prevents_new_checkpoints(self):
        controller,notices=await self.controller();identity=controller.session.identity;folder=controller.store.path/identity
        before={path.name:path.read_bytes() for path in folder.iterdir()};entered=threading.Event();release=threading.Event();original=controller.store.discard
        def held(*args,**kwargs):
            entered.set()
            if not release.wait(3):raise AssertionError('test barrier expired')
            checkpoint();return original(*args,**kwargs)
        task=None;stop=None
        try:
            with patch.object(controller.store,'discard',side_effect=held):
                task=asyncio.create_task(controller.discard_current(run=self.w.file_operation));await event_seen(entered)
                self.assertTrue(self.w.busy);controller.changed();controller.start()
                self.assertIsNone(controller.timer);self.assertFalse(await controller.flush());self.assertFalse(await controller.write())
                stop=asyncio.create_task(controller.stop());await event_seen(self.w.owned_io.cancel)
                self.assertFalse(stop.done());self.assertFalse(task.done());release.set()
                self.assertFalse(await asyncio.wait_for(task,3));await asyncio.wait_for(stop,3)
            self.assertEqual({path.name:path.read_bytes() for path in folder.iterdir()},before)
            self.assertIsNone(controller.session);self.assertIsNone(self.w.owned_io.owner);self.assertFalse(self.w.busy)
            self.assertTrue(any('cleanup cancelled' in text.lower() for text in notices));self.assertEqual(controller.store.load(identity).record['current'],self.current)
            controller.changed();self.assertIsNone(controller.timer)
        finally:
            release.set()
            await asyncio.gather(*(item for item in (task,stop) if item is not None),return_exceptions=True)

    async def test_cancellation_after_deletion_commit_returns_actual_completed_outcome(self):
        controller,notices=await self.controller();identity=controller.session.identity;entered=threading.Event();release=threading.Event();original=recovery.OwnedFiles.cleanup
        def held(owned):
            entered.set()
            if not release.wait(3):raise AssertionError('test barrier expired')
            checkpoint();return original(owned)
        task=None
        try:
            with patch.object(recovery.OwnedFiles,'cleanup',held):
                task=asyncio.create_task(controller.discard_current());await event_seen(entered);task.cancel()
                await event_seen(controller.packing.cancel);self.assertFalse(task.done());release.set()
                self.assertTrue(await asyncio.wait_for(task,3))
            self.assertFalse((controller.store.path/identity).exists());self.assertIsNone(controller.retiring);self.assertIsNone(controller.packing.owner)
            self.assertFalse(any('cleanup cancelled' in text.lower() for text in notices))
            self.current['latitude']='35';self.assertTrue(await controller.flush());self.assertNotEqual(controller.session.identity,identity)
            await controller.stop()
        finally:
            release.set()
            if task is not None:await asyncio.gather(task,return_exceptions=True)
