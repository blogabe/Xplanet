"""Exit and display safety without renderer or installed-state access."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from textual.widgets import Input, Static
from configurator.app import ConfiguratorApp, ConfirmDiscard, ReportScreen, STOCK_LIBRARY
from configurator.workspace import Workspace, open_view

class EditorSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'config').mkdir()
        self.workspace=Workspace()
        self.addCleanup(self.workspace.close)
        self.app=ConfiguratorApp(self.root,sys.executable,self.workspace,recovery=False)

    async def test_inherited_quit_respects_dirty_draft_and_palette_is_disabled(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#latitude',Input).value='25'
            await pilot.pause()
            await pilot.press('ctrl+p')
            self.assertEqual(len(self.app.screen_stack),1)
            self.app.action_quit()
            await pilot.pause()
            self.assertIsInstance(self.app.screen,ConfirmDiscard)
            self.app.screen.dismiss(False)
            await pilot.pause()
            self.assertFalse(self.app.leaving)
            self.assertEqual(self.app.query_one('#latitude',Input).value,'25')

    async def test_untrusted_status_and_report_escape_controls_but_expand_tabs(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.status('a\tESC\x1b[2J')
            text=str(self.app.query_one('#status',Static).content)
            self.assertNotIn('\x1b',text)
            self.assertNotIn('\t',text)
            report=ReportScreen('title\x1b', ['a\tb\x1b'])
            self.assertNotIn('\x1b',report.report_title)
            self.assertNotIn('\t',report.sections[0])
            self.assertNotIn('\x1b',report.sections[0])

    async def test_open_default_is_real_shipped_pair_without_dev_directory(self):
        self.assertTrue(STOCK_LIBRARY.is_absolute())
        open_view(STOCK_LIBRARY/'earth-september.conf')
        async with self.app.run_test(size=(100,45)) as pilot:
            button=self.app.query_one('#load')
            button.scroll_visible(animate=False)
            await pilot.pause()
            await pilot.click('#load')
            await pilot.pause()
            self.assertEqual(self.app.screen.query_one('#source-directory',Input).value,str(STOCK_LIBRARY/'earth-september.conf'))
            self.assertFalse((self.root/'dev').exists())

    async def test_terminal_watch_uses_original_descriptors_not_textual_wrappers(self):
        with patch('configurator.app.os.isatty',side_effect=lambda fd:fd in (0,1)) as tty, patch.object(self.app,'external_termination') as terminate:
            self.app.check_terminal()
        self.assertEqual([call.args[0] for call in tty.call_args_list],[0,1])
        terminate.assert_not_called()
