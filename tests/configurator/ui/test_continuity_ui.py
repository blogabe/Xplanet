"""Saving continues a draft without overwriting or discarding earlier history."""
import io,unittest
from contextlib import redirect_stdout
from textual.widgets import Button,Input,Static,Select
from configurator.__main__ import report_result
from configurator.workspace import open_view
from configurator.model import ROOT
import test_app as fixtures
click=fixtures.click

class ContinuityUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.AppTests.asyncSetUp

    async def test_continue_save_sets_baseline_keeps_undo_and_reports_prior_copy_on_exit(self):
        target=self.root/'config/scenes/one.conf'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';self.app.query_one('#destination',Input).value=str(target)
            await click(pilot,'#save-continue');await click(pilot,'#confirm-save');await pilot.pause()
            self.assertFalse(self.app.leaving);self.assertFalse(self.app.history.dirty);self.assertTrue(self.app.history.can_undo)
            self.assertEqual(open_view(target).view.latitude,25)
            await pilot.press('ctrl+z');await pilot.pause();self.assertTrue(self.app.history.dirty);self.assertEqual(self.app.draft().latitude,0)
            await pilot.press('escape');await pilot.pause();self.assertFalse(self.app.leaving)
            await click(pilot,'#keep-editing');await pilot.pause();self.assertEqual(self.app.draft().latitude,0)
            await pilot.press('escape');await click(pilot,'#discard-draft');await pilot.pause()
        self.assertEqual(self.app.return_value[:2],('kept',str(target)));self.assertEqual(open_view(target).view.latitude,25)
        out=io.StringIO()
        with redirect_stdout(out):self.assertEqual(report_result(self.app.return_value),0)
        self.assertIn('no additional save',out.getvalue())

    async def test_force_interrupt_leaves_existing_saved_selection_uncertainty_visible(self):
        target=self.root/'config/scenes/one.conf';self.app.selection_label='uncertain'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#destination',Input).value=str(target)
            await click(pilot,'#save-continue');await click(pilot,'#confirm-save');await pilot.pause()
            self.app.query_one('#latitude',Input).value='invalid';await pilot.pause();await pilot.press('ctrl+c')
        self.assertEqual(self.app.return_value,('kept',str(target),'uncertain'))
        with redirect_stdout(io.StringIO()):self.assertEqual(report_result(self.app.return_value),5)

    async def test_library_filters_names_shows_validated_context_and_refuses_bad_pair(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await click(pilot,'#stock');await pilot.pause()
            self.app.screen.query_one('#library-filter',Input).value='earthrise';await pilot.pause()
            self.assertIn('1 shown / 24',str(self.app.screen.query_one('#library-count',Static).render()))
            text=str(self.app.screen.query_one('#library-summary',Static).render());self.assertIn('lunar orbital',text);self.assertIn('1920x1080',text)
            self.app.screen.query_one('#library-filter',Input).value='no-match-ever';await pilot.pause()
            self.assertTrue(self.app.screen.query_one('#library-open',Button).disabled)
            await pilot.press('escape');await pilot.pause();self.assertFalse(self.app.history.dirty)
        self.assertEqual(list((self.root/'config').iterdir()),[])


    async def test_save_continue_collision_and_cancel_do_not_advance_baseline(self):
        target=self.root/'config/scenes/one.conf'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';self.app.query_one('#destination',Input).value=str(target)
            await click(pilot,'#save-continue');await click(pilot,'#back');await pilot.pause()
            self.assertTrue(self.app.history.dirty);self.assertIsNone(self.app.saved);self.assertFalse(target.exists())
            await click(pilot,'#save-continue');await click(pilot,'#confirm-save');await pilot.pause()
            original=target.read_bytes();self.app.query_one('#latitude',Input).value='30';self.app.query_one('#destination',Input).value=str(target)
            await click(pilot,'#save-continue');await click(pilot,'#confirm-save');await pilot.pause()
            self.assertTrue(self.app.history.dirty);self.assertEqual(target.read_bytes(),original)
            await pilot.press('ctrl+d');await click(pilot,'#discard-draft');await pilot.pause()
        self.assertEqual(self.app.return_value,('kept',str(target)))

    async def test_successful_copy_with_failed_reopen_is_reported_without_losing_draft(self):
        from unittest.mock import patch
        target=self.root/'config/scenes/one.conf'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';self.app.query_one('#destination',Input).value=str(target)
            await click(pilot,'#save-continue')
            with patch('configurator.app.open_view',side_effect=ValueError('external replacement')):await click(pilot,'#confirm-save')
            await pilot.pause();self.assertTrue(target.exists());self.assertTrue(self.app.history.dirty)
            self.assertIn('Copy saved',str(self.app.query_one('#status',Static).render()))
            self.assertIn('reopening it failed',str(self.app.query_one('#status',Static).render()))
            self.assertEqual(self.app.draft().latitude,25);await pilot.press('ctrl+c')
        self.assertEqual(open_view(target).view.latitude,25)

    async def test_empty_and_unsupported_libraries_are_readonly(self):
        from configurator.library_ui import SceneLibrary
        library=self.root/'config/scenes';library.mkdir()
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.push_screen(SceneLibrary(library));await pilot.pause()
            self.assertTrue(self.app.screen.query_one('#library-open',Button).disabled)
            self.assertIn('0 shown / 0',str(self.app.screen.query_one('#library-count',Static).render()))
            await pilot.press('escape');await pilot.pause()
            (library/'bad.conf').write_bytes(b'[earth]\nunknown=opaque\n');(library/'bad.def').write_bytes(b'touch NEVER_EXECUTE\n')
            before={p.name:p.read_bytes() for p in library.iterdir()}
            self.app.push_screen(SceneLibrary(library));await pilot.pause()
            self.assertTrue(self.app.screen.query_one('#library-open',Button).disabled)
            self.assertIn('Cannot open this pair',str(self.app.screen.query_one('#library-summary',Static).render()))
            await pilot.press('escape');await pilot.press('ctrl+c')
        self.assertEqual(before,{p.name:p.read_bytes() for p in library.iterdir()});self.assertFalse((self.root/'NEVER_EXECUTE').exists())

    async def test_literal_native_path_and_grid_copy_keeps_source_and_editor_unchanged(self):
        source=self.root/'native.conf';source.write_bytes(b'[earth]\nmap=old.jpg # retain\ngrid=false\nunknown=opaque\n');before=source.read_bytes()
        async with self.app.run_test(size=(110,50)) as pilot:
            await fixtures.NativeValueAppTests.enter(self,pilot,source)
            self.app.screen.query_one('#native-value-map',Input).value='../maps/new.jpg'
            self.app.screen.query_one('#native-value-grid',Input).value='true';await pilot.pause()
            await click(pilot,'#native-patch-review-button');await pilot.pause()
            review=str(self.app.screen.query_one('#native-patch-review',Static).render())
            self.assertIn('old.jpg',review);self.assertIn('../maps/new.jpg',review)
            await click(pilot,'#native-patch-confirm');await pilot.pause()
            self.assertFalse(self.app.history.dirty);await pilot.press('ctrl+c')
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual((self.root/'native-edited.conf').read_bytes(),before.replace(b'old.jpg',b'../maps/new.jpg').replace(b'grid=false',b'grid=true'))


    async def test_name_filter_does_not_reread_unchanged_selected_capture(self):
        from unittest.mock import patch
        from configurator.library_ui import SceneLibrary
        with patch('configurator.library_ui.open_view',wraps=open_view) as inspect:
            async with self.app.run_test(size=(110,50)) as pilot:
                self.app.push_screen(SceneLibrary(ROOT/'scripts/configurator/samples/scenes'));await pilot.pause()
                first=inspect.call_args[0][0];count=inspect.call_count
                # Exact selected name retains the same selected path through filtering.
                name=__import__('pathlib').Path(first).stem
                self.app.screen.query_one('#library-filter',Input).value=name[:2];await pilot.pause()
                self.app.screen.query_one('#library-filter',Input).value=name;await pilot.pause()
                self.assertEqual(inspect.call_count,count)
                await pilot.press('escape');await pilot.press('ctrl+c')


    async def test_real_terminal_dirty_exit_confirmation_and_interrupt_restore_screen(self):
        import os,pty,select,subprocess,sys,termios,time
        from pathlib import Path
        from configurator import __file__ as module
        driver=self.root/'driver.py'
        driver.write_text("""import sys
from pathlib import Path
from textual.widgets import Input
from configurator.app import ConfiguratorApp
from configurator.workspace import Workspace
from configurator.__main__ import report_result
class DirtyApp(ConfiguratorApp):
    def on_mount(self):
        super().on_mount()
        def dirty():
            self.query_one('#latitude',Input).value='25'
            self.run_worker(self.action_cancel())
        self.call_after_refresh(dirty)
    async def action_cancel(self):
        await super().action_cancel()
        path=self.root/'exit-requests'
        path.write_text(str(int(path.read_text())+1) if path.exists() else '1')
    def discard_finished(self,discard):
        super().discard_finished(discard)
        if not discard:(self.root/'kept-dirty').write_text(str(self.history.dirty))
w=Workspace()
try: result=DirtyApp(Path(sys.argv[1]),sys.executable,w).run()
finally: w.close()
sys.exit(report_result(result))
""")
        for interrupt in (b'\x03',b'\x04'):
            (self.root/'exit-requests').unlink(missing_ok=True)
            master,slave=pty.openpty();before=termios.tcgetattr(slave)
            env={**os.environ,'HOME':str(self.root),'TERM':'xterm-256color','PYTHONPATH':str(Path(module).parent.parent),'PYTHONDONTWRITEBYTECODE':'1'}
            process=subprocess.Popen([sys.executable,'-B',str(driver),str(self.root)],stdin=slave,stdout=slave,stderr=slave,env=env,cwd=self.root)
            output=b''
            def until(marker):
                nonlocal output
                deadline=time.monotonic()+10
                while marker not in output and process.poll() is None and time.monotonic()<deadline:
                    if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                self.assertTrue(marker in output,output[-1000:])
            try:
                until(b'Leave the scene editor?')
                if interrupt==b'\x04':
                    os.write(master,b'\r')
                    deadline=time.monotonic()+10
                    while not (self.root/'kept-dirty').exists() and time.monotonic()<deadline:
                        if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                    self.assertEqual((self.root/'kept-dirty').read_text(),'True')
                    # The default decision kept the dirty draft; only Ctrl-D exits.
                    self.assertIsNone(process.poll())
                os.write(master,interrupt)
                if interrupt==b'\x04':
                    deadline=time.monotonic()+10
                    while (not (self.root/'exit-requests').exists() or int((self.root/'exit-requests').read_text())<2) and time.monotonic()<deadline:
                        if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                    self.assertIsNone(process.poll());os.write(master,b'\x03')
                deadline=time.monotonic()+10
                while process.poll() is None and time.monotonic()<deadline:
                    if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                self.assertEqual(process.wait(timeout=2),3,output[-1000:])
                while select.select([master],[],[],0)[0]:output+=os.read(master,65536)
                self.assertIn(b'\x1b[?1049h',output);self.assertIn(b'\x1b[?1049l',output)
                self.assertEqual(termios.tcgetattr(slave),before);self.assertFalse((self.root/'config/scenes').exists())
            finally:
                if process.poll() is None:process.kill();process.wait()
                os.close(master);os.close(slave)
