"""Astronomy controls never refresh providers or activate a scene."""
import asyncio
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
from textual.widgets import Select,Input,Static
from configurator.app import ConfiguratorApp
from configurator.model import ViewDocument
from configurator.workspace import Workspace,open_view
# The CI UI job supplies only scripts; reuse offline producer fixtures explicitly.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import test_astronomy_scene as fixtures


async def click(pilot,selector):
    pilot.app.screen.query_one(selector).scroll_visible(animate=False);await pilot.pause();await pilot.click(selector);await pilot.pause()


class AstronomyUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture=fixtures.AstronomySceneTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.view,self.data=self.fixture.scene()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
        self.workspace=Workspace();self.addCleanup(self.workspace.close)
        document=ViewDocument(self.view,sys.executable,self.view.body(),astronomy=tuple(self.data.values()))
        self.app=ConfiguratorApp(self.root,sys.executable,self.workspace,document=document,recovery=False)
        self.app.copy_destination=lambda:str(self.root/'config/scenes/event-copy.conf')

    async def test_modes_keep_captures_and_report_current_vs_prediction_eligibility(self):
        async with self.app.run_test(size=(120,55)) as pilot:
            await pilot.pause();self.assertEqual(self.app.draft().uses_astronomy(),('eclipse',))
            self.assertIn('Fixed UTC',str(self.app.query_one('#astronomy-summary',Static).render()))
            ids=(self.app.norad_id,self.app.eclipse_id,self.app.eclipse_window)
            self.app.query_one('#time-mode',Select).value='now';await pilot.pause()
            self.assertEqual(self.app.draft().uses_astronomy(),('norad',));self.assertIn('inactive',str(self.app.query_one('#astronomy-summary',Static).render()))
            self.app.query_one('#target',Select).value='mars';await pilot.pause()
            self.assertEqual(self.app.draft().uses_astronomy(),());self.assertFalse(self.app.query_one('#control-norad-layer').display)
            self.assertEqual((self.app.norad_id,self.app.eclipse_id,self.app.eclipse_window),ids)
            self.app.action_undo();await pilot.pause();self.assertEqual(self.app.draft().target,'earth')
            self.app.action_undo();await pilot.pause();self.assertEqual(self.app.draft().time_mode,'fixed')
            await pilot.press('ctrl+c')

    async def test_capture_cancel_does_not_start_worker_and_prediction_button_is_honest(self):
        async with self.app.run_test(size=(120,55)) as pilot:
            with patch.object(self.workspace,'capture_astronomy',new_callable=AsyncMock) as capture:
                await click(pilot,'#capture-eclipse')
                self.assertIn('prediction',str(self.app.screen.query_one('#confirm-capture').label))
                await click(pilot,'#back-capture');capture.assert_not_called()
            self.assertEqual(self.app.eclipse_id,self.data['eclipse'].identity)
            await pilot.press('ctrl+c')

    async def test_actual_readonly_worker_capture_undo_and_save_keep_all_associations(self):
        before={str(path.relative_to(self.fixture.root)):(path.read_bytes(),path.stat().st_mtime_ns) for path in self.fixture.root.rglob('*') if path.is_file()}
        async with self.app.run_test(size=(120,55)) as pilot:
            self.app.query_one('#capture-root',Input).value=str(self.fixture.root.resolve());self.app.query_one('#capture-config',Input).value='config.ini'
            await click(pilot,'#capture-norad');await click(pilot,'#confirm-capture');await self.app.workers.wait_for_complete();await pilot.pause()
            new_id=self.app.norad_id;self.assertNotEqual(new_id,self.data['norad'].identity)
            self.assertIn(new_id,self.workspace.astronomy)
            self.app.action_undo();await pilot.pause();self.assertEqual(self.app.norad_id,self.data['norad'].identity)
            self.app.action_redo();await pilot.pause();self.assertEqual(self.app.norad_id,new_id)
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        path=self.root/'config/scenes/event-copy.conf';doc=open_view(path)
        self.assertEqual(doc.view.norad_id,new_id);self.assertEqual(len(doc.astronomy),2)
        self.assertEqual(before,{str(path.relative_to(self.fixture.root)):(path.read_bytes(),path.stat().st_mtime_ns) for path in self.fixture.root.rglob('*') if path.is_file()})
        self.assertFalse((self.root/'config/desktop.scene').exists())

    async def test_failed_capture_retains_prior_ids_interval_and_preview(self):
        from configurator.workspace import PreviewSnapshot
        from configurator.resources import identity
        image=self.root/'retained-preview-fixture.png';image.write_bytes(b'prior image fixture')
        binary=Path(sys.executable).resolve()
        snapshot=PreviewSnapshot(image,self.view,binary,self.view.render_digest(),'fixture time','',binary_identity=identity(binary),image_identity=identity(image))
        self.workspace.latest=snapshot;before=(self.app.norad_id,self.app.eclipse_id,self.app.eclipse_window)
        async with self.app.run_test(size=(120,55)) as pilot:
            with patch.object(self.workspace,'capture_astronomy',new_callable=AsyncMock,side_effect=ValueError('fixture source unavailable')):
                await click(pilot,'#capture-norad');await click(pilot,'#confirm-capture');await self.app.workers.wait_for_complete();await pilot.pause()
            self.assertEqual((self.app.norad_id,self.app.eclipse_id,self.app.eclipse_window),before)
            self.assertIs(self.workspace.latest,snapshot);self.assertEqual(image.read_bytes(),b'prior image fixture')
            self.assertIn('Previous capture and preview retained',str(self.app.query_one('#status',Static).render()))
            await pilot.press('ctrl+c')
