"""Bundled in-app help preserves the draft and any editable dialog beneath it."""
import unittest
from unittest.mock import patch
from textual.widgets import Button,Input,Markdown,Static
from configurator.help_ui import StudioHelp
import test_app as fixtures
click=fixtures.click

class HelpUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.AppTests.asyncSetUp

    async def test_f1_and_help_button_show_same_manual_without_writes_or_viewer(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            before=self.app.history.current
            with patch('configurator.app.open_image') as viewer:
                await pilot.press('f1');await pilot.pause();self.assertIsInstance(self.app.screen,StudioHelp)
                markdown=self.app.screen.query_one('#studio-help-text',Markdown)
                self.assertIn('Scene studio user guide',markdown.source);self.assertFalse(markdown._open_links)
                await pilot.press('f1');await pilot.pause();self.assertFalse(isinstance(self.app.screen,StudioHelp))
                await click(pilot,'#help');await pilot.pause();self.assertIsInstance(self.app.screen,StudioHelp)
                self.app.screen.on_markdown_link_clicked(Markdown.LinkClicked(self.app.screen.query_one(Markdown),'recovery.md'))
                self.assertIn('no browser opened',str(self.app.screen.query_one('#studio-help-link',Static).render()))
                await pilot.press('escape');await pilot.pause();viewer.assert_not_called()
            self.assertEqual(self.app.history.current,before);self.assertFalse(self.app.history.dirty)
            await pilot.press('ctrl+d')
        self.assertEqual(list((self.root/'config').iterdir()),[]);self.assertFalse((self.root/'.state').exists())

    async def test_help_over_editable_form_does_not_bypass_exit_protection(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await click(pilot,'#load');await pilot.pause();form=self.app.screen
            form.query_one('#source-directory',Input).value='/not/opened/unsaved'
            await pilot.press('f1');await pilot.pause();self.assertIsInstance(self.app.screen,StudioHelp)
            await pilot.press('ctrl+d');await pilot.pause()
            self.assertFalse(self.app.leaving);self.assertTrue(self.app.screen.query_one('#keep-draft',Button).disabled)
            await click(pilot,'#keep-editing');await pilot.press('escape');await pilot.pause()
            self.assertIs(self.app.screen,form);self.assertEqual(form.query_one('#source-directory',Input).value,'/not/opened/unsaved')
            await pilot.press('escape');await pilot.press('ctrl+d')
        self.assertFalse((self.root/'.state').exists())

    async def test_looping_manual_parent_is_an_actionable_help_screen(self):
        parent=self.root/'manual-loop';parent.symlink_to('manual-loop',target_is_directory=True)
        async with self.app.run_test(size=(110,50)) as pilot:
            with patch('configurator.guide.GUIDE',parent/'user-guide.md'):
                await pilot.press('f1');await pilot.pause()
            self.assertIn('Help unavailable',self.app.screen.query_one(Markdown).source)
            await pilot.press('escape');await pilot.press('ctrl+d')
        self.assertFalse((self.root/'.state').exists())

    async def test_missing_manual_is_a_readonly_actionable_help_screen(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            with patch('configurator.help_ui.read_guide',side_effect=OSError('missing bundled guide')):
                await pilot.press('f1');await pilot.pause()
            self.assertIn('Help unavailable',self.app.screen.query_one(Markdown).source)
            self.assertIn('Restore docs/',self.app.screen.query_one(Markdown).source)
            await pilot.press('escape');await pilot.press('ctrl+d')
        self.assertFalse((self.root/'.state').exists())
