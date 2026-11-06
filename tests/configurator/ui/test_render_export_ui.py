"""Explicit retained-image export preserves drafts, sources and lifecycle state."""
import json,unittest
from textual.widgets import Input,Static,Select
from configurator.export_ui import RenderExport
from tests.configurator.ui import fixtures
from tests.configurator.ui import test_resources_ui as resources
click=fixtures.click
class ExportUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor
    renderer=resources.ResourceUITests.renderer
    async def prepare(self,pilot):
        self.app.query_one('#renderer',Input).value=str(self.renderer());await pilot.pause()
        await click(pilot,'#preview');await self.app.workers.wait_for_complete();await pilot.pause()
    async def test_preview_export_cancel_save_and_stale_snapshot_preserve_draft_and_source(self):
        destination=self.root/'dev/saved preview'
        async with self.app.run_test(size=(130,55)) as pilot:
            await self.prepare(pilot);snapshot=self.workspace.latest;raw=snapshot.path.read_bytes()
            await click(pilot,'#export-image');self.assertIsInstance(self.app.screen,RenderExport)
            await pilot.press('escape');self.assertFalse(destination.exists())
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();before=self.app.history.current;dirty=self.app.history.dirty
            await click(pilot,'#export-image');self.app.screen.query_one('#render-export-directory',Input).value=str(destination)
            await click(pilot,'#render-export-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
            self.assertIn('Durable render exported',str(self.app.query_one('#status',Static).render()))
            self.assertEqual(self.app.history.current,before);self.assertEqual(self.app.history.dirty,dirty)
            self.assertIs(self.workspace.latest,snapshot);self.assertEqual((destination/'preview.png').read_bytes(),raw)
            self.assertEqual(json.loads((destination/'export.json').read_text())['scene_summary'],snapshot.view.summary())
        self.assertEqual(list((self.root/'config').iterdir()),[])
        self.workspace.close();self.assertEqual((destination/'preview.png').read_bytes(),raw)
    async def test_failure_keeps_source_and_reenables_export_and_preview(self):
        destination=self.root/'dev/exists';destination.mkdir();(destination/'keep').write_bytes(b'keep')
        async with self.app.run_test(size=(130,55)) as pilot:
            await self.prepare(pilot);snapshot=self.workspace.latest
            await click(pilot,'#export-image');self.app.screen.query_one('#render-export-directory',Input).value=str(destination)
            await click(pilot,'#render-export-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
            self.assertIn('Cannot export',str(self.app.query_one('#status',Static).render()))
            self.assertFalse(self.app.query_one('#export-image').disabled);self.assertFalse(self.app.query_one('#preview').disabled)
            self.assertIs(self.workspace.latest,snapshot);self.assertEqual((destination/'keep').read_bytes(),b'keep')
    async def test_sheet_export_does_not_change_original_preview_or_draft(self):
        destination=self.root/'dev/saved sheet'
        async with self.app.run_test(size=(130,55)) as pilot:
            await self.prepare(pilot);snapshot=self.workspace.latest
            self.app.query_one('#projection',Select).value='space';await pilot.pause()
            await click(pilot,'#framing-sheet');await click(pilot,'#comparison-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
            before=self.app.history.current;sheet=self.workspace.comparison_latest
            await click(pilot,'#export-sheet');self.app.screen.query_one('#render-export-directory',Input).value=str(destination)
            await click(pilot,'#render-export-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
            self.assertEqual(self.app.history.current,before);self.assertIs(self.workspace.latest,snapshot);self.assertIs(self.workspace.comparison_latest,sheet)
            self.assertTrue((destination/'index.html').is_file());self.assertTrue((destination/'frame-3.png').is_file())
        self.assertEqual(list((self.root/'config').iterdir()),[])

    async def test_small_terminal_export_buttons_and_exit_protection_remain_usable(self):
        destination=self.root/'dev/not-written'
        async with self.app.run_test(size=(80,30)) as pilot:
            await self.prepare(pilot);snapshot=self.workspace.latest
            button=self.app.query_one('#export-image');button.scroll_visible(animate=False);await pilot.pause()
            self.assertLessEqual(button.region.right,self.app.size.width)
            await click(pilot,'#export-image');self.app.screen.query_one('#render-export-directory',Input).value=str(destination)
            await pilot.press('ctrl+d');await pilot.pause();self.assertFalse(self.app.leaving)
            self.assertTrue(self.app.screen.query_one('#keep-draft').disabled)
            await click(pilot,'#keep-editing');await pilot.pause();self.assertIsInstance(self.app.screen,RenderExport)
            self.assertEqual(self.app.screen.query_one('#render-export-directory',Input).value,str(destination))
            await pilot.press('escape');self.assertFalse(destination.exists());self.assertTrue(snapshot.path.exists())
        self.assertEqual(list((self.root/'config').iterdir()),[])
