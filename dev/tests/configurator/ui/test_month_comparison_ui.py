"""Explicit imagery-month review preserves the source scene."""
import unittest
from unittest.mock import patch
from textual.widgets import Select,Input,Button,Static
import test_app as fixtures
import test_comparison_ui as comparisons
click=fixtures.click

class MonthComparisonUI(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.AppTests.asyncSetUp
    binary=comparisons.ComparisonUITests.binary
    async def test_disabled_stock_review_duplicate_and_cancel_have_no_render(self):
        async with self.app.run_test(size=(120,55)) as pilot:
            self.assertTrue(self.app.query_one('#month-sheet',Button).disabled)
            self.app.query_one('#map-family',Select).value='world';await pilot.pause();before=self.app.raw_fields()
            await click(pilot,'#month-sheet');self.app.screen.query_one('#comparison-month-2',Select).value='01';await click(pilot,'#month-comparison-confirm')
            self.assertIn('distinct',str(self.app.screen.query_one('#month-comparison-error',Static).render()));self.assertIsNone(self.workspace.process)
            await click(pilot,'#month-comparison-back');self.assertEqual(self.app.raw_fields(),before);await pilot.press('ctrl+c')
    async def test_custom_months_render_without_changing_draft_or_opening_viewer(self):
        async with self.app.run_test(size=(120,55)) as pilot:
            self.app.query_one('#map-family',Select).value='world';self.app.query_one('#renderer',Input).value=self.binary();await pilot.pause();before=self.app.raw_fields()
            await click(pilot,'#month-sheet')
            for index,value in enumerate(('02','06','10'),1):self.app.screen.query_one('#comparison-month-'+str(index),Select).value=value
            with patch('configurator.app.open_image') as viewer:
                await click(pilot,'#month-comparison-confirm');await self.app.workers.wait_for_complete();await pilot.pause();viewer.assert_not_called()
            self.assertEqual(self.workspace.comparison_latest.plan.months,('02','06','10'));self.assertEqual(self.app.raw_fields(),before)
            self.assertIn('imagery-month',str(self.app.query_one('#open-sheet',Button).label));await pilot.press('ctrl+c')
