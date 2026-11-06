"""Signals target only an owned shell/process group in a disposable fixture."""
import os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from .support import PROJECT

class ShellSignalCleanupTests(unittest.TestCase):
    def test_python_selection_term_removes_owned_temp_and_preserves_old_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'config').mkdir();scripts=root/'scripts';scripts.mkdir();tools=root/'bin';tools.mkdir()
            choice=root/'config/totalmarker.python';choice.write_text('/prior/python\n')
            runner=scripts/'run-totalmarker';runner.write_text('#!/bin/sh\nexit 0\n');runner.chmod(0o700)
            ready=root/'rename-ready'
            mover=tools/'mv';mover.write_text('#!'+sys.executable+'\nimport pathlib,time\npathlib.Path('+repr(str(ready))+').write_text("ready")\ntime.sleep(20)\n');mover.chmod(0o700)
            code='project_root=$1;script_dir="$1/scripts";source "$2";python_save_selection /usr/bin/true'
            environment={**os.environ,'PATH':str(tools)+':/usr/bin:/bin'}
            # The suite launcher supplies an override; this test exercises writes
            # after the production override guard, not refusal before preparation.
            environment.pop('TOTALMARKER_PYTHON',None)
            process=subprocess.Popen(['/bin/zsh','-f','-c',code,'fixture',str(root),str(PROJECT/'scripts/lib/xplanet/python-runtime.zsh')],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.005)
                detail=process.communicate(timeout=2) if process.poll() is not None else ('still running','')
                self.assertTrue(ready.exists(),'owned rename barrier was not reached: '+repr(detail))
                self.assertTrue(list((root/'config').glob('.totalmarker.python.*')))
                os.killpg(process.pid,signal.SIGTERM)
                process.communicate(timeout=5)
                self.assertNotEqual(process.returncode,0)
                self.assertEqual(choice.read_text(),'/prior/python\n')
                self.assertEqual(list((root/'config').glob('.totalmarker.python.*')),[])
            finally:
                if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=5)
