"""Repeated Ctrl-C never detaches an in-flight owned filesystem writer."""
import asyncio
import signal
import threading
import unittest
from unittest.mock import patch

from textual.widgets import Input
from configurator.fileio import OwnedFiles
from configurator.owned_io import checkpoint
from tests.configurator.ui import fixtures


class OwnedInterruptTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor

    async def test_second_ctrl_c_waits_for_owned_save_cleanup_before_exit(self):
        target=self.root/'config/scenes/interrupted.conf'
        entered=threading.Event();release=threading.Event();finished=threading.Event()
        original=OwnedFiles.write

        def held_write(owned,name,data):
            original(owned,name,data)
            entered.set()
            try:
                if not release.wait(10):raise AssertionError('filesystem write barrier expired')
                checkpoint()
            finally:finished.set()

        try:
            async with self.app.run_test(size=(110,50)) as pilot:
                self.app.query_one('#latitude',Input).value='25'
                await pilot.pause()
                with patch.object(OwnedFiles,'write',held_write):
                    worker=self.app.run_worker(self.app.save(True,target,self.app.view(),self.app.renderer,keep_open=True))
                    await fixtures.wait_event(entered)
                    owner=self.workspace.owned_io.owner
                    thread=self.workspace.owned_io.thread
                    self.assertTrue(thread.is_alive())
                    self.assertTrue(any(target.parent.iterdir()))
                    await pilot.press('ctrl+c')
                    await fixtures.wait_event(self.workspace.owned_io.cancel)
                    self.assertTrue(self.app.cancelling_operation)
                    self.assertFalse(self.app.leaving)
                    await pilot.press('ctrl+c')
                    async def leaving():
                        while not self.app.leaving:await asyncio.sleep(.005)
                    await asyncio.wait_for(leaving(),3)
                    self.assertEqual(self.app.termination_signal,signal.SIGINT)
                    self.assertIsNone(self.app.return_value)
                    self.assertIs(self.workspace.owned_io.owner,owner)
                    self.assertIs(self.workspace.owned_io.thread,thread)
                    self.assertTrue(thread.is_alive())
                    self.assertFalse(finished.is_set())
                    self.assertFalse(owner.done())
                    self.assertTrue(self.workspace.busy)
                    release.set()
                    await asyncio.wait_for(self.app.workers.wait_for_complete(),3)
            self.assertTrue(finished.is_set())
            self.assertFalse(thread.is_alive())
            self.assertIsNone(self.workspace.owned_io.owner)
            self.assertIsNone(self.workspace.owned_io.thread)
            self.assertFalse(self.workspace.busy)
            self.assertEqual(self.app.return_value,('cancelled',None))
            self.assertEqual(list(target.parent.iterdir()),[])
        finally:release.set()
