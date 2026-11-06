"""Discovery must not execute optional UI tests or ignored local scratch."""
from pathlib import Path
import os,tempfile,unittest
from unittest.mock import patch
from . import run_core

class SuiteBoundaryTests(unittest.TestCase):
    def test_only_explicit_core_containers_are_enumerated(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'configurator/ui').mkdir(parents=True);(root/'.tmp').mkdir();(root/'configurator/.tmp').mkdir()
            for name in ('test_a.py','configurator/test_b.py','configurator/ui/test_optional.py','.tmp/test_private.py','configurator/.tmp/test_private.py'):
                (root/name).write_text('raise AssertionError("must not execute while enumerating")')
            with patch.object(run_core,'TEST_ROOT',root):
                self.assertEqual(run_core.module_names(),['tests.test_a','tests.configurator.test_b'])
    def test_unknown_portable_exclusion_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError,'Unknown test exclusions'):
            run_core.suite(exclude={'tests.missing_old_path'})

    def test_run_environment_is_private_distinct_and_restored_after_failure(self):
        original={name:os.environ.get(name) for name in ('TMPDIR','XDG_CACHE_HOME')}
        previous=tempfile.tempdir
        with self.assertRaisesRegex(RuntimeError,'fixture failure'):
            with run_core.isolated_environment() as first:
                self.assertEqual(first.stat().st_mode & 0o777,0o700)
                self.assertEqual(Path(tempfile.gettempdir()),first)
                self.assertEqual(Path(os.environ['XDG_CACHE_HOME']),first/'cache')
                owned=first/'owned';owned.write_text('fixture')
                with run_core.isolated_environment() as second:
                    self.assertNotEqual(first,second)
                    self.assertEqual(Path(tempfile.gettempdir()),second)
                self.assertFalse(second.exists());self.assertTrue(owned.is_file())
                self.assertEqual(Path(tempfile.gettempdir()),first)
                raise RuntimeError('fixture failure')
        self.assertFalse(first.exists())
        self.assertEqual({name:os.environ.get(name) for name in original},original)
        self.assertEqual(tempfile.tempdir,previous)
