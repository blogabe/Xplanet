"""Explicit local-file UI import has no provider or desktop side effects."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from textual.widgets import Input,Static
from configurator.app import ConfiguratorApp
from configurator.model import View,ViewDocument
from configurator.workspace import Workspace
from tests.test_eclipse import TOTAL,TOTAL_URL

async def click(pilot,selector):
    pilot.app.screen.query_one(selector).scroll_visible(animate=False);await pilot.pause();await pilot.click(selector);await pilot.pause()

class LocalEclipseUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
        self.source=self.root/'local.html';self.source.write_bytes(TOTAL)
        self.workspace=Workspace();self.addCleanup(self.workspace.close)
        view=View(eclipse_layer='captured');self.app=ConfiguratorApp(self.root,sys.executable,self.workspace,document=ViewDocument(view,sys.executable,view.body()),recovery=False)

    async def test_cancel_does_not_read_local_file_or_start_worker(self):
        async with self.app.run_test(size=(120,55)) as pilot:
            with patch.object(self.workspace,'import_eclipse_file',new_callable=AsyncMock) as load:
                await click(pilot,'#import-eclipse');await click(pilot,'#eclipse-import-back');load.assert_not_called()
            self.assertEqual(self.app.eclipse_id,'');await pilot.press('ctrl+c')

    async def test_real_worker_import_keeps_now_inactive_and_unknown_origin_visible(self):
        before=self.source.read_bytes(),self.source.stat().st_mtime_ns
        async with self.app.run_test(size=(120,55)) as pilot:
            await click(pilot,'#import-eclipse');self.app.screen.query_one('#eclipse-local-file',Input).value=str(self.source);self.app.screen.query_one('#eclipse-reference-url',Input).value=TOTAL_URL
            await click(pilot,'#eclipse-import-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
            self.assertTrue(self.app.eclipse_id);self.assertEqual(self.app.draft().time_mode,'now');self.assertNotIn('eclipse',self.app.draft().uses_astronomy())
            summary=str(self.app.query_one('#astronomy-summary',Static).render());self.assertIn('authorship NOT verified',summary);self.assertIn('last success unknown',summary)
            self.assertFalse((self.root/'config/desktop.scene').exists());await pilot.press('ctrl+c')
        self.assertEqual(before,(self.source.read_bytes(),self.source.stat().st_mtime_ns))

    async def test_midnight_requires_explicit_day_and_preserves_prior_capture_on_refusal(self):
        from tests.configurator.test_midnight_eclipse import MIDNIGHT
        async with self.app.run_test(size=(120,55)) as pilot:
            await click(pilot,'#import-eclipse');self.app.screen.query_one('#eclipse-local-file',Input).value=str(self.source);self.app.screen.query_one('#eclipse-reference-url',Input).value=TOTAL_URL
            await click(pilot,'#eclipse-import-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
            prior=self.app.eclipse_id;window=self.app.eclipse_window;self.source.write_bytes(MIDNIGHT)
            async def submit(date):
                await click(pilot,'#import-eclipse');self.app.screen.query_one('#eclipse-local-file',Input).value=str(self.source);self.app.screen.query_one('#eclipse-reference-url',Input).value=TOTAL_URL
                self.app.screen.query_one('#eclipse-first-row-date',Input).value=date
                await click(pilot,'#eclipse-import-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
            await submit('');self.assertEqual(self.app.eclipse_id,prior);self.assertEqual(self.app.eclipse_window,window)
            await submit('2027-08-01');self.assertNotEqual(self.app.eclipse_id,prior)
            item=self.workspace.astronomy[self.app.eclipse_id];self.assertEqual(item.window_token,'2027-08-01T23:58:00Z/2027-08-02T00:02:00Z')
            self.assertIn('User-supplied first-row UTC date',str(self.app.query_one('#astronomy-summary',Static).render()))
            self.assertNotIn('eclipse',self.app.draft().uses_astronomy());await pilot.press('ctrl+c')
