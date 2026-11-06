"""Recovery and interruption use disposable editor roots and owned children only."""
import asyncio,os,signal,sys,unittest
from pathlib import Path
from textual.widgets import Input,Button,Static,Checkbox
from configurator.app import ConfiguratorApp
import test_app as fixtures
click=fixtures.click

class RecoveryUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.AppTests.asyncSetUp(self)
        self.app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),self.workspace,recovery=True)

    async def test_opening_and_cancelling_clean_editor_creates_no_recovery_files(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await click(pilot,'#recovery');self.assertIn('No recoverable sessions',str(self.app.screen.query_one('#recovery-details',Static).render()))
            await pilot.press('escape');await pilot.press('ctrl+d')
        self.assertEqual(self.app.return_value,('cancelled',None));self.assertFalse((self.root/'.state').exists())

    async def test_ctrl_d_keeps_raw_invalid_draft_and_explicit_recovery_never_renders(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='-invalid';await pilot.pause()
            await pilot.press('ctrl+d');await pilot.pause()
            self.assertFalse(self.app.leaving);await click(pilot,'#keep-draft');await pilot.pause()
        self.assertEqual(self.app.return_value[0],'draft')
        store=self.app.recovery.store;rows=store.entries();self.assertEqual(len(rows),1);self.assertFalse(rows[0]['active'])
        self.assertEqual(store.load(rows[0]['id']).record['current']['latitude'],'-invalid')
        app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),recovery=True)
        try:
            async with app.run_test(size=(110,50)) as pilot:
                await click(pilot,'#recovery');await click(pilot,'#recovery-inspect')
                self.assertFalse(app.screen.query_one('#recovery-recover',Button).disabled)
                await click(pilot,'#recovery-recover');await pilot.pause()
                self.assertEqual(app.query_one('#latitude',Input).value,'-invalid');self.assertTrue(app.history.dirty)
                self.assertFalse(app.history.can_redo);self.assertIsNone(app.workspace.process);self.assertIsNone(app.workspace.latest)
                self.assertIn('No source reread',str(app.query_one('#status',Static).render()))
                await pilot.press('ctrl+c')
        finally:app.workspace.close()
        self.assertFalse((self.root/'config/desktop.scene').exists());self.assertFalse((self.root/'config/scenes').exists())

    async def test_dirty_exit_default_continues_and_explicit_discard_removes_only_own_draft(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='20';await pilot.pause();self.assertTrue(await self.app.recovery.flush())
            identity=self.app.recovery.session.identity
            await pilot.press('ctrl+q');await pilot.pause();await click(pilot,'#keep-editing');await pilot.pause()
            self.assertTrue(self.app.history.dirty);self.assertFalse(self.app.leaving)
            await pilot.press('ctrl+d');await click(pilot,'#discard-draft');await pilot.pause()
        self.assertFalse((self.app.recovery.store.path/identity).exists())
        self.assertFalse((self.root/'config/scenes').exists())

    async def test_recovery_failure_keeps_exit_dialog_from_claiming_latest_draft_is_kept(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.recovery.store.budget=1;self.app.query_one('#latitude',Input).value='20';await pilot.pause()
            await pilot.press('ctrl+d');await click(pilot,'#keep-draft');await pilot.pause()
            self.assertFalse(self.app.leaving);self.assertIsNone(self.app.return_value)
            self.assertIn('could not be checkpointed',str(self.app.query_one('#status',Static).render()))
            await pilot.press('ctrl+c')
        self.assertEqual(self.app.termination_signal,signal.SIGINT)
        self.assertFalse((self.root/'config/scenes').exists())

    async def test_save_continue_retires_obsolete_recovery_without_overwriting_scene(self):
        target=self.root/'config/scenes/one.conf'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='20';self.app.query_one('#destination',Input).value=str(target);await pilot.pause()
            await self.app.recovery.flush();identity=self.app.recovery.session.identity
            await click(pilot,'#save-continue');await click(pilot,'#confirm-save');await pilot.pause()
            self.assertFalse(self.app.history.dirty);self.assertTrue(target.exists())
            self.assertFalse((self.app.recovery.store.path/identity).exists())
            await pilot.press('ctrl+d')
        self.assertEqual(self.app.return_value,('kept',str(target)))

    def renderer(self,ignore_term=False):
        path=self.root/'renderer';path.write_text('#!'+sys.executable+'\nimport signal,time\n'+('signal.signal(signal.SIGTERM,signal.SIG_IGN)\n' if ignore_term else '')+'time.sleep(30)\n');path.chmod(0o700);return path

    async def test_ctrl_c_cancels_active_preview_then_idle_ctrl_c_exits(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#renderer',Input).value=str(self.renderer());await click(pilot,'#preview')
            async def started():
                while self.workspace.process is None:await asyncio.sleep(.001)
            await asyncio.wait_for(started(),3);process=self.workspace.process
            await pilot.press('ctrl+c');await pilot.pause()
            self.assertFalse(self.app.leaving);self.assertIsNone(self.workspace.process);self.assertIsNotNone(process.returncode)
            self.assertIn('cancelled',str(self.app.query_one('#status',Static).render()))
            await pilot.press('ctrl+c')
        self.assertEqual(self.app.termination_signal,signal.SIGINT)

    async def test_second_interrupt_escalates_and_keeps_selection_uncertainty(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#renderer',Input).value=str(self.renderer(True));await click(pilot,'#preview')
            async def started():
                while self.workspace.process is None:await asyncio.sleep(.001)
            await asyncio.wait_for(started(),3);process=self.workspace.process
            # Enter the same cancelling state as a first queued key; exercise a
            # second key without waiting for Textual's pilot idle drain.
            self.app.cancelling_operation=True;self.app.selection_label='uncertain'
            await pilot.press('ctrl+c');await pilot.pause()
            self.assertTrue(self.app.leaving);self.assertIsNotNone(process.returncode)
        self.assertEqual(self.app.return_value,('selected','uncertain'));self.assertIsNone(self.workspace.process)

    async def test_real_terminal_signals_and_double_ctrl_c_reap_only_owned_renderer(self):
        import fcntl,pty,select,subprocess,termios,time
        from configurator import __file__ as module
        control=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
        try:
            for trigger,expected in ((signal.SIGTERM,143),(signal.SIGHUP,129),(signal.SIGINT,130),(None,130)):
                root=self.root/('signal-'+str(trigger));root.mkdir();(root/'config').mkdir()
                original=root/'config/xp.conf';original.write_bytes(b'personal source must not be inspected or replaced\n')
                renderer=root/'renderer';renderer.write_text('#!'+sys.executable+'\nimport signal,time,pathlib,os\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\npathlib.Path('+repr(str(root/'child-ready'))+').write_text(str(os.getpid()))\ntime.sleep(30)\n');renderer.chmod(0o700)
                driver=root/'driver.py';driver.write_text('''import asyncio,sys
from pathlib import Path
from textual.widgets import Input
import configurator.__main__ as entry
from configurator.app import ConfiguratorApp
class TestApp(ConfiguratorApp):
    def on_mount(self,event):
        event.prevent_default()
        super().on_mount()
        self.query_one('#latitude',Input).value='25'
        original=self.workspace.kill_owned
        def kill():
            (self.root/'escalated').write_text('owned group only')
            original()
        self.workspace.kill_owned=kill
        self.run_worker(self.arm())
    async def arm(self):
        try:
            (self.root/'arm-started').write_text('started')
            assert await self.recovery.flush()
            (self.root/'arm-flushed').write_text('flushed')
            self.preview_job=self.render(self.view(),self.query_one('#renderer',Input).value)
            while self.workspace.process is None or not (self.root/'child-ready').exists():
                if self.preview_job.state.name in ('ERROR','SUCCESS','CANCELLED'):raise ValueError('Renderer ended before ready: '+str(self.workspace.last_error))
                await asyncio.sleep(.001)
            (self.root/'ready').write_text(str(self.workspace.process.pid))
        except Exception as exc:(self.root/'arm-error').write_text(repr(exc))
import configurator.app as app_module
app_module.ConfiguratorApp=TestApp
sys.exit(entry.main())
''')
                master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,__import__('struct').pack('HHHH',40,110,0,0));before=termios.tcgetattr(slave)
                env={**os.environ,'TERM':'xterm-256color','HOME':str(root),'PYTHONPATH':str(Path(module).parent.parent),'PYTHONDONTWRITEBYTECODE':'1'}
                process=subprocess.Popen([sys.executable,'-B',str(driver),'--root',str(root),'--renderer',str(renderer)],stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True)
                output=b''
                try:
                    deadline=time.monotonic()+12
                    while not (root/'ready').exists() and not (root/'arm-error').exists() and process.poll() is None and time.monotonic()<deadline:
                        if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                    self.assertTrue((root/'ready').exists(),(root/'arm-error').read_text() if (root/'arm-error').exists() else {'files':[str(p.relative_to(root)) for p in root.rglob('*')],'tail':output[-1000:]});owned_pid=int((root/'ready').read_text())
                    if trigger is None:os.write(master,b'\x03\x03')
                    else:os.kill(process.pid,trigger)
                    deadline=time.monotonic()+8
                    while process.poll() is None and time.monotonic()<deadline:
                        if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
                    self.assertEqual(process.wait(timeout=2),expected,output[-1500:])
                    while select.select([master],[],[],0)[0]:
                        chunk=os.read(master,65536)
                        if not chunk:break
                        output+=chunk
                    if trigger is None:self.assertEqual((root/'escalated').read_text(),'owned group only')
                    self.assertIn(b'\x1b[?1049h',output);self.assertIn(b'\x1b[?1049l',output);self.assertEqual(termios.tcgetattr(slave),before)
                    with self.assertRaises(ProcessLookupError):os.kill(owned_pid,0)
                    self.assertIsNone(control.poll());self.assertEqual(original.read_bytes(),b'personal source must not be inspected or replaced\n')
                    store=__import__('configurator.recovery',fromlist=['RecoveryStore']).RecoveryStore(root)
                    rows=store.entries();self.assertEqual(len(rows),1);self.assertFalse(rows[0]['active'])
                    self.assertEqual(store.load(rows[0]['id']).record['current']['latitude'],'25')
                    self.assertFalse((root/'config/desktop.scene').exists())
                finally:
                    if process.poll() is None:process.kill();process.wait()
                    os.close(master);os.close(slave)
        finally:control.terminate();control.wait()


    async def test_recorded_renderer_requires_explicit_optin_and_never_executes_on_recover(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#renderer',Input).value='/missing/recorded-renderer';await pilot.pause()
            await self.app.recovery.flush();await pilot.press('ctrl+c')
        for optin in (False,True):
            app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),recovery=True)
            try:
                async with app.run_test(size=(110,50)) as pilot:
                    await click(pilot,'#recovery');await click(pilot,'#recovery-inspect')
                    app.screen.query_one('#recovery-renderer',Checkbox).value=optin
                    await click(pilot,'#recovery-recover');await pilot.pause()
                    expected='/missing/recorded-renderer' if optin else str(Path(sys.executable).resolve())
                    self.assertEqual(app.query_one('#renderer',Input).value,expected);self.assertIsNone(app.workspace.process)
                    await pilot.press('ctrl+c')
            finally:app.workspace.close()
