"""Actionable native-file failures retain refusal and avoid raw path disclosure."""
import errno
import unittest
from configurator.fileio import native_error

class NativeErrorTests(unittest.TestCase):
    def test_known_failures_are_actionable_without_echoing_opaque_paths(self):
        for code,phrase in ((errno.ENOENT,'missing'),(errno.ELOOP,'symbolic link'),
                            (errno.EACCES,'Permission'),(errno.EEXIST,'new name'),
                            (errno.ENOSPC,'free space'),(errno.EROFS,'read-only'),
                            (errno.ENOTDIR,'not a directory'),(errno.EISDIR,'regular native file')):
            with self.subTest(errno=code):
                text=native_error(OSError(code,'raw exception wording','private-token\x1b[2J'))
                self.assertIn(phrase,text)
                self.assertNotIn('private-token',text);self.assertNotIn('\x1b',text)
                self.assertNotIn('raw exception',text)
    def test_unknown_os_errors_do_not_guess_and_validation_explanations_survive(self):
        self.assertIn('access failed',native_error(OSError(9999,'opaque raw detail')))
        self.assertEqual(native_error(ValueError('Ambiguous native sections; choose another source.')),
                         'Ambiguous native sections; choose another source.')
