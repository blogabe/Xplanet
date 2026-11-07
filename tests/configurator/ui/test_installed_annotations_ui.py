"""Explicit import, mode retention and undo/save remain usable in the editor."""
import asyncio,unittest
from pathlib import Path
from unittest.mock import patch
from textual.widgets import Input,Select,Static
from tests.configurator.ui import fixtures
from tests.configurator.support_installed_annotations import SOURCES
from configurator.installed_annotations import DATASETS
from configurator.workspace import open_view

class AnnotationUITests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=fixtures.setup_editor
 async def test_explicit_import_undo_redo_save_reopen_and_inactivity(self):
  source=self.root/'installed';source.mkdir()
  for key,text in SOURCES.items():
   path=source/DATASETS[key][0];path.parent.mkdir(exist_ok=True);path.write_text(text)
  saved=self.root/'config/scenes/annotations.conf'
  async with self.app.run_test(size=(110,50)) as pilot:
   self.app.query_one('#projection',Select).value='space';await pilot.pause()
   self.app.query_one('#sky-labels',Select).value='on';self.app.query_one('#sky-constellations',Select).value='on';await pilot.pause()
   self.assertTrue(any(i.severity=='blocking' and i.field=='sky_labels' for i in self.app.current_issues()))
   self.app.query_one('#annotation-source',Input).value=str(source)
   await fixtures.click(pilot,'#import-annotations');await self.app.workers.wait_for_complete();await pilot.pause()
   self.assertIn('1 frozen rows',str(self.app.query_one('#annotation-summary',Static).render()));self.assertTrue(self.app.draft().sky_labels_text)
   self.app.action_undo();await pilot.pause();self.assertFalse(self.app.draft().sky_labels_text)
   self.app.action_redo();await pilot.pause();self.assertTrue(self.app.draft().sky_labels_text)
   self.app.query_one('#projection',Select).value='rectangular';await pilot.pause();self.assertNotIn('-marker_file',self.app.draft().arguments())
   self.assertTrue(self.app.draft().sky_labels_text);self.app.query_one('#destination',Input).value=str(saved)
   await fixtures.click(pilot,'#save-continue');await fixtures.click(pilot,'#confirm-save');await self.app.workers.wait_for_complete();await pilot.pause()
   self.assertEqual(open_view(saved).view,self.app.draft());self.assertNotIn(str(source),'\n'.join(self.app.change_review()))
   self.app.query_one('#projection',Select).value='space';await pilot.pause();self.assertIn('-marker_file',self.app.draft().arguments())
 async def test_failed_and_cancelled_import_preserve_previous_draft(self):
  async with self.app.run_test(size=(100,40)) as pilot:
   self.app.query_one('#target',Select).value='moon';await pilot.pause();self.app.query_one('#moon-sites',Select).value='on';await pilot.pause()
   prior=self.app.raw_fields();self.app.query_one('#annotation-source',Input).value=str(self.root/'missing')
   await fixtures.click(pilot,'#import-annotations');await self.app.workers.wait_for_complete();await pilot.pause()
   self.assertEqual(self.app.raw_fields(),prior);self.assertIn('refused',str(self.app.query_one('#status',Static).render()))
   with patch('configurator.app.import_datasets',side_effect=asyncio.CancelledError):
    await fixtures.click(pilot,'#import-annotations');await self.app.workers.wait_for_complete();await pilot.pause()
   self.assertEqual(self.app.raw_fields(),prior);self.assertFalse(self.workspace.busy);self.assertFalse(self.app.query_one('#content').disabled)

 async def test_cancellation_at_final_source_reread_does_not_apply(self):
  import threading
  from configurator import installed_annotations as module
  source=self.root/'installed';(source/'markers').mkdir(parents=True);(source/'markers/moon').write_text(SOURCES['moon_sites'])
  original=module.read_stable;entered=threading.Event();release=threading.Event();calls=0
  def blocking(*args):
   nonlocal calls
   raw=original(*args);calls+=1
   if calls==2:entered.set();release.wait(3)
   return raw
  async with self.app.run_test(size=(100,40)) as pilot:
   self.app.query_one('#target',Select).value='moon';await pilot.pause();self.app.query_one('#moon-sites',Select).value='on';await pilot.pause();prior=self.app.raw_fields()
   with patch.object(module,'read_stable',side_effect=blocking):
    task=asyncio.create_task(self.app._import_annotations(str(source),('moon_sites',)))
    try:
     await fixtures.wait_event(entered);task.cancel();await asyncio.sleep(.02);release.set();await task
    finally:release.set()
   self.assertEqual(self.app.raw_fields(),prior);self.assertFalse(self.workspace.busy)
   self.assertIn('cancelled',str(self.app.query_one('#status',Static).render()))
