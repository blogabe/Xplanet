"""Exit review does not cancel work until the user commits to leaving."""
import asyncio
import unittest
from unittest.mock import patch
from textual.widgets import Input
from configurator.app import ConfirmDiscard
from tests.configurator.ui import fixtures


class ExitOperationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor

    async def pending_preview(self,release,started,finished):
        self.workspace.busy=True;self.workspace.operation='render'
        started.set()
        try:
            await release.wait()
            return self.root/'completed.png'
        finally:
            self.workspace.busy=False;self.workspace.operation=None;finished.set()

    async def test_keep_editing_preserves_same_preview_and_completion_under_exit_question(self):
        release=asyncio.Event();started=asyncio.Event();finished=asyncio.Event()
        async def preview(*args,**kwargs):return await self.pending_preview(release,started,finished)
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25'
            with patch.object(self.workspace,'preview',side_effect=preview):
                worker=self.app.preview_job=self.app.render(self.app.view(),self.app.renderer)
                await asyncio.wait_for(started.wait(),2)
                await pilot.press('ctrl+d');await pilot.pause()
                self.assertIsInstance(self.app.screen,ConfirmDiscard)
                self.assertFalse(finished.is_set());self.assertFalse(worker.is_cancelled)
                release.set();await asyncio.wait_for(finished.wait(),2);await pilot.pause()
                self.assertIsInstance(self.app.screen,ConfirmDiscard)
                self.app.screen.dismiss(False);await pilot.pause()
                self.assertFalse(self.app.leaving);self.assertFalse(worker.is_cancelled)
                self.assertEqual(self.app.draft().latitude,25)
            await pilot.press('ctrl+c')

    async def test_confirmed_discard_awaits_preview_cleanup(self):
        release=asyncio.Event();started=asyncio.Event();finished=asyncio.Event()
        async def preview(*args,**kwargs):return await self.pending_preview(release,started,finished)
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25'
            with patch.object(self.workspace,'preview',side_effect=preview):
                self.app.preview_job=self.app.render(self.app.view(),self.app.renderer)
                await asyncio.wait_for(started.wait(),2)
                await pilot.press('ctrl+d');await pilot.pause()
                self.assertFalse(finished.is_set())
                self.app.screen.dismiss(True);await pilot.pause()
        self.assertTrue(finished.is_set());self.assertFalse(self.workspace.busy)
        self.assertEqual(self.app.return_value,('cancelled',None))

    async def test_save_completion_under_question_keeps_copy_and_editing_continuity(self):
        import threading
        from configurator.library import save_named
        started=threading.Event();release=threading.Event()
        target=self.root/'config/scenes/saved.conf'
        def save(*args,**kwargs):
            started.set()
            if not release.wait(5):raise AssertionError('publication barrier expired')
            return save_named(*args,**kwargs)
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25'
            with patch('configurator.app.save_named',side_effect=save):
                worker=self.app.run_worker(self.app.save(True,str(target),self.app.view(),self.app.renderer))
                await fixtures.wait_event(started);await pilot.press('ctrl+d');await pilot.pause()
                self.assertIsInstance(self.app.screen,ConfirmDiscard)
                release.set();await worker.wait();await pilot.pause()
                self.assertIsInstance(self.app.screen,ConfirmDiscard)
                self.assertTrue(target.is_file());self.assertEqual(self.app.document.source,target)
                self.app.screen.dismiss(False);await pilot.pause()
                self.assertFalse(self.app.leaving);self.assertFalse(self.app.history.dirty)
            await pilot.press('ctrl+c')
        self.assertEqual(self.app.return_value,('kept',str(target)))

    async def test_failed_recovery_after_confirmed_exit_restores_action_controls(self):
        from configurator.app import ConfiguratorApp
        self.app=ConfiguratorApp(self.root,self.app.renderer,self.workspace,recovery=True)
        release=asyncio.Event();started=asyncio.Event();finished=asyncio.Event()
        async def preview(*args,**kwargs):return await self.pending_preview(release,started,finished)
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25'
            with patch.object(self.workspace,'preview',side_effect=preview), patch.object(self.app.recovery,'flush',return_value=False):
                self.app.preview_job=self.app.render(self.app.view(),self.app.renderer)
                await asyncio.wait_for(started.wait(),2)
                await pilot.press('ctrl+d');await pilot.pause()
                self.app.screen.dismiss('keep');await pilot.pause()
                self.assertTrue(finished.is_set());self.assertFalse(self.app.leaving)
                self.assertFalse(self.app.exit_prompting)
                self.assertFalse(self.app.query_one('#preview').disabled)
                self.assertFalse(self.app.query_one('#load').disabled)
            await pilot.press('ctrl+c')
