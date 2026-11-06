"""Review-only handoff interaction and preservation tests; no activation."""
from tests.configurator.ui.support_handoff import HandoffUIFixture, prepare_handoff
from tests.configurator.ui.terminal_support import open_terminal
from pathlib import Path
import sys,tempfile,unittest,asyncio,threading
from unittest.mock import patch
from textual.widgets import Button,Input,Static
from configurator.app import ConfiguratorApp
from configurator.handoff import check_bundle
from configurator.library import save_named
from configurator.model import View
from configurator.workspace import Workspace
from configurator.fileio import OwnedFiles
from tests.configurator.ui.fixtures import click




class HandoffUITests(HandoffUIFixture, unittest.IsolatedAsyncioTestCase):




    async def test_open_cancel_review_and_escape_are_readonly_and_preserve_dirty_draft(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();before=self.app.history.current
            await self.enter(pilot)
            self.assertTrue(self.app.screen.dirty)
            await click(pilot,'#handoff-review-button');await pilot.pause()
            self.assertIn('Nothing has been written',self.status());self.assertFalse(self.target.exists())
            review=str(self.app.screen.query_one('#handoff-review',Static).render())
            self.assertIn('earth.jpg',review);self.assertIn('not fully bound',review)
            await pilot.press('escape');await pilot.pause()
            self.assertEqual(self.app.history.current,before);self.assertTrue(self.app.history.dirty)
            self.assertFalse(self.app.leaving);self.assertFalse(self.target.exists())
        self.unchanged()

    async def test_confirm_exports_saved_scene_not_unsaved_draft_then_check_and_back(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();before=self.app.history.current
            await self.enter(pilot);await click(pilot,'#handoff-review-button')
            await click(pilot,'#handoff-confirm');await pilot.pause()
            self.assertIn('No scene selected or activated',self.status())
            record=check_bundle(self.root,self.target);self.assertFalse(record['activation_ready'])
            self.assertEqual((self.target/'earth.conf').read_bytes(),self.source[self.scene])
            await click(pilot,'#handoff-check');await pilot.pause()
            self.assertIn('verified',self.status());await click(pilot,'#handoff-back');await pilot.pause()
            self.assertIn('verified',str(self.app.query_one('#status',Static).render()))
            self.assertEqual(self.app.history.current,before);self.assertIsNone(self.workspace.process)
        self.unchanged()

    async def test_invalid_geometry_and_changed_inputs_require_new_review(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot);self.app.screen.query_one('#handoff-geometry',Input).value='bad';await pilot.pause()
            await click(pilot,'#handoff-review-button');self.assertIn('WIDTHxHEIGHT',self.status())
            self.assertFalse(self.app.screen.query_one('#handoff-confirm',Button).display)
            self.app.screen.query_one('#handoff-geometry',Input).value='1280x720';await pilot.pause()
            await click(pilot,'#handoff-review-button')
            self.app.screen.query_one('#handoff-renderer',Input).value='/not/a/renderer';await pilot.pause()
            self.assertIsNone(self.app.screen.plan);self.assertIn('Review inputs changed',self.status())
            self.assertFalse(self.app.screen.query_one('#handoff-confirm',Button).display)
            self.assertFalse(self.target.exists())
        self.unchanged()

    async def test_stale_source_and_existing_destination_refuse_without_overwriting(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot);await click(pilot,'#handoff-review-button')
            self.legacy.write_bytes(b'new opaque source')
            await click(pilot,'#handoff-confirm');self.assertIn('changed',self.status());self.assertFalse(self.target.exists())
            self.legacy.write_bytes(self.source[self.legacy]);await click(pilot,'#handoff-review-button')
            self.target.mkdir();sentinel=self.target/'keep';sentinel.write_bytes(b'keep')
            await click(pilot,'#handoff-confirm');self.assertIn('refused',self.status());self.assertEqual(sentinel.read_bytes(),b'keep')
            self.assertIn('destination already exists',self.status());self.assertIn('Choose a new name',self.status());self.assertNotIn('[Errno',self.status())
        self.unchanged()

    async def test_failed_publication_cleans_owned_output_and_shows_error(self):
        write=OwnedFiles.write
        def broken(owner,name,raw):write(owner,name,raw);raise OSError('injected disk failure')
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot);await click(pilot,'#handoff-review-button')
            with patch.object(OwnedFiles,'write',autospec=True,side_effect=broken):await click(pilot,'#handoff-confirm')
            self.assertIn('injected disk failure',self.status());self.assertFalse(self.target.exists())
            self.assertFalse(self.app.screen.query_one('#handoff-confirm',Button).display)
        self.unchanged()

    async def test_bad_existing_bundle_and_partial_output_are_reported_without_force_cleanup(self):
        write=OwnedFiles.write
        def broken(owner,name,raw):
            write(owner,name,raw);(self.target/name).write_bytes(b'external edit');raise OSError('injected failure')
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot);await click(pilot,'#handoff-check');self.assertIn('refused',self.status())
            await click(pilot,'#handoff-review-button')
            with patch.object(OwnedFiles,'write',autospec=True,side_effect=broken):await click(pilot,'#handoff-confirm')
            self.assertIn('Partial review output remains',self.status());self.assertTrue(self.target.exists())
            self.assertEqual(next(self.target.iterdir()).read_bytes(),b'external edit')
        self.unchanged()

    async def test_checked_bundle_tamper_is_not_reported_as_valid(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot);await click(pilot,'#handoff-review-button');await click(pilot,'#handoff-confirm')
            (self.target/'earth.conf').write_bytes(b'external edit\n')
            await click(pilot,'#handoff-check');self.assertIn('refused',self.status())
            self.assertNotIn('verified',self.status())
            self.assertEqual((self.target/'earth.conf').read_bytes(),b'external edit\n')
        self.unchanged()



    async def test_apply_requires_confirmation_keeps_dirty_draft_and_never_restarts(self):
        from configurator.selection import inspect_selection,read_revision
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();before=self.app.history.current
            await self.export_and_review_apply(pilot)
            self.assertIsNone(inspect_selection(self.root).revision);self.assertFalse((self.root/'.state').exists())
            self.assertIn('No files or selection changed',self.status())
            await click(pilot,'#handoff-apply-confirm');await pilot.pause()
            selected=inspect_selection(self.root);self.assertIsNotNone(selected.revision);read_revision(self.root,selected.revision)
            self.assertIn('No restart',self.status());self.assertIsNone(self.workspace.process)
            await click(pilot,'#handoff-back');await pilot.pause()
            self.assertEqual(self.app.history.current,before);self.assertTrue(self.app.history.dirty)
            await pilot.press('escape');await pilot.pause()
            self.assertFalse(self.app.leaving);await click(pilot,'#discard-draft');await pilot.pause()
        self.assertEqual(self.app.return_value,('selected',selected.revision))
        for path,raw in self.source.items():self.assertEqual(path.read_bytes(),raw)
        self.assertFalse((self.root/'never-execute').exists())

    async def test_apply_cancel_and_reviewed_restore_leave_original_files_and_revisions(self):
        from configurator.selection import inspect_selection,REVISIONS
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.export_and_review_apply(pilot);await pilot.press('escape');await pilot.pause()
            self.assertIsNone(inspect_selection(self.root).revision);self.assertFalse((self.root/'.state').exists())
            await self.enter(pilot);await click(pilot,'#handoff-apply-review');await click(pilot,'#handoff-apply-confirm')
            selected=inspect_selection(self.root)
            await click(pilot,'#handoff-restore');self.assertEqual(inspect_selection(self.root),selected)
            await click(pilot,'#handoff-restore-confirm');await pilot.pause()
            self.assertIsNone(inspect_selection(self.root).revision);self.assertTrue((self.root/REVISIONS/selected.revision).is_dir())
            self.assertIn('Previous selection restored',self.status())
        for path,raw in self.source.items():self.assertEqual(path.read_bytes(),raw)

    async def test_concurrent_selection_after_review_is_preserved(self):
        from configurator.selection import inspect_selection,SELECTOR
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.export_and_review_apply(pilot)
            raw=b'v1 '+b'a'*64+b'\n';(self.root/SELECTOR).write_bytes(raw)
            await click(pilot,'#handoff-apply-confirm');await pilot.pause()
            self.assertIn('changed',self.status());self.assertEqual((self.root/SELECTOR).read_bytes(),raw)
            self.assertEqual(inspect_selection(self.root).revision,'a'*64);self.assertFalse((self.root/'.state').exists())
        for path,data in self.source.items():self.assertEqual(path.read_bytes(),data)

    async def test_uncertain_selection_is_not_reported_as_success_or_automatically_restored(self):
        from configurator.selection import UncertainSelection
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.export_and_review_apply(pilot)
            with patch('configurator.handoff_ui.apply_bundle',side_effect=UncertainSelection('injected uncertainty')):
                await click(pilot,'#handoff-apply-confirm')
            self.assertIn('outcome uncertain',self.status());self.assertIn('no automatic rollback',self.status())
            self.assertTrue(self.app.screen.query_one('#handoff-restore',Button).disabled)
            await click(pilot,'#handoff-back');await pilot.press('escape');await pilot.pause()
        self.assertEqual(self.app.return_value,('selected','uncertain'))
        self.unchanged()

    async def test_ctrlc_after_confirmed_selection_retains_and_reports_completed_change(self):
        from configurator.selection import inspect_selection
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.export_and_review_apply(pilot);await click(pilot,'#handoff-apply-confirm');await pilot.pause()
            selected=inspect_selection(self.root)
            await pilot.press('ctrl+c');await pilot.pause()
        self.assertEqual(self.app.return_value,('selected',selected.revision))
        self.assertEqual(inspect_selection(self.root),selected)
        for path,data in self.source.items():self.assertEqual(path.read_bytes(),data)

    async def test_slow_review_keeps_ui_responsive_and_escape_cancels_owned_reader(self):
        from configurator.handoff import create_plan
        entered=threading.Event();release=threading.Event()
        def held(*args):
            entered.set()
            if not release.wait(5):raise AssertionError('review barrier expired')
            return create_plan(*args)
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot)
            try:
                with patch('configurator.handoff_ui.create_plan',side_effect=held):
                    await click(pilot,'#handoff-review-button')
                    self.assertTrue(await asyncio.to_thread(entered.wait,3))
                    self.assertTrue(self.workspace.busy)
                    await pilot.press('escape')
                    async def requested():
                        while not self.workspace.owned_io.cancel.is_set():await asyncio.sleep(0)
                    await asyncio.wait_for(requested(),3)
                    release.set()
                    async def finished():
                        while self.workspace.busy:await asyncio.sleep(0)
                    await asyncio.wait_for(finished(),3);await pilot.pause()
                self.assertFalse(self.app.leaving)
                self.assertIn('cancelled',self.status())
                self.assertFalse(self.target.exists())
            finally:release.set()


class HandoffTerminalTests(unittest.TestCase):
    setUp=prepare_handoff

    def test_real_terminal_modal_escape_ctrlc_ctrld_restore_tty_and_original_screen(self):
        import os,select,subprocess,termios,time
        from configurator import __file__ as module_file
        driver=self.root/'terminal_fixture.py'
        driver.write_text('''from pathlib import Path
import sys
from textual.widgets import Button
from configurator.app import ConfiguratorApp
from configurator.workspace import Workspace
class TestApp(ConfiguratorApp):
    def on_mount(self):
        super().on_mount()
        self.call_after_refresh(self.query_one('#handoff',Button).press)
workspace=Workspace()
try:
    result=TestApp(Path(sys.argv[1]),sys.executable,workspace).run()
    sys.exit(3 if result and result[0]=='cancelled' else 2)
finally:workspace.close()
''')
        for key in (b'\x1b\x1b',b'\x03',b'\x04'):
            with self.subTest(key=key):
                master,slave,before=open_terminal()
                env={**os.environ,'TERM':'xterm-256color','HOME':str(self.root),'PYTHONPATH':str(Path(module_file).parent.parent),'PYTHONDONTWRITEBYTECODE':'1'}
                process=subprocess.Popen([sys.executable,'-B',str(driver),str(self.root)],stdin=slave,stdout=slave,stderr=slave,env=env)
                output=b''
                try:
                    deadline=time.monotonic()+10
                    while b'Scene handoff' not in output and time.monotonic()<deadline:
                        if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                    self.assertIn(b'Scene handoff',output)
                    # Distinct Escape presses: close modal first, then leave the editor.
                    for byte in key:
                        os.write(master,bytes([byte]))
                        if key==b'\x1b\x1b':time.sleep(.15)
                    if key==b'\x04':
                        while b'Leave the scene editor?' not in output and time.monotonic()<deadline:
                            if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                        self.assertIn(b'Leave the scene editor?',output)
                        # Open handoff fields are transient, not part of recovery.
                        # Continue editing is the default; explicitly choose discard.
                        os.write(master,b'\t\r')
                    while process.poll() is None and time.monotonic()<deadline:
                        if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                    self.assertEqual(process.wait(timeout=2),3,output[-1000:])
                    while select.select([master],[],[],0)[0]:output+=os.read(master,65536)
                    self.assertIn(b'\x1b[?1049h',output);self.assertIn(b'\x1b[?1049l',output)
                    self.assertEqual(termios.tcgetattr(slave),before);self.assertFalse(self.target.exists())
                finally:
                    if process.poll() is None:process.kill();process.wait()
                    os.close(master);os.close(slave)
        self.unchanged()


    def unchanged(self):
        for path, raw in self.source.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertFalse((self.root / 'never-execute').exists())
        self.assertFalse((self.root / '.state').exists())
