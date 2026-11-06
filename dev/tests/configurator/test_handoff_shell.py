"""Native wrapper boundary; portable data tests remain in test_scene_handoff."""
import os,shlex,shutil,subprocess,sys,unittest
from tests.configurator import test_scene_handoff as fixtures
from configurator.model import ROOT
from configurator.handoff import create_plan,stage_plan,check_bundle

class HandoffShellTests(unittest.TestCase):
    setUp=fixtures.HandoffTests.setUp
    plan=fixtures.HandoffTests.plan

    def stdlib_env(self):
        shim=self.root/'stdlib python'
        shim.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -S "$@"\n');shim.chmod(0o700)
        env={**os.environ,'TOTALMARKER_PYTHON':str(shim),'HOME':str(self.root),'PYTHONPATH':str(self.root/'scripts'),'PYTHONDONTWRITEBYTECODE':'1'}
        probe=subprocess.run([str(shim),'-c','import importlib.util; assert importlib.util.find_spec("textual") is None'],env=env,text=True,capture_output=True,timeout=5)
        self.assertEqual(probe.returncode,0,probe.stderr)
        return env

    def test_readonly_setup_handoff_check_does_not_require_textual_or_run_legacy(self):
        shutil.copytree(ROOT/'scripts',self.root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        plan=self.plan();stage_plan(plan,self.target)
        env=self.stdlib_env()
        result=subprocess.run(['/bin/zsh',str(self.root/'scripts/xplanet.sh'),'setup','--check-handoff',str(self.target)],env=env,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('No scene selected',result.stdout)
        self.assertFalse((self.root/'forbidden').exists());self.assertFalse((self.root/'.state').exists())
        self.assertTrue(all((self.root/name).read_bytes()==raw for name,raw in self.legacy.items()))

    def test_export_wrapper_is_scriptable_without_ui_dependencies_or_setup(self):
        shutil.copytree(ROOT/'scripts',self.root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        env=self.stdlib_env()
        result=subprocess.run(['/bin/zsh',str(self.root/'scripts/xplanet.sh'),'config','--export-handoff',str(self.target),'--view',str(self.scene),'--renderer',sys.executable,'--geometry','1280x720'],env=env,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('No selection, setup, restart',result.stdout)
        self.assertFalse(check_bundle(self.root,self.target)['activation_ready'])
        self.assertFalse((self.root/'forbidden').exists());self.assertFalse((self.root/'.state').exists())

    def test_explicit_apply_requires_expected_choice_and_never_runs_setup_or_renderer(self):
        from configurator.selection import inspect_selection,read_revision
        shutil.copytree(ROOT/'scripts',self.root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        stage_plan(self.plan(),self.target);env=self.stdlib_env()
        def run(*options):
            return subprocess.run(['/bin/zsh',str(self.root/'scripts/xplanet.sh'),'config',*options],env=env,text=True,capture_output=True,timeout=20)
        result=run('--apply-handoff',str(self.target));self.assertEqual(result.returncode,2)
        self.assertIsNone(inspect_selection(self.root).revision);self.assertFalse((self.root/'.state').exists())
        result=run('--apply-handoff',str(self.target),'--expect-selected','legacy')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('No restart, renderer, provider or job action',result.stdout)
        selected=inspect_selection(self.root);self.assertIsNotNone(selected.revision);read_revision(self.root,selected.revision)
        wrong=run('--use-legacy','--expect-selected','legacy');self.assertEqual(wrong.returncode,2);self.assertEqual(inspect_selection(self.root),selected)
        status=run('--show-selection');self.assertEqual(status.returncode,0,status.stderr);self.assertIn(selected.revision,status.stdout)
        restored=run('--use-legacy','--expect-selected',selected.revision);self.assertEqual(restored.returncode,0,restored.stderr)
        self.assertIsNone(inspect_selection(self.root).revision)
        again=run('--select-revision',selected.revision,'--expect-selected','legacy');self.assertEqual(again.returncode,0,again.stderr)
        self.assertEqual(inspect_selection(self.root).revision,selected.revision)
        self.assertFalse((self.root/'forbidden').exists())
        self.assertTrue(all((self.root/name).read_bytes()==raw for name,raw in self.legacy.items()))
