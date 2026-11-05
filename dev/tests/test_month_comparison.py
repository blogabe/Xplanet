"""Bundled imagery changes, never camera/time or current-data identity."""
from dataclasses import replace
from datetime import datetime,timezone
import json,unittest
from unittest.mock import patch
from configurator.comparison import plan,reason,render_set
from configurator.model import View
from configurator.render_export import export_snapshot
from . import test_comparison as fixtures

class MonthComparisonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixtures.ComparisonTests.setUp(self)
        self.view=View(projection='orthographic',latitude=12,longitude=65,map_family='world',month='03')
    async def test_plan_changes_only_three_declared_imagery_months_and_freezes_now_once(self):
        review=plan(self.view,kind='months',months=('01','07','12'),now=datetime(2027,8,2,12,tzinfo=timezone.utc))
        self.assertEqual(review.parameter,'month');self.assertEqual(review.months,('01','07','12'))
        for view,month in zip(review.views,review.months):
            self.assertEqual(view.month,month);self.assertEqual(view.time_mode,'fixed');self.assertEqual(view.utc,review.epoch)
            for field,value in vars(self.view).items():
                if field not in ('month','geometry','time_mode','utc'):self.assertEqual(getattr(view,field),value)
        self.assertEqual(self.view.month,'03');self.assertEqual(self.view.time_mode,'now')
    async def test_default_months_are_three_distinct_values_relative_to_selected_month(self):
        review=plan(self.view,kind='months');self.assertEqual(review.months,('03','07','11'))
    async def test_stock_planetary_live_data_and_malformed_months_refuse_before_render(self):
        for view in (View(),replace(self.view,target='mars'),replace(self.view,clouds='captured'),replace(self.view,storm_layer='captured'),replace(self.view,norad_layer='captured')):
            with self.assertRaises(ValueError):plan(view,kind='months')
        for months in (('01','01','02'),('00','03','05'),('01','02'),(None,'02','03'),([1],'02','03'),3):
            with self.assertRaises(ValueError):plan(self.view,kind='months',months=months)
        self.assertFalse(list(self.workspace.root.iterdir()))
    async def test_render_export_and_previous_preview_remain_intact(self):
        await self.workspace.preview(self.view,str(self.binary));prior=self.workspace.latest
        review=plan(self.view,kind='months',months=('02','06','10'));result=await render_set(self.workspace,review,str(self.binary))
        self.assertIs(self.workspace.latest,prior);self.assertEqual(len(result.frames),3)
        page=result.index.read_text();self.assertIn('bundled 2004 imagery months',page);self.assertIn('world',page)
        self.assertIn('not different simulated scene times',page)
        exported=await export_snapshot(self.workspace,'sheet',result,self.root/'month-export')
        record=json.loads((exported/'export.json').read_text());self.assertEqual(record['parameter'],'month')
        frames=json.loads((exported/'comparison.json').read_text())['frames'];self.assertEqual([row['value'] for row in frames],['02','06','10'])
        self.assertTrue(all(row['epoch']==review.epoch for row in frames));self.workspace.close();self.assertTrue((exported/'frame-1.png').exists())
    async def test_forged_camera_or_undeclared_month_changes_are_refused(self):
        review=plan(self.view,kind='months')
        for field,value in (('longitude',66),('month','12')):
            changed=replace(review,views=(replace(review.views[0],**{field:value}),*review.views[1:]))
            with self.assertRaisesRegex(ValueError,'plan changed'):await render_set(self.workspace,changed,str(self.binary))
        self.assertFalse(self.workspace.busy);self.assertFalse(list(self.workspace.root.iterdir()))
    async def test_later_failure_retains_complete_month_sheet(self):
        review=plan(self.view,kind='months');prior=await render_set(self.workspace,review,str(self.binary))
        with patch('configurator.comparison.png_bytes',side_effect=ValueError('fixture image failure')),self.assertRaises(ValueError):await render_set(self.workspace,review,str(self.binary))
        self.assertIs(self.workspace.comparison_latest,prior);self.assertTrue(prior.index.exists());self.assertIsNone(self.workspace.comparison_workspace)
    async def test_now_to_fixed_must_not_activate_retained_eclipse(self):
        view=replace(self.view,eclipse_layer='captured',eclipse_window='2027-08-02T11:30:00Z/2027-08-02T11:34:00Z')
        with self.assertRaisesRegex(ValueError,'eligibility'):plan(view,kind='months',now=datetime(2027,8,2,11,32,tzinfo=timezone.utc))
