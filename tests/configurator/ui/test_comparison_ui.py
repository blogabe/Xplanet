"""The framing-set UI never changes the draft or opens a viewer implicitly."""
from tests.configurator.ui.support_comparison import ComparisonUIFixture
import sys,unittest
from pathlib import Path
from unittest.mock import patch
from textual.widgets import Button,Input,Select,Static
from tests.configurator.ui import fixtures
click=fixtures.click

class ComparisonUITests(ComparisonUIFixture, unittest.IsolatedAsyncioTestCase):
    async def test_context_review_cancel_render_and_explicit_open(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.assertTrue(self.app.query_one('#framing-sheet',Button).disabled)
            self.assertIn('space view',str(self.app.query_one('#comparison-context',Static).render()))
            self.app.query_one('#projection',Select).value='space';self.app.query_one('#renderer',Input).value=self.binary();await pilot.pause()
            before=self.app.history.current;await click(pilot,'#framing-sheet')
            self.assertIn('1920',' '.join(str(w.render()) for w in self.app.screen.query(Static)))
            await click(pilot,'#comparison-back');self.assertIsNone(self.workspace.comparison_latest)
            await click(pilot,'#framing-sheet')
            with patch('configurator.app.open_image') as open_viewer:
                await click(pilot,'#comparison-confirm');await self.app.workers.wait_for_complete();await pilot.pause()
                self.assertIsNotNone(self.workspace.comparison_latest);open_viewer.assert_not_called()
                self.assertEqual(self.app.history.current,before);self.assertIsNone(self.workspace.latest)
                await click(pilot,'#open-sheet');open_viewer.assert_called_once_with(self.workspace.comparison_latest.index)
            self.app.query_one('#radius',Input).value='30';await pilot.pause()
            self.assertEqual(str(self.app.query_one('#open-sheet',Button).label),'Open prior framing sheet')
            await pilot.press('ctrl+c')
        self.assertFalse((self.root/'config/desktop.scene').exists());self.assertFalse((self.root/'config/scenes').exists())
