"""Exchange saved files explicitly; importing never silently replaces a draft."""
import asyncio,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from textual.widgets import Input,Static
from configurator.app import ConfiguratorApp
from configurator.model import View
from configurator.workspace import Workspace,save_view,open_view
from configurator.exchange import export_scene


async def click(pilot,selector):
    pilot.app.screen.query_one(selector).scroll_visible(animate=False);await pilot.pause();await pilot.click(selector);await pilot.pause()


class ExchangeUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
        self.source=save_view(self.root/'saved',View(latitude=10),sys.executable)
        self.workspace=Workspace();self.addCleanup(self.workspace.close)
        self.app=ConfiguratorApp(self.root,sys.executable,self.workspace,document=open_view(self.source),recovery=False)
    async def dirty(self,pilot):
        self.app.query_one('#latitude',Input).value='44';await pilot.pause();self.app.capture_edit();self.assertTrue(self.app.history.dirty)
    def paths(self,source,destination):
        self.app.screen.query_one('#exchange-source',Input).value=str(source)
        self.app.screen.query_one('#exchange-destination',Input).value=str(destination)
    async def finish(self,pilot):await self.app.workers.wait_for_complete();await pilot.pause()

    async def test_open_back_and_blank_confirmation_never_start_filesystem_worker(self):
        async with self.app.run_test(size=(120,55)) as pilot:
            with patch.object(self.workspace,'exchange_scene',new_callable=AsyncMock) as exchange:
                await click(pilot,'#exchange-export');await click(pilot,'#exchange-confirm')
                self.assertIn('Nothing has been written',str(self.app.screen.query_one('#exchange-message',Static).render()))
                await click(pilot,'#exchange-back');await click(pilot,'#exchange-import');await pilot.press('escape');exchange.assert_not_called()
            self.assertFalse((self.root/'config/desktop.scene').exists());await pilot.press('ctrl+c')

    async def test_export_uses_saved_source_not_dirty_editor_or_current_preview(self):
        async with self.app.run_test(size=(120,55)) as pilot:
            await self.dirty(pilot);await click(pilot,'#exchange-export')
            self.assertEqual(self.app.screen.query_one('#exchange-source',Input).value,str(self.source))
            self.assertEqual(self.app.screen.query_one('#exchange-preview',Input).value,'')
            self.paths(self.source,self.root/'package');await click(pilot,'#exchange-confirm');await self.finish(pilot)
            target=await self.workspace.exchange_scene('import',self.root/'package/scene.xplanet.zip',self.root/'check',renderer=sys.executable)
            self.assertEqual(open_view(target).view.latitude,10);self.assertEqual(self.app.draft().latitude,44);self.assertTrue(self.app.history.dirty)
            self.assertEqual(self.app.document.source,self.source);await pilot.press('ctrl+c')

    async def test_import_back_preserves_dirty_draft_and_created_copy(self):
        package=export_scene(self.source,self.root/'package')/'scene.xplanet.zip'
        async with self.app.run_test(size=(120,55)) as pilot:
            await self.dirty(pilot);before=self.app.history.current
            await click(pilot,'#exchange-import');self.paths(package,self.root/'imported');await click(pilot,'#exchange-confirm');await self.finish(pilot)
            self.assertIn('replace draft',str(self.app.screen.query_one('#confirm-open').label))
            self.assertEqual(self.app.draft().latitude,44);await click(pilot,'#back-open')
            self.assertEqual(self.app.history.current,before);self.assertEqual(open_view(self.root/'imported').view.latitude,10)
            self.assertFalse((self.root/'config/desktop.scene').exists());await pilot.press('ctrl+c')

    async def test_open_import_requires_explicit_confirm_and_keeps_local_renderer(self):
        package=export_scene(self.source,self.root/'package')/'scene.xplanet.zip'
        async with self.app.run_test(size=(120,55)) as pilot:
            await self.dirty(pilot);renderer=self.app.query_one('#renderer',Input).value
            await click(pilot,'#exchange-import');self.paths(package,self.root/'imported');await click(pilot,'#exchange-confirm');await self.finish(pilot)
            self.assertEqual(self.app.draft().latitude,44);await click(pilot,'#confirm-open');await pilot.pause()
            self.assertEqual(self.app.draft().latitude,10);self.assertFalse(self.app.history.dirty);self.assertEqual(self.app.query_one('#renderer',Input).value,renderer)
            self.assertEqual(self.app.document.source,self.root/'imported');await pilot.press('ctrl+c')

    async def test_bad_archive_preserves_draft_without_open_offer(self):
        bad=self.root/'bad.zip';bad.write_bytes(b'not archive')
        async with self.app.run_test(size=(120,55)) as pilot:
            await self.dirty(pilot);await click(pilot,'#exchange-import');self.paths(bad,self.root/'new');await click(pilot,'#exchange-confirm');await self.finish(pilot)
            self.assertIn('Cannot exchange',str(self.app.query_one('#status',Static).render()));self.assertEqual(self.app.draft().latitude,44)
            self.assertFalse((self.root/'new').exists());self.assertEqual(self.app.document.source,self.source);await pilot.press('ctrl+c')

    async def test_ctrl_c_stops_exchange_writer_and_reports_uncertain_destination(self):
        marker=self.root/'exchange.pid';binary=self.root/'slow exchange'
        binary.write_text('#!'+sys.executable+'\nimport os,time\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text(str(os.getpid()))\ntime.sleep(30)\n');binary.chmod(0o700)
        async with self.app.run_test(size=(120,55)) as pilot:
            with patch('configurator.workspace.sys.executable',str(binary)):
                await click(pilot,'#exchange-export');self.paths(self.source,self.root/'pending');await click(pilot,'#exchange-confirm')
                async def started():
                    while not marker.exists():await asyncio.sleep(.01)
                await asyncio.wait_for(started(),3);pid=int(marker.read_text());await pilot.press('ctrl+c');await self.finish(pilot)
            self.assertFalse(self.app.leaving);self.assertFalse(self.workspace.busy);self.assertIsNone(self.workspace.process)
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            self.assertIn('Inspect',str(self.app.query_one('#status',Static).render()));self.assertIn(str(self.root/'pending'),str(self.app.query_one('#status',Static).render()))
            await pilot.press('ctrl+c')

    async def test_unresolvable_destination_is_friendly_and_dirty_editor_remains_usable(self):
        loop=self.root/'loop';loop.symlink_to(loop)
        async with self.app.run_test(size=(120,55)) as pilot:
            await self.dirty(pilot);await click(pilot,'#exchange-export');self.paths(self.source,loop);await click(pilot,'#exchange-confirm');await self.finish(pilot)
            self.assertEqual(self.app.draft().latitude,44);self.assertTrue(self.app.history.dirty)
            self.assertIn('cannot be resolved safely',str(self.app.query_one('#status',Static).render()));self.assertFalse(self.app.query_one('#exchange-export').disabled)
            self.assertFalse(self.workspace.busy);await pilot.press('ctrl+c')

    async def test_emergency_exit_retains_partial_copy_and_persistent_inspection_notice(self):
        marker=self.root/'emergency.pid';target=self.root/'partial-output';binary=self.root/'stubborn exchange'
        binary.write_text('#!'+sys.executable+'\nimport os,time,signal\nfrom pathlib import Path\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nfolder=Path('+repr(str(target))+');folder.mkdir();(folder/"partial").write_text("preserve fixture")\nPath('+repr(str(marker))+').write_text(str(os.getpid()))\ntime.sleep(60)\n');binary.chmod(0o700)
        async with self.app.run_test(size=(120,55)) as pilot:
            with patch('configurator.workspace.sys.executable',str(binary)):
                await click(pilot,'#exchange-export');self.paths(self.source,target);await click(pilot,'#exchange-confirm')
                async def started():
                    while not marker.exists():await asyncio.sleep(.01)
                await asyncio.wait_for(started(),3);pid=int(marker.read_text());await pilot.press('ctrl+c');await pilot.press('ctrl+c')
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)
        self.assertIn('Inspect',self.app.exchange_notice);self.assertIn(str(target),self.app.exchange_notice)
        self.assertEqual((target/'partial').read_text(),'preserve fixture');self.assertFalse(self.workspace.busy)
        self.assertEqual(self.app.return_value,('cancelled',None))
