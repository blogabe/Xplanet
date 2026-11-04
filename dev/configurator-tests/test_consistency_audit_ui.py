"""Same-session selection/save outcomes and diagnostic preflight stay truthful."""
import io,unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from textual.widgets import Input,Static
from configurator.__main__ import report_result
from configurator.selection import inspect_selection,UncertainSelection
import test_app as fixtures
import test_handoff_ui as handoff_fixtures
click=fixtures.click

class AuditDiagnosticUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.AppTests.asyncSetUp

    async def test_missing_renderer_diagnostic_modal_contains_actionable_failure(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#renderer',Input).value='/missing/renderer';await pilot.pause()
            await click(pilot,'#resources');await self.app.workers.wait_for_complete();await pilot.pause()
            text='\n'.join(str(widget.render()) for widget in self.app.screen.query(Static))
            self.assertIn('Last attempt: failed',text);self.assertIn('absolute path to an installed Xplanet',text)
            self.assertIsNone(self.workspace.process);self.assertIsNone(self.workspace.latest)

class SelectionSaveUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=handoff_fixtures.HandoffUITests.asyncSetUp
    enter=handoff_fixtures.HandoffUITests.enter
    export_and_review_apply=handoff_fixtures.HandoffUITests.export_and_review_apply

    async def test_successful_apply_then_save_reports_both_and_preserves_selection(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.export_and_review_apply(pilot);await click(pilot,'#handoff-apply-confirm');await pilot.pause()
            selected=inspect_selection(self.root);self.assertIsNotNone(selected.revision)
            await click(pilot,'#handoff-back');await pilot.pause()
            self.app.query_one('#destination',Input).value=str(self.root/'config/scenes/new-copy.conf')
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        result=self.app.return_value;self.assertEqual(result[0],'saved');self.assertEqual(result[2],selected.revision)
        self.assertEqual(inspect_selection(self.root),selected);output=io.StringIO()
        with redirect_stdout(output):self.assertEqual(report_result(result),0)
        self.assertIn(selected.revision,output.getvalue());self.assertNotIn('desktop settings were not changed',output.getvalue())

    async def test_uncertain_apply_then_saved_copy_still_requires_inspection(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.export_and_review_apply(pilot)
            with patch('configurator.handoff_ui.apply_bundle',side_effect=UncertainSelection('fixture')):
                await click(pilot,'#handoff-apply-confirm');await pilot.pause()
            await click(pilot,'#handoff-back');await pilot.pause()
            self.app.query_one('#destination',Input).value=str(self.root/'config/scenes/new-copy.conf')
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        result=self.app.return_value;self.assertEqual(result[2],'uncertain');self.assertTrue((self.root/'config/scenes/new-copy.conf').is_file())
        output=io.StringIO()
        with redirect_stdout(output):self.assertEqual(report_result(result),5)
        self.assertIn('inspect config/desktop.scene',output.getvalue());self.assertNotIn('desktop settings were not changed',output.getvalue())
