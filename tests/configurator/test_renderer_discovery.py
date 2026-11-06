"""Discover local executables without evaluating local or imported definitions."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from configurator.renderer_discovery import discover

class RendererDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
        self.binary=self.root/'custom prefix/bin/xplanet';self.binary.parent.mkdir(parents=True)
        self.binary.write_text('#!/bin/sh\ntouch '+str(self.root/'EXECUTED')+'\n');self.binary.chmod(0o700)
    def test_setup_literal_custom_prefix_wins_with_sparse_path_without_execution(self):
        import shlex
        (self.root/'config/xp.def').write_text('XPLANET_BIN='+shlex.quote(str(self.binary))+'\n')
        with patch('configurator.renderer_discovery.shutil.which',side_effect=AssertionError('no fallback')):
            value,note=discover(self.root)
        self.assertEqual(value,str(self.binary));self.assertIn('literal project',note)
        self.assertFalse((self.root/'EXECUTED').exists())
    def test_computed_ambiguous_unavailable_or_symlink_configuration_does_not_execute_or_fallback(self):
        for text in ('XPLANET_BIN="$(touch '+str(self.root/'EXECUTED')+')"\n',
                     'XPLANET_BIN=/missing/xplanet\n',
                     'XPLANET_BIN=/one\nXPLANET_BIN=/two\n'):
            with self.subTest(text=text):
                (self.root/'config/xp.def').write_text(text)
                with patch('configurator.renderer_discovery.shutil.which',side_effect=AssertionError('no fallback')):
                    value,note=discover(self.root)
                self.assertEqual(value,'');self.assertTrue(note);self.assertFalse((self.root/'EXECUTED').exists())
        (self.root/'config/xp.def').unlink();(self.root/'config/xp.def').symlink_to(self.binary)
        self.assertEqual(discover(self.root)[0],'')
    def test_explicit_choice_is_authoritative_and_not_validated_by_execution(self):
        value,note=discover(self.root,'/explicit/unavailable')
        self.assertEqual(value,'/explicit/unavailable');self.assertIn('Explicit',note)
    def test_path_and_homebrew_fallbacks_without_package_manager_execution(self):
        with patch('configurator.renderer_discovery.shutil.which',return_value=str(self.binary)):
            self.assertEqual(discover(self.root)[0],str(self.binary))
        home=self.root/'home';candidate=home/'.homebrew/bin/xplanet'
        with patch.dict(os.environ,{'HOME':str(home)}),patch('configurator.renderer_discovery.shutil.which',return_value=None),patch('configurator.renderer_discovery.executable',side_effect=lambda value:Path(value)==candidate):
            self.assertEqual(discover(self.root)[0],str(candidate))
    def test_blank_project_assignment_allows_pre_setup_path_discovery(self):
        (self.root/'config/xp.def').write_text("XPLANET_BIN=''\n")
        with patch('configurator.renderer_discovery.shutil.which',return_value=str(self.binary)):
            self.assertEqual(discover(self.root)[0],str(self.binary))

    def test_large_blank_definition_has_bounded_discovery_cost(self):
        import subprocess,sys
        (self.root/'config/xp.def').write_text('\n'*200000)
        code="from unittest.mock import patch; from pathlib import Path; from configurator.renderer_discovery import discover; import sys; expected=sys.executable; p=patch('configurator.renderer_discovery.shutil.which',return_value=expected); p.start(); assert discover(Path(sys.argv[1]))[0]==expected"
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.root)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_filesystem_errors_leave_project_renderer_unavailable_without_fallback(self):
        import errno,shlex
        (self.root/'config/xp.def').write_text('XPLANET_BIN='+shlex.quote(str(self.binary))+'\n')
        for code in (errno.EACCES,errno.ENAMETOOLONG):
            with self.subTest(errno=code),patch('configurator.renderer_discovery.Path.is_file',side_effect=OSError(code,'fixture filesystem failure')),patch('configurator.renderer_discovery.shutil.which',side_effect=AssertionError('no fallback')):
                value,note=discover(self.root)
                self.assertEqual(value,'');self.assertIn('unavailable',note)
