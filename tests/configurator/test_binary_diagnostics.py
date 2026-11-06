"""Explicit support inspection uses disposable executables and private state only."""
import asyncio,contextlib,io,json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from configurator import binary_diagnostics as diagnostic
from configurator.model import ROOT
from configurator.resources import safe
from tests.support import copy_launcher

REPORT='Xplanet 1.3.1\nCompiled with support for:\n\tPNG\n\tJPEG\n'
class BinaryDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.binary=self.root/'renderer with spaces'
        self.write('print('+repr(REPORT)+',end="")')
    def write(self,body):
        self.binary.write_text('#!'+sys.executable+'\n'+body+'\n');self.binary.chmod(0o700)
    async def test_success_keeps_raw_identity_and_cache_roundtrip_without_more_execution(self):
        report=await diagnostic.probe(self.binary)
        self.assertEqual(report.status,'reported');self.assertEqual(report.raw,REPORT)
        diagnostic.store(self.root,report);before=(self.root/diagnostic.CACHE).read_bytes()
        with patch('configurator.binary_diagnostics.probe',side_effect=AssertionError('no repeat probe')):
            loaded=diagnostic.load(self.root)
        self.assertEqual(loaded,report);self.assertTrue(loaded.matches(self.binary));self.assertEqual((self.root/diagnostic.CACHE).read_bytes(),before)
        self.assertEqual((self.root/diagnostic.CACHE).stat().st_mode&0o777,0o600)
    async def test_replacement_is_stale_and_show_never_executes_new_binary(self):
        report=await diagnostic.probe(self.binary);diagnostic.store(self.root,report)
        self.write('raise RuntimeError("must not run on show")')
        with patch('sys.argv',['diagnostic','--root',str(self.root),'--renderer',str(self.binary),'--show']),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(diagnostic.main(),1)
        self.assertIn('STALE',output.getvalue());self.assertIn('does not identify a running process',output.getvalue())
    async def test_failed_odd_invalid_bytes_and_flood_are_unknown_not_unsupported(self):
        for body in ('print("unfamiliar version")','print('+repr(REPORT)+',end="");raise SystemExit(7)','import os;os.write(1,b"\\xff\\x1b[31m odd")','print("x"*200000)'):
            self.write(body);report=await diagnostic.probe(self.binary)
            self.assertNotEqual(report.status,'reported');self.assertEqual(report.features,())
            self.assertLess(len(report.raw),34000);self.assertNotIn('\x1b',safe(report.raw))
            diagnostic.store(self.root,report);self.assertEqual(diagnostic.load(self.root).status,report.status)
    async def test_timeout_reaps_owned_group_and_removes_private_workspace(self):
        record=self.root/'private-location'
        self.write('import pathlib,os,time;pathlib.Path('+repr(str(record))+').write_text(os.getcwd());time.sleep(30)')
        start=time.monotonic();report=await diagnostic.probe(self.binary,timeout=.3)
        self.assertLess(time.monotonic()-start,5);self.assertIn('unknown',report.status)
        self.assertFalse(Path(record.read_text()).exists())
    async def test_binary_change_during_probe_invalidates_recognized_report(self):
        self.write('import pathlib;print('+repr(REPORT)+',end="");p=pathlib.Path(__file__);p.write_text(p.read_text()+"#replacement")')
        report=await diagnostic.probe(self.binary);self.assertIn('changed',report.status)
    async def test_private_home_and_finite_arguments_no_network_or_desktop_requested(self):
        record=self.root/'arguments.json'
        self.write('import json,os,sys,pathlib;pathlib.Path('+repr(str(record))+').write_text(json.dumps([sys.argv,os.environ["HOME"],os.getcwd()]));print('+repr(REPORT)+',end="")')
        report=await diagnostic.probe(self.binary);self.assertEqual(report.status,'reported')
        args,home,cwd=json.loads(record.read_text());self.assertEqual(Path(home).resolve(),Path(cwd).resolve())
        self.assertIn('-version',args);self.assertIn('-output',args);self.assertIn('-num_times',args);self.assertNotIn('-fork',args)
        self.assertFalse(Path(home).exists());self.assertFalse((self.root/'config').exists())
    async def test_cache_corruption_links_and_oversize_refused_without_replacing_targets(self):
        report=await diagnostic.probe(self.binary);diagnostic.store(self.root,report);path=self.root/diagnostic.CACHE
        path.write_text('{');self.assertIsNone(diagnostic.cached(self.root))
        path.write_bytes(b'x'*(diagnostic.LIMIT+1));self.assertIsNone(diagnostic.cached(self.root))
        path.unlink();target=self.root/'keep';target.write_bytes(b'original');path.symlink_to(target)
        self.assertIsNone(diagnostic.cached(self.root))
        with self.assertRaises(ValueError):diagnostic.store(self.root,report)
        self.assertEqual(target.read_bytes(),b'original')
    async def test_atomic_concurrent_cache_writes_remain_complete(self):
        import concurrent.futures
        report=await diagnostic.probe(self.binary);diagnostic.store(self.root,report)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda _:diagnostic.store(self.root,report),range(12)))
        self.assertEqual(diagnostic.load(self.root),report)
        self.assertFalse(list((self.root/diagnostic.CACHE).parent.glob('.binary-evidence-*')))
    @unittest.skipUnless(shutil.which("zsh"),"zsh shell routing; core probe/cache tests remain portable")
    async def test_shell_explicit_renderer_and_missing_configuration_are_isolated(self):
        scripts=self.root/'scripts';scripts.mkdir();entry=scripts/'xplanet.sh';copy_launcher(entry)
        # Real stdlib module with disposable shell root; never installed files.
        (scripts/'configurator').symlink_to(ROOT/'scripts/configurator',target_is_directory=True)
        (scripts/'totalmarker').symlink_to(ROOT/'scripts/totalmarker',target_is_directory=True)
        runner=scripts/'run-totalmarker';runner.write_text('#!/bin/sh\nprintf "%s\\n" '+repr(sys.executable)+'\n');runner.chmod(0o700)
        result=subprocess.run([str(entry),'diagnostics','--renderer',str(self.binary)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('Compiled with support',result.stdout)
        self.assertTrue((self.root/diagnostic.CACHE).exists());self.assertFalse((self.root/'config').exists())
        self.assertIn('Recorded file identity',result.stdout)
        self.write('raise RuntimeError("show must not execute")')
        result=subprocess.run([str(entry),'diagnostics','--show','--renderer',str(self.binary)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1,result.stderr);self.assertIn('STALE',result.stdout)

    @unittest.skipUnless(shutil.which("zsh"),"zsh desktop selection; core probe/cache tests remain portable")
    async def test_selected_resolution_is_authoritative_and_invalid_selector_has_no_path_fallback(self):
        scripts=self.root/'scripts';scripts.mkdir();entry=scripts/'xplanet.sh';copy_launcher(entry)
        (self.root/'config').mkdir();(self.root/'config/desktop.scene').write_text('invalid selector\n')
        # A valid fallback executable must never be tried for an invalid selection.
        result=subprocess.run([str(entry),'diagnostics'],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,2);self.assertIn('no custom configuration fallback',result.stderr)
        self.assertFalse((self.root/diagnostic.CACHE).exists())

    @unittest.skipUnless(shutil.which('zsh'),'dependency-free zsh help')
    async def test_shell_help_needs_no_interpreter_config_or_evidence(self):
        scripts=self.root/'scripts';scripts.mkdir();entry=scripts/'xplanet.sh';copy_launcher(entry)
        result=subprocess.run([str(entry),'diagnostics','--help'],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('No renderer or Python',result.stdout)
        self.assertFalse((self.root/'.state').exists());self.assertFalse((self.root/'config').exists())
        empty=subprocess.run([str(entry),'diagnostics','--renderer',''],capture_output=True,text=True,timeout=5)
        self.assertEqual(empty.returncode,2);self.assertIn('absolute executable path',empty.stderr)

    async def test_cached_feature_controls_are_refused_and_formatter_escapes_untrusted_values(self):
        from dataclasses import replace
        report=await diagnostic.probe(self.binary)
        poisoned=replace(report,features=('PNG\x1b]0;not-a-title\x07',))
        diagnostic.store(self.root,poisoned)
        with self.assertRaisesRegex(ValueError,'support list'):diagnostic.load(self.root)
        with patch('sys.argv',['diagnostic','--root',str(self.root),'--renderer',str(self.binary),'--show']),contextlib.redirect_stdout(io.StringIO()) as output,contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(diagnostic.main(),2)
        self.assertNotIn('\x1b',output.getvalue()+errors.getvalue());self.assertNotIn('\x07',output.getvalue()+errors.getvalue())
        text='\n'.join(poisoned.sections());self.assertNotIn('\x1b',text);self.assertNotIn('\x07',text)


class DiagnosticPresentationTests(unittest.TestCase):
    def test_tabs_are_readable_but_other_terminal_controls_stay_escaped(self):
        from configurator.resources import safe
        self.assertEqual(safe('\tPNG\n\tMac OS X'), '    PNG\n    Mac OS X')
        self.assertEqual(safe('bad\x1b[31m\r\x00'), r'bad\x1b[31m\r\x00')

    def test_file_identity_is_labeled_without_changing_precise_evidence(self):
        from configurator.resources import Capabilities
        stamp = (7, 42, 1048576, 1_000_000_001, 2_000_000_002)
        report = Capabilities(Path('/example/xplanet'), stamp, 'reported', ('PNG',), '\tPNG', 4, 'now')
        text = '\n'.join(report.sections())
        for value in ('Device: 7; inode: 42', '1,048,576 bytes (1.00 MiB)',
                      '1970-01-01 00:00:01.000000001 UTC', '1970-01-01 00:00:02.000000002 UTC'):
            self.assertIn(value, text)
        self.assertEqual(report.binary_identity, stamp)
        self.assertEqual(report.raw, '\tPNG')

    def test_unreasonable_cached_identity_does_not_crash_presentation(self):
        from configurator.resources import identity_summary
        for stamp in ((7, 42, 1 << 2000, 0, 0), (7, 42, -1, 0, 0)):
            self.assertEqual(identity_summary(stamp), 'Recorded file identity: unavailable')


class StockRendererMetadataTests(unittest.TestCase):
    def test_stock_renderer_is_explicit_placeholder_and_old_metadata_still_opens(self):
        from configurator.model import parse_saved_view
        scenes = ROOT/'scripts/configurator/samples/scenes'
        for definition in scenes.glob('*.def'):
            with self.subTest(scene=definition.stem):
                self.assertIn(b'XPLANET_BIN=/path/to/xplanet\n', definition.read_bytes())
                self.assertIn(b'XPLANET_HOME="$project_root"\n', definition.read_bytes())
        source=scenes/'earth-september.def'
        body=source.with_suffix('.conf').read_bytes()
        current=parse_saved_view(source.read_bytes(), body)
        previous=parse_saved_view(source.read_bytes().replace(b'/path/to/xplanet', b'/usr/bin/xplanet'),body)
        self.assertEqual(current.view, previous.view)
        self.assertEqual(current.saved_renderer, '/path/to/xplanet')
        self.assertEqual(previous.saved_renderer, '/usr/bin/xplanet')
