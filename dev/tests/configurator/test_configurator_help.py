"""Help is bundled documentation, not dependency preparation or configuration."""
from pathlib import Path
import contextlib,io,os,shutil,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from configurator.guide import read_guide,GUIDE,LIMIT
from configurator.model import ROOT

class GuideTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()

    def test_direct_module_guide_is_noninteractive_and_does_not_import_textual(self):
        code='''import sys
from configurator.__main__ import main
sys.argv=['configurator','--guide']
assert main()==0
assert not any(name=='textual' or name.startswith('textual.') for name in sys.modules)
'''
        result=subprocess.run([sys.executable,'-B','-c',code],cwd=self.root,env={**os.environ,'PYTHONPATH':str(ROOT/'scripts'),'HOME':str(self.root),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,read_guide());self.assertEqual(list(self.root.iterdir()),[])

    def test_reader_refuses_linked_oversized_or_invalid_guide(self):
        real=self.root/'real.md';real.write_text('# Fixture guide\n');link=self.root/'link.md';link.symlink_to(real)
        with patch('configurator.guide.GUIDE',link),self.assertRaises(OSError):read_guide()
        real.write_bytes(b'x'*(LIMIT+1))
        with patch('configurator.guide.GUIDE',real),self.assertRaises(ValueError):read_guide()
        real.write_bytes(b'\xff')
        with patch('configurator.guide.GUIDE',real),self.assertRaises(UnicodeError):read_guide()

    def test_posix_wrapper_help_and_full_guide_need_no_python_or_runtime(self):
        scripts=self.root/'scripts';scripts.mkdir();(self.root/'docs/configurator').mkdir(parents=True)
        wrapper=scripts/'run-configurator';shutil.copyfile(ROOT/'scripts/run-configurator',wrapper);wrapper.chmod(0o700)
        (self.root/'docs/configurator/user-guide.md').write_text(read_guide())
        guard=self.root/'unexpected';runner=scripts/'run-totalmarker';runner.write_text('#!/bin/sh\nprintf bad > '+str(guard)+'\nexit 97\n');runner.chmod(0o700)
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for args in (['--help'],['--guide']):
            result=subprocess.run(['/bin/sh',str(wrapper),*args],cwd='/',env={**os.environ,'TOTALMARKER_PYTHON':'/must-not-execute'},capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            if args==['--guide']:self.assertEqual(result.stdout,read_guide())
            else:self.assertIn('config --guide',result.stdout);self.assertIn('F1',result.stdout)
        self.assertFalse(guard.exists());self.assertFalse((self.root/'.state').exists())
        self.assertEqual(before,{str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        bad=subprocess.run(['/bin/sh',str(wrapper),'--guide','--view','/not/opened'],capture_output=True,text=True)
        self.assertEqual(bad.returncode,2);self.assertIn('takes no other options',bad.stderr)

    def test_nested_manual_directory_symlink_is_refused_without_preparation(self):
        scripts=self.root/'scripts';scripts.mkdir();(self.root/'docs').mkdir()
        wrapper=scripts/'run-configurator';shutil.copyfile(ROOT/'scripts/run-configurator',wrapper)
        actual=self.root/'manual';actual.mkdir();guide=actual/'user-guide.md';guide.write_text(read_guide())
        (self.root/'docs/configurator').symlink_to(actual,target_is_directory=True)
        with patch('configurator.guide.GUIDE',self.root/'docs/configurator/user-guide.md'),self.assertRaises(ValueError):read_guide()
        result=subprocess.run(['/bin/sh',str(wrapper),'--guide'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('guide unavailable',result.stderr)
        self.assertFalse((self.root/'.state').exists());self.assertEqual(guide.read_text(),read_guide())

    def test_looping_manual_directory_is_reported_without_traceback(self):
        from configurator.__main__ import main
        scripts=self.root/'scripts';scripts.mkdir();(self.root/'docs').mkdir()
        wrapper=scripts/'run-configurator';shutil.copyfile(ROOT/'scripts/run-configurator',wrapper)
        parent=self.root/'docs/configurator';parent.symlink_to('configurator',target_is_directory=True)
        with patch('configurator.guide.GUIDE',parent/'user-guide.md'):
            with self.assertRaises((ValueError,OSError)):read_guide()
            output=io.StringIO()
            with patch.object(sys,'argv',['configurator','--guide']),contextlib.redirect_stderr(output):
                self.assertEqual(main(),2)
            self.assertIn('Guide unavailable',output.getvalue())
        result=subprocess.run(['/bin/sh',str(wrapper),'--guide'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('guide unavailable',result.stderr)
        self.assertFalse((self.root/'.state').exists())

    def test_missing_wrapper_guide_reports_error_without_starting_runtime(self):
        (self.root/'scripts').mkdir();wrapper=self.root/'scripts/run-configurator';shutil.copyfile(ROOT/'scripts/run-configurator',wrapper)
        result=subprocess.run(['/bin/sh',str(wrapper),'--guide'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('guide unavailable',result.stderr)
        self.assertFalse((self.root/'.state').exists())

    def test_existing_runtime_guidance_preserves_drafts_and_never_prepares_over_it(self):
        from configurator.runtime import prepare
        env=self.root/'.state/configurator/venv';env.mkdir(parents=True)
        drafts=env.parent/'drafts';drafts.mkdir();original=drafts/'keep';original.write_bytes(b'private recovery data')
        with patch('configurator.runtime.subprocess.run',side_effect=AssertionError('no downloads')),self.assertRaisesRegex(ValueError,'Preserve .state/configurator/drafts'):
            prepare(self.root)
        self.assertEqual(original.read_bytes(),b'private recovery data')
