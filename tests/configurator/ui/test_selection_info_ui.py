"""Selection clarity is an explicit, readonly flow with deliberate draft opening."""
from pathlib import Path
import sys,unittest
from textual.widgets import Button,Input,Static
from tests.configurator.ui import fixtures
from configurator.app import ConfiguratorApp
from configurator.model import View
from configurator.library import save_named
from configurator.handoff import create_plan,stage_plan
from configurator.selection import inspect_selection,apply_bundle,SELECTOR,REVISIONS
click=fixtures.click


class SelectedInfoUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor

    def selected(self):
        scene=save_named(self.root/'config/scenes/chosen.conf',View(),sys.executable)
        bundle=self.root/'review';stage_plan(create_plan(self.root,scene,sys.executable,'1280x720'),bundle)
        return apply_bundle(self.root,bundle,inspect_selection(self.root))

    async def test_legacy_is_not_auto_imported_or_treated_as_running(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await click(pilot,'#selected-scene');await pilot.pause()
            text=str(self.app.screen.query_one('#selected-scene-info',Static).render())
            self.assertIn('custom configuration default',text);self.assertIn('not a claim about the running renderer',text)
            self.assertTrue(self.app.screen.query_one('#selected-scene-open',Button).disabled)
            await pilot.press('escape');await pilot.pause();self.assertFalse(self.app.leaving)
        self.assertEqual(list((self.root/'config').iterdir()),[])

    async def test_review_and_back_preserve_dirty_draft_and_selection(self):
        receipt=self.selected()
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();draft=self.app.history.current
            await click(pilot,'#selected-scene');await pilot.pause()
            text=str(self.app.screen.query_one('#selected-scene-info',Static).render())
            self.assertIn('desktop geometry: 1280x720',text);self.assertIn('preview geometry: 1920x1080',text)
            await click(pilot,'#selected-scene-back');await pilot.pause()
            self.assertEqual(self.app.history.current,draft);self.assertTrue(self.app.history.dirty)
        self.assertEqual(inspect_selection(self.root),receipt.after)

    async def test_opening_frozen_native_draft_retains_renderer_and_saves_only_new_library_copy(self):
        receipt=self.selected();folder=self.root/REVISIONS/receipt.after.revision
        original={p.name:p.read_bytes() for p in folder.iterdir()}
        self.app.copy_destination=ConfiguratorApp.copy_destination.__get__(self.app)
        async with self.app.run_test(size=(110,50)) as pilot:
            renderer=self.app.query_one('#renderer',Input).value
            await click(pilot,'#selected-scene');await click(pilot,'#selected-scene-open');await pilot.pause()
            self.assertEqual(self.app.query_one('#renderer',Input).value,renderer)
            self.assertEqual(self.app.query_one('#geometry',Input).value,'1920x1080')
            self.assertEqual(self.app.query_one('#destination',Input).value,str(self.root/'config/scenes/chosen-copy.conf'))
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        self.assertTrue((self.root/'config/scenes/chosen-copy.conf').is_file())
        self.assertEqual(original,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertEqual(inspect_selection(self.root),receipt.after)

    async def test_invalid_selection_and_changed_choice_on_open_preserve_files_and_draft(self):
        receipt=self.selected();path=self.root/SELECTOR
        async with self.app.run_test(size=(110,50)) as pilot:
            await click(pilot,'#selected-scene');await pilot.pause()
            path.write_bytes(b'new invalid selector')
            await click(pilot,'#selected-scene-open');await pilot.pause()
            self.assertIn('Cannot open',str(self.app.screen.query_one('#selected-scene-info',Static).render()))
            self.assertTrue(self.app.screen.query_one('#selected-scene-open',Button).disabled)
            await click(pilot,'#selected-scene-refresh');await pilot.pause()
            self.assertIn('No custom configuration fallback',str(self.app.screen.query_one('#selected-scene-info',Static).render()))
        self.assertEqual(path.read_bytes(),b'new invalid selector')
