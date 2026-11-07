"""Evidence-backed scene preservation, outcome and runtime consistency checks."""
from pathlib import Path
from contextlib import redirect_stdout
import io,os,pty,shutil,sys,tempfile,unittest
from unittest.mock import patch
from configurator.fileio import OwnedFiles,new_directory
from configurator.library import save_named
from configurator.workspace import open_view
from configurator.model import View,ROOT
from configurator.runtime import ready,lock_digest
from configurator.__main__ import report_result

class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.library=self.root/'library';self.library.mkdir()

    def test_cleanup_does_not_adopt_bytes_changed_during_fsync(self):
        fd=os.open(self.library,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,fd);owner=OwnedFiles(fd)
        original=os.fsync
        def sync(child):
            original(child);(self.library/'new.conf').write_bytes(b'unique concurrent editor content')
        with patch('configurator.fileio.os.fsync',side_effect=sync):owner.write('new.conf',b'p'*len(b'unique concurrent editor content'))
        self.assertEqual(owner.cleanup(),['new.conf'])
        self.assertEqual((self.library/'new.conf').read_bytes(),b'unique concurrent editor content')

    def test_new_directory_refuses_moved_parent_and_preserves_replacement(self):
        original=OwnedFiles.write; moved=self.root/'moved'
        def write(owner,name,data):
            original(owner,name,data)
            if not moved.exists():
                self.library.rename(moved);self.library.mkdir();(self.library/'keep').write_bytes(b'replacement content')
        with patch.object(OwnedFiles,'write',autospec=True,side_effect=write),self.assertRaisesRegex(ValueError,'directory changed'):
            new_directory(self.library/'scene',(('xp.conf',b'known'),('xp.def',b'known')))
        self.assertEqual((self.library/'keep').read_bytes(),b'replacement content')
        self.assertFalse((self.library/'scene').exists());self.assertFalse((moved/'scene').exists())

    def test_named_save_refuses_moved_library_and_cleans_only_owned_files(self):
        original=OwnedFiles.write;moved=self.root/'moved';(self.library/'old.conf').write_bytes(b'original user scene')
        def write(owner,name,data):
            original(owner,name,data)
            if not moved.exists():
                self.library.rename(moved);self.library.mkdir();(self.library/'keep').write_bytes(b'new directory content')
        with patch.object(OwnedFiles,'write',autospec=True,side_effect=write),self.assertRaisesRegex(ValueError,'directory changed'):
            save_named(self.library/'new.conf',View(),sys.executable)
        self.assertEqual((moved/'old.conf').read_bytes(),b'original user scene');self.assertEqual((self.library/'keep').read_bytes(),b'new directory content')
        self.assertFalse((moved/'new.conf').exists());self.assertFalse((moved/'new.def').exists())

    def test_open_refuses_changed_directory_instead_of_reporting_nonexistent_source(self):
        source=save_named(self.library/'scene.conf',View(),sys.executable)
        from configurator import workspace
        original=workspace.read_bounded;moved=self.root/'moved';before={p.name:p.read_bytes() for p in self.library.iterdir()}
        def read(fd,limit):
            data=original(fd,limit)
            if not moved.exists():self.library.rename(moved);self.library.mkdir();(self.library/'keep').write_bytes(b'new user data')
            return data
        with patch.object(workspace,'read_bounded',side_effect=read),self.assertRaisesRegex(ValueError,'directory changed'):open_view(source)
        self.assertEqual(before,{p.name:p.read_bytes() for p in moved.iterdir()});self.assertEqual((self.library/'keep').read_bytes(),b'new user data')

    def test_selected_case_alias_must_identify_the_opened_canonical_file(self):
        source=save_named(self.library/'scene.conf',View(),sys.executable);other=self.root/'other';other.write_bytes(b'other selected entry')
        original=os.stat
        def stat(path,*args,**kwargs):
            if path=='scene.CONF' and kwargs.get('dir_fd') is not None:return original(other)
            return original(path,*args,**kwargs)
        with patch('configurator.workspace.os.stat',side_effect=stat),self.assertRaisesRegex(ValueError,'differs from the canonical'):open_view(source.with_suffix('.CONF'))
        self.assertEqual(other.read_bytes(),b'other selected entry')

    def test_cleanup_retains_a_file_when_expected_metadata_is_incomplete(self):
        fd=os.open(self.library,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,fd);owner=OwnedFiles(fd)
        owner.write('new.conf',b'known');owner.expected.clear()
        self.assertEqual(owner.cleanup(),['new.conf']);self.assertEqual((self.library/'new.conf').read_bytes(),b'known')

    def test_interrupt_before_expected_hash_creates_no_file_or_cleanup_error(self):
        fd=os.open(self.library,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,fd);owner=OwnedFiles(fd)
        with patch('configurator.fileio.hashlib.sha256',side_effect=KeyboardInterrupt()),self.assertRaises(KeyboardInterrupt):owner.write('new.conf',b'known')
        self.assertEqual(owner.cleanup(),[]);self.assertEqual(list(self.library.iterdir()),[])

    def test_moved_child_replacement_and_concurrent_material_survive_refusal(self):
        original=OwnedFiles.write;moved=self.library/'moved';target=self.library/'scene'
        def write(owner,name,data):
            original(owner,name,data)
            if not moved.exists():
                target.rename(moved);target.mkdir();(target/'keep').write_bytes(b'replacement')
                (moved/'unique').write_bytes(b'concurrent material')
        with patch.object(OwnedFiles,'write',autospec=True,side_effect=write),self.assertRaisesRegex(ValueError,'directory changed'):
            new_directory(target,(('xp.conf',b'known'),('xp.def',b'known')))
        self.assertEqual((target/'keep').read_bytes(),b'replacement');self.assertEqual((moved/'unique').read_bytes(),b'concurrent material')
        self.assertFalse((moved/'xp.conf').exists());self.assertFalse((moved/'xp.def').exists())

class ResultTests(unittest.TestCase):
    def test_saved_result_keeps_selection_change_and_uncertainty_visible(self):
        for label,code in ((None,0),('legacy',0),('a'*64,0),('uncertain',5)):
            output=io.StringIO();result=('saved','/new/scene.conf') if label is None else ('saved','/new/scene.conf',label)
            with redirect_stdout(output):self.assertEqual(report_result(result),code)
            text=output.getvalue();self.assertIn('/new/scene.conf',text)
            if label is None:self.assertIn('desktop settings were not changed',text)
            else:self.assertNotIn('desktop settings were not changed',text)
            if label=='uncertain':self.assertIn('inspect config/desktop.scene',text)
            elif label is not None:self.assertIn('Restart explicitly',text)

class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        (self.root/'scripts/configurator').mkdir(parents=True);(self.root/'scripts/configurator/requirements.txt').write_text('textual==8.2.8 --hash=sha256:fixture\n')
        self.location=self.root/'.state/configurator';(self.location/'venv').mkdir(parents=True)
        (self.location/'lock.sha256').write_text(lock_digest(self.root))

    def test_ready_is_bound_to_project_environment_and_refuses_linked_folders(self):
        with patch('configurator.runtime.version',return_value='8.2.8'),patch('sys.prefix',str(self.location/'venv')):
            self.assertTrue(ready(self.root))
            with patch('sys.prefix',str(self.root/'foreign-venv')):self.assertFalse(ready(self.root))
            (self.location/'venv').rename(self.location/'elsewhere');(self.location/'venv').symlink_to(self.location/'elsewhere')
            self.assertFalse(ready(self.root))

    def test_launcher_refuses_linked_runtime_before_executing_foreign_python(self):
        shutil.copyfile(ROOT/'scripts/run-configurator',self.root/'scripts/run-configurator');(self.root/'scripts/run-configurator').chmod(0o700)
        (self.location/'venv').rename(self.location/'foreign');(self.location/'venv').symlink_to(self.location/'foreign')
        binary=self.location/'foreign/bin/python';binary.parent.mkdir();guard=self.root/'executed'
        binary.write_text('#!/bin/sh\nprintf bad > '+str(guard)+'\nexit 4\n');binary.chmod(0o700)
        master,slave=pty.openpty()
        try:
            import subprocess
            result=subprocess.run([str(self.root/'scripts/run-configurator')],stdin=slave,stdout=slave,stderr=subprocess.PIPE,timeout=5,env={**os.environ,'HOME':str(self.root)})
        finally:os.close(master);os.close(slave)
        self.assertEqual(result.returncode,4,result.stderr);self.assertFalse(guard.exists())


class RuntimeHintTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();scripts=self.root/'scripts';scripts.mkdir()
        self.wrapper=scripts/'run-configurator';shutil.copyfile(ROOT/'scripts/run-configurator',self.wrapper)
        # Launching the studio must never select a preparation interpreter or install dependencies.
        (scripts/'run-totalmarker').write_text('#!/bin/sh\nexit 91\n')
        (scripts/'run-totalmarker').chmod(0o700)

    def snapshot(self):
        return {str(path.relative_to(self.root)): ('link',os.readlink(path)) if path.is_symlink()
                else ('directory',) if path.is_dir() else ('file',path.read_bytes())
                for path in self.root.rglob('*')}

    def launch(self):
        import subprocess
        before=self.snapshot();master,slave=pty.openpty()
        try:
            result=subprocess.run(['/bin/sh',str(self.wrapper)],stdin=slave,stdout=slave,
                                  stderr=subprocess.PIPE,text=True,timeout=5,
                                  env={**os.environ,'HOME':str(self.root)})
        finally:os.close(master);os.close(slave)
        self.assertEqual(result.returncode,4,result.stderr)
        self.assertIn('No dependencies were installed.',result.stderr)
        self.assertEqual(before,self.snapshot(),'runtime failure must remain read-only')
        return result.stderr

    def test_missing_runtime_suggests_explicit_preparation(self):
        output=self.launch()
        self.assertIn('Prepare the isolated environment: ./scripts/xplanet.sh config --prepare',output)
        self.assertIn('downloads pinned dependencies from PyPI',output)
        self.assertIn('Then run ./scripts/xplanet.sh config again.',output)
        self.assertIn('./scripts/xplanet.sh config --guide',output)
        self.assertFalse((self.root/'.state').exists())

    def test_missing_venv_with_recovery_drafts_suggests_preparation(self):
        drafts=self.root/'.state/configurator/drafts';drafts.mkdir(parents=True)
        (drafts/'keep').write_bytes(b'private recovery draft')
        self.assertIn('config --prepare',self.launch())

    def test_existing_incomplete_or_failed_runtime_suggests_rebuilding(self):
        runtime=self.root/'.state/configurator/venv';runtime.mkdir(parents=True)
        for executable in (False,True):
            with self.subTest(executable=executable):
                if executable:
                    binary=runtime/'bin/python';binary.parent.mkdir()
                    binary.write_text('#!/bin/sh\nexit 4\n');binary.chmod(0o700)
                output=self.launch()
                self.assertIn('config --guide',output)
                self.assertIn('Preserve .state/configurator/drafts',output)
                self.assertIn('does not replace an existing environment',output)
                self.assertNotIn('config --prepare',output)

    def test_obstructed_or_linked_paths_do_not_suggest_preparation(self):
        for relative in ('.state','.state/configurator','.state/configurator/venv',
                         '.state/configurator/lock.sha256'):
            for kind in ('file','link'):
                if relative.endswith('lock.sha256') and kind=='file':continue
                with self.subTest(path=relative,kind=kind):
                    state=self.root/'.state'
                    if state.is_symlink() or state.is_file():state.unlink()
                    elif state.exists():shutil.rmtree(state)
                    target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                    if kind=='link':target.symlink_to(self.root/'missing-target')
                    else:target.write_bytes(b'keep')
                    output=self.launch()
                    self.assertIn('config --guide',output)
                    self.assertNotIn('config --prepare',output)
