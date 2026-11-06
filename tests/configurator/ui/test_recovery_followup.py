"""Completed saves remain truthful when owned reopen/recovery work is cancelled."""
import asyncio,threading,unittest
from unittest.mock import patch
from textual.widgets import Input,Static
from configurator.app import ConfiguratorApp
from configurator.workspace import open_view
from configurator.owned_io import checkpoint
from tests.configurator.ui import fixtures

class SaveFollowupTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor

    async def test_ctrl_c_during_reopen_reports_committed_copy_and_preserves_dirty_draft(self):
        target=self.root/'config/scenes/copy.conf';entered=threading.Event();release=threading.Event();original=open_view
        def held(source):
            entered.set()
            if not release.wait(3):raise AssertionError('test barrier expired')
            checkpoint();return original(source)
        try:
            async with self.app.run_test(size=(110,50)) as pilot:
                self.app.query_one('#latitude',Input).value='25';await pilot.pause();draft=self.app.raw_fields()
                with patch('configurator.app.open_view',side_effect=held):
                    worker=self.app.run_worker(self.app.save(True,target,self.app.view(),self.app.renderer,keep_open=True))
                    await fixtures.wait_event(entered);self.assertTrue(target.exists());await pilot.press('ctrl+c');await fixtures.wait_event(self.workspace.owned_io.cancel)
                    release.set();await self.app.workers.wait_for_complete();await pilot.pause()
                text=str(self.app.query_one('#status',Static).content)
                self.assertIn('Copy saved to',text);self.assertIn('reopening the saved copy was cancelled',text);self.assertNotIn('Save cancelled;',text)
                self.assertEqual(self.app.raw_fields(),draft);self.assertTrue(self.app.history.dirty);self.assertFalse(self.app.leaving);self.assertIsNone(self.app.return_value)
                self.assertFalse(self.app.query_one('#content').disabled);self.assertEqual(open_view(target).view.latitude,25)
                await pilot.press('ctrl+c')
            self.assertEqual(self.app.completed_result()[0],'kept');self.assertEqual(open_view(target).view.latitude,25)
        finally:release.set()

    async def test_ctrl_c_during_recovery_verification_keeps_saved_copy_and_prior_checkpoint(self):
        self.app=ConfiguratorApp(self.root,self.app.renderer,self.workspace,recovery=True)
        target=self.root/'config/scenes/copy.conf';entered=threading.Event();release=threading.Event();original=self.app.recovery.store.discard
        def held(*args,**kwargs):
            entered.set()
            if not release.wait(3):raise AssertionError('test barrier expired')
            checkpoint();return original(*args,**kwargs)
        try:
            async with self.app.run_test(size=(110,50)) as pilot:
                self.app.query_one('#latitude',Input).value='25';await pilot.pause();self.assertTrue(await self.app.recovery.flush());identity=self.app.recovery.session.identity
                with patch.object(self.app.recovery.store,'discard',side_effect=held):
                    self.app.run_worker(self.app.save(True,target,self.app.view(),self.app.renderer,keep_open=True))
                    await fixtures.wait_event(entered);self.assertTrue(target.exists());self.assertTrue(self.workspace.busy)
                    await pilot.press('ctrl+c');await fixtures.wait_event(self.workspace.owned_io.cancel);release.set()
                    await self.app.workers.wait_for_complete();await pilot.pause()
                self.assertFalse(self.app.history.dirty);self.assertFalse(self.app.leaving);self.assertIsNone(self.app.return_value)
                self.assertIn('cleanup cancelled',self.app.recovery_notice.lower());self.assertEqual(open_view(target).view.latitude,25)
                self.assertTrue((self.app.recovery.store.path/identity).exists());self.assertIsNone(self.app.recovery.session)
                self.assertEqual(self.app.recovery.store.load(identity).record['current']['latitude'],'25')
                await pilot.press('ctrl+c')
            self.assertEqual(self.app.completed_result()[0],'kept');self.assertTrue(target.exists())
        finally:release.set()


    async def test_hash_bound_older_escaped_observation_scene_refuses_open_and_preserves_dirty_draft(self):
        import hashlib
        from types import MethodType,SimpleNamespace
        from configurator.library import save_named
        from configurator.model import View
        from configurator.observation_capture import names,META_FILE,json_bytes,payload_names
        from tests.configurator.support_observations import ObservationCaptureFixture
        from totalmarker.quake_geojson import render_marker as producer_marker
        producer=SimpleNamespace(addCleanup=self.addCleanup)
        for name in ('install','save_state','capture'):setattr(producer,name,MethodType(getattr(ObservationCaptureFixture,name),producer))
        ObservationCaptureFixture.setUp(producer);frozen=producer.capture(('quake',));cases=[]
        for suffix,row in (('quote',b'1 2 "Quote \\" text" color=Red\n'),('slash',b'1 2 "Backslash \\\\ text" color=Red\n')):
            source=save_named(self.root/'config/scenes'/('old-'+suffix+'.conf'),View(quake_layer='captured',observations_id=frozen.identity),self.app.renderer,observations=frozen)
            marker=names('quake')[0];bad=b'# Frozen TotalMarker quake markers v1\n'+row
            meta=frozen.metadata;meta['files'][marker]=hashlib.sha256(bad).hexdigest()
            meta['products']['quake']['source_marker_sha256']=hashlib.sha256(producer_marker(row,1700000000)).hexdigest()
            raw=json_bytes(meta);identity=hashlib.sha256(raw).hexdigest()
            (source.parent/(source.stem+'.'+marker)).write_bytes(bad)
            (source.parent/(source.stem+'.'+META_FILE)).write_bytes(raw)
            definition=source.with_suffix('.def');definition.write_bytes(definition.read_bytes().replace(frozen.identity.encode(),identity.encode()))
            self.assertIn(marker,payload_names(raw));self.assertEqual(meta['files'][marker],hashlib.sha256(bad).hexdigest())
            self.assertIn(identity.encode(),definition.read_bytes())
            cases.append(source)
        before={path.name:(path.read_bytes(),path.stat().st_mtime_ns) for source in cases for path in source.parent.glob(source.stem+'.*')}
        message='Unsafe older observation label; create a new draft and recapture it from the producer.'
        for source in cases:
            with self.subTest(source=source.name),self.assertRaisesRegex(ValueError,'Unsafe older observation label'):open_view(source)
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();draft=self.app.raw_fields();document=self.app.document
            for source in cases:
                await fixtures.click(pilot,'#load');self.app.screen.query_one('#source-directory',Input).value=str(source)
                await fixtures.click(pilot,'#confirm-open');await self.app.workers.wait_for_complete();await pilot.pause()
                self.assertIn(message,str(self.app.query_one('#status',Static).content))
                self.assertIs(self.app.document,document);self.assertEqual(self.app.raw_fields(),draft);self.assertTrue(self.app.history.dirty)
                self.assertIsNone(self.workspace.process)
            await pilot.press('ctrl+c')
        after={path.name:(path.read_bytes(),path.stat().st_mtime_ns) for source in cases for path in source.parent.glob(source.stem+'.*')}
        self.assertEqual(before,after)
