"""Slow local inspections remain interruptible and never detach their reader."""
import asyncio
import threading
import unittest
from unittest.mock import patch
from textual.widgets import Input,Static
from configurator.library_ui import SceneLibrary
from configurator.selection_info_ui import SelectedSceneScreen
from configurator.recovery_ui import RecoveryScreen
from configurator.recovery import RecoveryStore
from configurator.owned_io import checkpoint
from tests.configurator.ui import fixtures


reached=fixtures.wait_event

class InspectionResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor

    async def test_library_reader_is_owned_off_loop_and_ctrl_c_cancels_before_exit(self):
        started=threading.Event();finished=threading.Event();threads=[]
        def slow(_):
            threads.append(threading.get_ident());started.set()
            try:
                while True:checkpoint();threading.Event().wait(.005)
            finally:finished.set()
        async with self.app.run_test(size=(110,50)) as pilot:
            with patch('configurator.library_ui.list_scenes',side_effect=slow):
                self.app.push_screen(SceneLibrary(self.root/'config/scenes'))
                await reached(started)
                self.app.screen.query_one('#library-filter',Input).value='earth'
                await pilot.pause()
                self.assertEqual(self.app.screen.query_one('#library-filter',Input).value,'earth')
                self.assertNotEqual(threads,[threading.get_ident()])
                await pilot.press('ctrl+c');await pilot.pause()
                self.assertTrue(finished.is_set());self.assertFalse(self.workspace.busy)
                self.assertFalse(self.app.leaving)
                await pilot.press('escape');await pilot.pause()
            await pilot.press('ctrl+c')
        self.assertFalse((self.root/'config/scenes').exists())

    async def test_selected_scene_and_recovery_lists_cancel_owned_reader_on_back(self):
        for kind in ('selected','recovery'):
            with self.subTest(kind=kind):
                # A fresh app is required after the previous run's terminal exit.
                if kind=='recovery':fixtures.prepare_editor(self)
                started=threading.Event();finished=threading.Event()
                def slow(*args):
                    started.set()
                    try:
                        while True:checkpoint();threading.Event().wait(.005)
                    finally:finished.set()
                target='configurator.selection_info_ui.inspect_selected' if kind=='selected' else 'configurator.recovery.RecoveryStore.entries'
                async with self.app.run_test(size=(110,50)) as pilot:
                    with patch(target,side_effect=slow):
                        self.app.push_screen(SelectedSceneScreen(self.root) if kind=='selected' else RecoveryScreen(RecoveryStore(self.root)))
                        await reached(started)
                        await pilot.press('escape');await pilot.pause()
                        self.assertTrue(finished.is_set());self.assertFalse(self.workspace.busy)
                        self.assertEqual(len(self.app.screen_stack),1)
                    await pilot.press('ctrl+c')

    async def test_native_inspection_does_not_publish_result_above_exit_question(self):
        started=threading.Event();release=threading.Event()
        from configurator.native_inspection import NativeReview
        def slow(_):
            started.set()
            while not release.wait(.005):checkpoint()
            return NativeReview(self.root,())
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25'
            with patch('configurator.app.inspect_native',side_effect=slow):
                self.app.inspect_source(str(self.root))
                await reached(started);await pilot.press('ctrl+d');await pilot.pause()
                from configurator.app import ConfirmDiscard,NativeReviewScreen
                self.assertIsInstance(self.app.screen,ConfirmDiscard)
                release.set();await pilot.pause()
                self.assertIsInstance(self.app.screen,ConfirmDiscard)
                self.app.screen.dismiss(False);await pilot.pause()
                self.assertIsInstance(self.app.screen,NativeReviewScreen)
                self.assertEqual(self.app.draft().latitude,25)
                await pilot.press('escape');await pilot.pause()
            await pilot.press('ctrl+c')

    async def test_library_stale_reader_cannot_enable_open_for_an_unverified_selection(self):
        from configurator.app import STOCK_LIBRARY
        from configurator.workspace import open_view
        from textual.widgets import Select,Button
        started=threading.Event();release=threading.Event();first=[True]
        def inspect(source):
            if first[0]:
                first[0]=False;started.set()
                while not release.wait(.005):checkpoint()
            return open_view(source)
        async with self.app.run_test(size=(110,50)) as pilot:
            with patch('configurator.library_ui.open_view',side_effect=inspect):
                self.app.push_screen(SceneLibrary(STOCK_LIBRARY))
                await reached(started)
                screen=self.app.screen
                screen.query_one('#library-filter',Input).value='moon-from-earth'
                await pilot.pause()
                self.assertTrue(screen.query_one('#library-open',Button).disabled)
                release.set();await asyncio.wait_for(screen.inspection_worker.wait(),3);await pilot.pause()
                self.assertTrue(str(screen.query_one('#library-selection',Select).value).endswith('moon-from-earth.conf'))
                self.assertFalse(screen.query_one('#library-open',Button).disabled)
                self.assertIn('Moon',str(screen.query_one('#library-summary',Static).content))
                await pilot.press('escape');await pilot.pause()
            await pilot.press('ctrl+c')

    async def test_repeated_back_while_reader_cleanup_waits_dismisses_once(self):
        started=asyncio.Event();release=asyncio.Event()
        async def stop():started.set();await release.wait()
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25'
            screen=SceneLibrary(self.root/'config/scenes')
            self.app.push_screen(screen);await self.app.workers.wait_for_complete();await pilot.pause()
            with patch.object(self.workspace,'stop',side_effect=stop):
                screen.action_back();screen.action_back()
                await asyncio.wait_for(started.wait(),2)
                self.assertEqual(len(self.app.screen_stack),2)
                release.set();await self.app.workers.wait_for_complete();await pilot.pause()
                self.assertEqual(len(self.app.screen_stack),1)
                self.assertEqual(self.app.draft().latitude,25)
            await pilot.press('ctrl+c')
