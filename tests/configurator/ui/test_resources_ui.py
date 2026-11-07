"""Explicit resource diagnostics and geometry never apply scenes or run jobs."""
from tests.configurator.ui.support_resources import ResourceUIFixture
import sys,unittest
from unittest.mock import patch
from configurator.binary_diagnostics import load as load_binary_evidence
from configurator.app import ConfiguratorApp
from configurator.workspace import Workspace
from pathlib import Path
from textual.widgets import Input,Static
from configurator.model import View
from configurator.workspace import open_view
from tests.configurator.ui import fixtures
click=fixtures.click


class ResourceUITests(ResourceUIFixture, unittest.IsolatedAsyncioTestCase):


    async def test_explicit_diagnostic_report_and_health_show_evidence_not_false_lookup_failures(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#renderer',Input).value=str(self.renderer());await pilot.pause()
            self.assertEqual(self.app.query_one('#geometry',Input).value,'1920x1080')
            self.assertIsNone(self.workspace.capabilities)
            await click(pilot,'#health');await pilot.pause();self.assertIsNone(self.workspace.capabilities)
            await click(pilot,'#close-report')
            await click(pilot,'#resources');await self.app.workers.wait_for_complete();await pilot.pause()
            text='\n'.join(str(widget.render()) for widget in self.app.screen.query(Static))
            self.assertIn('PNG',text);self.assertIn('/fixture/earth.jpg',text);self.assertIn('normal, not a source failure',text)
            self.assertIn('(1920, 1080)',text);self.assertIsNone(self.workspace.process)
            await click(pilot,'#close-report');await click(pilot,'#health')
            text='\n'.join(str(widget.render()) for widget in self.app.screen.query(Static))
            self.assertIn('Self-reported compiled support',text)
        self.assertEqual(list((self.root/'config').iterdir()),[])
        recorded=load_binary_evidence(self.root);self.assertEqual(recorded,self.workspace.capabilities)
        with patch('configurator.workspace.Workspace._run_child',side_effect=AssertionError('opening does not probe')):
            other=Workspace()
            try:
                app=ConfiguratorApp(self.root,str(recorded.renderer),other,recovery=False)
                self.assertEqual(app.workspace.capabilities,recorded)
                self.assertTrue(recorded.matches(recorded.renderer))
            finally:other.close()

    async def test_known_missing_png_is_actionable_and_changing_binary_invalidates_cached_claim(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#renderer',Input).value=str(self.renderer(False));await pilot.pause()
            await click(pilot,'#resources');await self.app.workers.wait_for_complete();await pilot.pause()
            await click(pilot,'#close-report');await click(pilot,'#health')
            text='\n'.join(str(widget.render()) for widget in self.app.screen.query(Static))
            self.assertIn('reports no PNG support',text);self.assertIsNone(self.workspace.latest)
            await click(pilot,'#close-report')
            new=self.root/'other renderer';new.write_text('#!/bin/sh\nexit 1\n');new.chmod(0o700)
            self.app.query_one('#renderer',Input).value=str(new);await pilot.pause();await click(pilot,'#health')
            text='\n'.join(str(widget.render()) for widget in self.app.screen.query(Static))
            self.assertIn('stale or belongs to another',text)
            self.assertFalse(any(i.severity=='blocking' and 'PNG' in i.message for i in self.app.current_issues()))

    async def test_geometry_changes_invalidate_preview_and_roundtrip_with_undo_and_reopen(self):
        source=self.root/'config/scenes/new-frame.conf'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#renderer',Input).value=str(self.renderer());await pilot.pause()
            await click(pilot,'#preview');await self.app.workers.wait_for_complete();await pilot.pause()
            self.app.query_one('#geometry',Input).value='2160x1080';await pilot.pause()
            self.assertIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            await pilot.press('ctrl+z');await pilot.pause();self.assertEqual(self.app.query_one('#geometry',Input).value,'1920x1080')
            await pilot.press('ctrl+y');await pilot.pause();self.assertEqual(self.app.query_one('#geometry',Input).value,'2160x1080')
            self.app.query_one('#geometry',Input).value='16384x16384';await pilot.pause()
            await click(pilot,'#preview');self.assertIn('16,777,216',str(self.app.query_one('#status',Static).render()))
            self.app.query_one('#geometry',Input).value='2160x1080';self.app.query_one('#destination',Input).value=str(source);await pilot.pause()
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        self.assertEqual(open_view(source).view.geometry,'2160x1080');self.assertIn(b'scene v17',source.with_suffix('.def').read_bytes())


    async def test_evidence_readable_at_narrow_width(self):
        await self.check_readable_evidence((60, 25))

    async def test_evidence_readable_at_wide_width(self):
        await self.check_readable_evidence((120, 45))
