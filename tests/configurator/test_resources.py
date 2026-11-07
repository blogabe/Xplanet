"""Binary evidence is explicit, bounded, scoped and never guessed from failure."""
import asyncio,io,os,sys,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from configurator.model import View,parse_saved_view
from configurator.resources import BoundedLog,capabilities,identity,capability_issues,resource_evidence
from configurator.workspace import Workspace,configuration_issues
from configurator.geometry import geometry


class GeometryTests(unittest.TestCase):
    def test_default_custom_bounds_and_preview_identity(self):
        view=View();self.assertEqual(view.geometry,'1920x1080')
        for value in ('2160x1080','3840x2160','5120x2880','1080x1080','800x600'):
            changed=replace(view,geometry=value);changed.validate()
            self.assertEqual(changed.arguments()[-1],value)
            self.assertEqual(parse_saved_view(changed.definition('/renderer').encode(),changed.body()).view,changed)
            if value!=view.geometry:self.assertNotEqual(changed.render_digest(),view.render_digest())
        for value in ('0x1080','01920x1080','1920x1080+0+0','16384x16384','999999x2','$(echo x)',None):
            with self.subTest(value=value),self.assertRaises(ValueError):geometry(value)

    def test_v13_is_preserved_and_unknown_geometry_edits_are_refused(self):
        old=View(geometry='800x600');raw=old.definition('/renderer',version=13).encode()
        self.assertEqual(parse_saved_view(raw,old.body()).view,old)
        with self.assertRaises(ValueError):parse_saved_view(raw.replace(b'800x600',b'1920x1080'),old.body())
        with self.assertRaises(ValueError):View().definition('/renderer',version=13)
        current=View();definition=current.definition('/renderer').encode();self.assertIn(b'scene v17',definition)
        self.assertEqual(parse_saved_view(definition,current.body()).view,current)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.binary=self.root/'renderer';self.binary.write_bytes(b'fixture');self.stamp=identity(self.binary)

    def report(self,raw,code=0):return capabilities(self.binary,self.stamp,io.BytesIO(raw),code)

    def test_supported_missing_unknown_and_failed_are_distinct(self):
        good=self.report(b'Xplanet 1.3.1\nCompiled with support for:\n\tPNG\n\tJPEG\n\tCSPICE_N0067\n')
        self.assertEqual(good.status,'reported');self.assertFalse(any(i.severity=='blocking' for i in capability_issues(good,View(),self.binary)))
        missing=self.report(b'Xplanet 1.3.1\nCompiled with support for:\n\tJPEG\n')
        self.assertTrue(any(i.severity=='blocking' and 'PNG' in i.message for i in capability_issues(missing,View(),self.binary)))
        for raw,code in ((b'unknown output',0),(b'Xplanet 1.3.1\nCompiled with support for:\n\tJPEG\n',1),(b'Xplanet 1.3.1\nCompiled with support for:\n PNG\n',0),(b'Xplanet 1.3.1\nCompiled with support for:\n\t\x1b[31mPNG\n',0)):
            report=self.report(raw,code);self.assertNotEqual(report.status,'reported');self.assertEqual(report.exit_code,code)
            self.assertFalse(any(i.severity=='blocking' for i in capability_issues(report,View(),self.binary)))
        self.assertIn('CSPICE_N0067',good.features)

    def test_changed_binary_invalidates_evidence_without_claiming_missing_features(self):
        report=self.report(b'Xplanet 1.3.1\nCompiled with support for:\n\tJPEG\n')
        self.binary.write_bytes(b'new binary');issues=capability_issues(report,View(),self.binary)
        self.assertFalse(any(i.severity=='blocking' for i in issues));self.assertIn('stale',issues[0].message)

    def test_large_logs_are_drained_and_truncation_cannot_fabricate_full_support(self):
        log=BoundedLog();log.feed(b'Xplanet 1.3.1\nCompiled with support for:\n\tJPEG\n')
        for _ in range(200):log.feed(b'x'*65536+b'\n')
        report=capabilities(self.binary,self.stamp,log,0)
        self.assertLessEqual(len(log.head)+len(log.tail),32768);self.assertGreater(report.log_bytes,10_000_000)
        self.assertNotEqual(report.status,'reported');self.assertFalse(any(i.severity=='blocking' for i in capability_issues(report,View(),self.binary)))

    def test_lookup_misses_are_attempts_not_failed_sources_and_controls_are_escaped(self):
        log=io.BytesIO(b'Looking for earth.jpg ... not found\nLooking for /safe/earth.jpg ... found\nWarning: something\n\x1b[31mnot trusted\n')
        evidence=resource_evidence(self.binary,View(),log,self.root/'missing','succeeded',0)
        self.assertEqual(evidence.lookups,(('earth.jpg',False),('/safe/earth.jpg',True)))
        text='\n'.join(evidence.sections());self.assertIn('normal',text);self.assertNotIn('\x1b',text)
        self.assertFalse(evidence.png_signature);self.assertIsNone(evidence.dimensions)


class DiagnosticProcessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.workspace=Workspace();self.addCleanup(self.workspace.close);self.trace=self.root/'trace'

    def renderer(self,version='PNG\\n\\tJPEG',version_code=0,render_extra=''):
        path=self.root/'renderer';path.write_text('#!'+sys.executable+'\nimport sys,pathlib,struct,time\na=sys.argv\n'+
            f'trace=pathlib.Path({str(self.trace)!r})\n'+
            'with trace.open("a") as f:f.write("version\\n" if "-version" in a else "render\\n")\n'+
            'if "-version" in a:\n'+f' print("Xplanet 1.3.1\\nCompiled with support for:\\n\\t{version}");sys.exit({version_code})\n'+
            render_extra+'\n'+
            'w,h=map(int,a[a.index("-geometry")+1].split("x"))\n'+
            'pathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\n"+b"\\0\\0\\0\\rIHDR"+struct.pack(">II",w,h))\n'+
            'print("Looking for earth.jpg ... not found\\nLooking for /fixture/earth.jpg ... found")\n')
        path.chmod(0o700);return path

    async def test_explicit_diagnostic_uses_same_binary_and_retains_attempt_evidence(self):
        binary=self.renderer();image=await self.workspace.preview(View(),binary,diagnostic=True)
        self.assertTrue(image.is_file());self.assertEqual(self.trace.read_text().splitlines(),['version','render'])
        self.assertEqual(self.workspace.capabilities.status,'reported');evidence=self.workspace.last_resources
        self.assertEqual(evidence.dimensions,(1920,1080));self.assertTrue(evidence.png_signature)
        self.assertIn(('/fixture/earth.jpg',True),evidence.lookups);self.assertIsNone(self.workspace.process)
        original=image;await self.workspace.preview(View(geometry='2160x1080'),binary)
        self.assertFalse(self.workspace.latest.matches(View(),binary,View().body()));self.assertTrue(original.exists())

    async def test_missing_reported_png_blocks_render_but_unknown_probe_does_not(self):
        binary=self.renderer('JPEG')
        with self.assertRaisesRegex(ValueError,'PNG'):await self.workspace.preview(View(),binary,diagnostic=True)
        self.assertEqual(self.trace.read_text().splitlines(),['version']);self.assertFalse(self.workspace.busy)
        self.trace.unlink();binary=self.renderer('JPEG',1)
        await self.workspace.preview(View(),binary,diagnostic=True)
        self.assertNotEqual(self.workspace.capabilities.status,'reported');self.assertEqual(self.trace.read_text().splitlines(),['version','render'])

    async def test_large_child_output_is_bounded_and_wrong_dimensions_keep_prior_preview(self):
        binary=self.renderer();old=await self.workspace.preview(View(),binary)
        binary=self.renderer(render_extra='sys.stdout.write("x"*1000000+"\\n");sys.stdout.flush()')
        await self.workspace.preview(View(),binary,diagnostic=True)
        self.assertTrue(self.workspace.last_resources.truncated)
        self.assertGreater(self.workspace.last_resources.log_bytes,1000000)
        self.assertLess(len(self.workspace.last_resources.raw),33000)
        previous=self.workspace.image
        binary=self.renderer(render_extra='a[a.index("-geometry")+1]="200x200"')
        with self.assertRaisesRegex(ValueError,'dimensions'):await self.workspace.preview(View(),binary,diagnostic=True)
        self.assertEqual(self.workspace.image,previous);self.assertTrue(old.exists())
        self.assertIsNone(self.workspace.process)

    async def test_same_path_binary_replacement_marks_old_preview_stale(self):
        binary=self.renderer();view=View();old=await self.workspace.preview(view,binary)
        self.assertTrue(self.workspace.latest.matches(view,binary,view.body()))
        binary.write_bytes(binary.read_bytes()+b'\n# replacement build\n')
        self.assertFalse(self.workspace.latest.matches(view,binary,view.body()));self.assertEqual(self.workspace.image,old);self.assertTrue(old.exists())

    async def test_diagnostic_metadata_only_updates_keep_verified_support_current(self):
        binary=self.renderer();raw=binary.read_text();binary.write_text(raw.replace('a=sys.argv\n','a=sys.argv\npathlib.Path(__file__).chmod(0o700)\n'))
        view=View();await self.workspace.preview(view,binary,diagnostic=True)
        self.assertEqual(self.workspace.capabilities.status,'reported');self.assertTrue(self.workspace.capabilities.matches(binary))
        self.assertTrue(self.workspace.latest.matches(view,binary,view.body()))

    async def test_metadata_only_change_is_verified_without_false_render_failure(self):
        binary=self.renderer(render_extra='pathlib.Path(__file__).chmod(0o700)');view=View()
        output=await self.workspace.preview(view,binary)
        self.assertTrue(output.exists());self.assertTrue(self.workspace.latest.matches(view,binary,view.body()))

    async def test_same_size_byte_change_with_restored_mtime_is_still_refused(self):
        binary=self.renderer();old=await self.workspace.preview(View(),binary)
        extra='p=pathlib.Path(__file__);st=p.stat();p.write_bytes(p.read_bytes().replace(b"# buildA",b"# buildB"));import os;os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))\n# buildA'
        binary=self.renderer(render_extra=extra)
        with self.assertRaisesRegex(ValueError,'Renderer changed during preview'):await self.workspace.preview(View(),binary)
        self.assertEqual(self.workspace.image,old)

    async def test_binary_changed_during_render_is_not_promoted(self):
        binary=self.renderer();old=await self.workspace.preview(View(),binary)
        binary=self.renderer(render_extra='pathlib.Path(__file__).write_bytes(pathlib.Path(__file__).read_bytes()+b"\\n# changed while rendering\\n")')
        with self.assertRaisesRegex(ValueError,'Renderer changed during preview'):await self.workspace.preview(View(),binary)
        self.assertEqual(self.workspace.image,old);self.assertTrue(old.exists());self.assertIsNone(self.workspace.process)

    async def test_failure_timeout_and_cancel_keep_previous_success_and_release_owned_process(self):
        binary=self.renderer();old=await self.workspace.preview(View(),binary)
        binary=self.renderer(render_extra='print("failure");sys.exit(7)')
        with self.assertRaises(ValueError):await self.workspace.preview(View(),binary,diagnostic=True)
        self.assertEqual(self.workspace.image,old);self.assertEqual(self.workspace.last_resources.outcome,'failed')
        binary=self.renderer(render_extra='time.sleep(30)')
        with self.assertRaisesRegex(ValueError,'exceeded'):await self.workspace.preview(View(),binary,timeout=.15,diagnostic=True)
        self.assertIsNone(self.workspace.process);self.assertEqual(self.workspace.image,old)
        task=asyncio.create_task(self.workspace.preview(View(),binary,diagnostic=True))
        while self.workspace.process is None:await asyncio.sleep(.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNone(self.workspace.process);self.assertFalse(self.workspace.busy);self.assertEqual(self.workspace.image,old)


class StockGeometryTests(unittest.TestCase):
    def test_stock_pairs_are_current_native_readonly_inputs_with_explicit_frames(self):
        from configurator.model import ROOT
        from configurator.workspace import open_view
        library=ROOT/'scripts/configurator/samples/scenes'
        paths=sorted(library.glob('*.conf'));self.assertEqual(len(paths),24)
        for path in paths:
            before=(path.read_bytes(),path.with_suffix('.def').read_bytes())
            document=open_view(path);self.assertEqual(document.view.geometry,'1920x1080',path.name)
            self.assertEqual(document.config,before[0],path.name)
            self.assertEqual(before,(path.read_bytes(),path.with_suffix('.def').read_bytes()))
        for name,target,origin in (('mars-from-deimos','mars','deimos'),('jupiter-from-io','jupiter','io'),('jupiter-from-europa','jupiter','europa'),('saturn-from-iapetus','saturn','iapetus'),('uranus-from-miranda','uranus','miranda')):
            view=open_view(library/(name+'.conf')).view
            self.assertEqual((view.target,view.observer,view.projection),(target,origin,'space'))
            self.assertEqual(view.time_mode,'fixed')
