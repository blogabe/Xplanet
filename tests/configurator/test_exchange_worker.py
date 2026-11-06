"""Owned exchange workers never activate, overwrite or outlive cancellation."""
import asyncio,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from configurator.workspace import Workspace,save_view,open_view
from configurator.model import View


class ExchangeWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.workspace=Workspace();self.addCleanup(self.workspace.close)
        self.source=save_view(self.root/'saved',View(latitude=10),sys.executable)

    async def test_real_worker_roundtrip_keeps_saved_source_and_does_not_execute_renderer(self):
        before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.source.iterdir()}
        package=await self.workspace.exchange_scene('export',self.source,self.root/'package')
        renderer=self.root/'not executed';marker=self.root/'must-not-exist'
        renderer.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\n');renderer.chmod(0o700)
        target=await self.workspace.exchange_scene('import',package/'scene.xplanet.zip',self.root/'imported',renderer=renderer)
        self.assertEqual(open_view(target).view.latitude,10);self.assertFalse(marker.exists())
        self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.source.iterdir()})
        self.assertFalse(self.workspace.busy);self.assertIsNone(self.workspace.process);self.assertFalse((self.root/'config/desktop.scene').exists())

    async def test_refused_import_existing_destination_and_temporary_target_keep_prior_preview(self):
        prior=object();self.workspace.latest=prior
        bad=self.root/'bad.zip';bad.write_bytes(b'not archive')
        with self.assertRaisesRegex(ValueError,'did not complete'):await self.workspace.exchange_scene('import',bad,self.root/'new',renderer=sys.executable)
        self.assertFalse((self.root/'new').exists());self.assertIs(self.workspace.latest,prior)
        with self.assertRaises(ValueError):await self.workspace.exchange_scene('export',self.source,self.source)
        with self.assertRaisesRegex(ValueError,'temporary preview'):await self.workspace.exchange_scene('export',self.source,self.workspace.root/'not-durable')
        self.assertFalse((self.workspace.root/'not-durable').exists())

    def slow_worker(self):
        path=self.root/'slow exchange';marker=self.root/'worker.pid';later=self.root/'late-write'
        path.write_text('#!'+sys.executable+'\nimport os,time\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text(str(os.getpid()))\ntime.sleep(30)\nPath('+repr(str(later))+').write_text("late")\n');path.chmod(0o700)
        return path,marker,later

    async def test_timeout_reaps_owned_worker_and_reports_destination_uncertainty(self):
        binary,marker,later=self.slow_worker()
        with patch('configurator.workspace.sys.executable',str(binary)),self.assertRaisesRegex(ValueError,'partial or complete'):
            await self.workspace.exchange_scene('export',self.source,self.root/'timed',timeout=.3)
        pid=int(marker.read_text())
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)
        self.assertFalse(later.exists());self.assertFalse(self.workspace.busy);self.assertIsNone(self.workspace.process)

    async def test_cancel_reaps_owned_worker_and_never_discards_prior_preview(self):
        binary,marker,later=self.slow_worker();prior=object();self.workspace.latest=prior
        with patch('configurator.workspace.sys.executable',str(binary)):
            task=asyncio.create_task(self.workspace.exchange_scene('export',self.source,self.root/'cancelled'))
            async def started():
                while not marker.exists():await asyncio.sleep(.01)
            await asyncio.wait_for(started(),3);pid=int(marker.read_text());task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)
        self.assertFalse(later.exists());self.assertIs(self.workspace.latest,prior);self.assertFalse(self.workspace.busy)

    async def test_missing_or_invalid_inputs_fail_without_background_work(self):
        for mode,source,destination,options in (('unknown',self.source,self.root/'new',{}),('export',Path('relative'),self.root/'new',{}),('import',self.root/'none',self.root/'new',{'renderer':''}),('import',self.root/'none',self.root/'new',{'renderer':sys.executable,'preview':self.root/'x.png'})):
            with self.subTest(mode=mode),self.assertRaises(ValueError):await self.workspace.exchange_scene(mode,source,destination,**options)
        self.assertFalse((self.root/'new').exists());self.assertIsNone(self.workspace.process)
        self.workspace.busy=True
        try:
            with self.assertRaisesRegex(ValueError,'current operation'):await self.workspace.exchange_scene('export',self.source,self.root/'busy')
        finally:self.workspace.busy=False

    async def test_unresolvable_source_destination_preview_and_renderer_are_friendly(self):
        loop=self.root/'loop';loop.symlink_to(loop)
        missing='~xplanet-no-such-user-91bc/path'
        cases=(('export',loop,self.root/'new',{}),
               ('export',self.source,loop/'new',{}),
               ('export',self.source,self.root/'new',{'preview':loop}),
               ('import',self.source,self.root/'new',{'renderer':loop}),
               ('export',missing,self.root/'new',{}),
               ('export',self.source,loop,{}),
               ('export',self.source,self.root/'new',{'preview':missing}),
               ('import',self.source,self.root/'new',{'renderer':missing}))
        from unittest.mock import AsyncMock
        with patch.object(self.workspace,'_run_child',new_callable=AsyncMock) as child:
            for mode,source,target,options in cases:
                with self.subTest(mode=mode,options=options),self.assertRaisesRegex(ValueError,'cannot be resolved safely'):
                    await self.workspace.exchange_scene(mode,source,target,**options)
            self.assertEqual(child.call_count,0)
        self.assertFalse(self.workspace.busy);self.assertFalse((self.root/'new').exists())

    async def test_permissive_nonstrict_loop_resolution_cannot_start_worker(self):
        from unittest.mock import AsyncMock
        loop=self.root/'loop';loop.symlink_to(loop);original=Path.resolve
        def resolve(path,strict=False):
            if path==loop and not strict:return path  # Python 3.13+ behavior.
            return original(path,strict=strict)
        with patch.object(Path,'resolve',autospec=True,side_effect=resolve),patch.object(self.workspace,'_run_child',new_callable=AsyncMock) as child:
            with self.assertRaisesRegex(ValueError,'cannot be resolved safely'):
                await self.workspace.exchange_scene('export',self.source,loop)
            self.assertEqual(child.call_count,0)
        self.assertFalse(self.workspace.busy);self.assertIsNone(self.workspace.process)

    async def test_existing_renderer_still_requires_explicit_absolute_path(self):
        from unittest.mock import AsyncMock
        relative=os.path.relpath(sys.executable)
        with patch.object(self.workspace,'_run_child',new_callable=AsyncMock) as child:
            with self.assertRaisesRegex(ValueError,'absolute path'):
                await self.workspace.exchange_scene('import',self.source,self.root/'new',renderer=relative)
            self.assertEqual(child.call_count,0)
        self.assertFalse(self.workspace.busy)

    async def test_new_destination_inside_existing_custom_parent_keeps_spaces(self):
        parent=self.root/'custom parent';parent.mkdir();target=parent/'new archive copy'
        result=await self.workspace.exchange_scene('export',self.source,target)
        self.assertEqual(result,target);self.assertTrue((target/'scene.xplanet.zip').is_file())
        self.assertFalse(self.workspace.busy);self.assertIsNone(self.workspace.process)


class ExchangeExitReportTests(unittest.TestCase):
    def test_last_exchange_notice_is_printed_after_cancel_without_changing_exitcode(self):
        from configurator import __main__ as entry
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        class FakeApp:
            recovery_notice='';exchange_notice='Inspect chosen destination: partial or complete copy may exist.'
            recovery=None;termination_signal=None
            def __init__(self,*args,**kwargs):pass
            async def run_async(self):return ('cancelled',None)
        output=StringIO()
        with tempfile.TemporaryDirectory() as root,patch.dict(sys.modules,{'configurator.app':SimpleNamespace(ConfiguratorApp=FakeApp)}),patch.object(sys,'argv',['configurator','--root',root]),patch('sys.stdin.isatty',return_value=True),redirect_stdout(output),patch.object(output,'isatty',return_value=True):
            code=entry.main()
        self.assertEqual(code,3);self.assertIn('Configurator cancelled',output.getvalue());self.assertIn(FakeApp.exchange_notice,output.getvalue())

    def test_last_exchange_notice_survives_exceptional_app_exit(self):
        from configurator import __main__ as entry
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        class FakeApp:
            recovery_notice='';exchange_notice='Inspect pending destination after fatal interruption.'
            recovery=None;termination_signal=None
            def __init__(self,*args,**kwargs):pass
            async def run_async(self):raise RuntimeError('fixture fatal')
        output=StringIO()
        with tempfile.TemporaryDirectory() as root,patch.dict(sys.modules,{'configurator.app':SimpleNamespace(ConfiguratorApp=FakeApp)}),patch.object(sys,'argv',['configurator','--root',root]),patch('sys.stdin.isatty',return_value=True),redirect_stdout(output),patch.object(output,'isatty',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'fixture fatal'):entry.main()
        self.assertIn(FakeApp.exchange_notice,output.getvalue())
