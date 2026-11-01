"""Desktop lifecycle uses fake process identities; never host process APIs."""
import copy
import ctypes
import fcntl
import importlib.util
import json
import io
import plistlib
import tempfile
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from .support import PROJECT, Sandbox

spec = importlib.util.spec_from_file_location(
    'xplanet_display_process', PROJECT / 'scripts/lib/xplanet/display_process.py')
display = importlib.util.module_from_spec(spec)
spec.loader.exec_module(display)


class FakeProcesses:
    def __init__(self):
        self.table = {}
        self.spawned = []
        self.signaled = []
        self.spawn_status = 0
        self.linger = False
        self.after_spawn = None

    def pids(self):
        return list(self.table)

    def snapshot(self, pid):
        return copy.deepcopy(self.table.get(pid))

    def terminate(self, pid):
        self.signaled.append(pid)
        if not self.linger:
            self.table.pop(pid, None)

    def spawn(self, argv):
        self.spawned.append(argv)
        if self.after_spawn:
            self.after_spawn()
        if not self.spawn_status:
            self.table[909] = identity(argv, 909)
        return self.spawn_status

    def pause(self):
        pass


def identity(argv, pid=101):
    return {'pid': pid, 'uid': os.geteuid(), 'start': [1700000000, pid],
            'executable': str(Path(argv[0]).resolve()), 'argv': list(argv)}


class DesktopProcessTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.api = FakeProcesses()
        self.argv = [str(self.root / 'bin/xplanet'), f'-searchdir={self.root}',
                     f'-config={self.root}/config/xp.conf', '-projection=lambert',
                     '-date_format=%D at %r', '-fork']

    def run_display(self, restart=False, **kwargs):
        return display.operate(self.root, self.argv, restart, self.api, **kwargs)

    def test_start_is_idempotent_and_records_exact_existing_desktop(self):
        self.api.table[101] = identity(self.argv)
        code, message = self.run_display()
        self.assertEqual(code, 0)
        self.assertIn('already running', message)
        self.assertFalse(self.api.spawned)
        self.assertEqual(json.loads((self.root / '.state/xplanet/display.json').read_text()),
                         self.api.table[101])

    def test_start_ignores_finite_render_and_other_checkout(self):
        self.api.table[101] = identity([*self.argv, '-output', '/tmp/frame.png'])
        self.api.table[202] = identity([arg.replace(str(self.root), '/other')
                                       for arg in self.argv], 202)
        self.assertEqual(self.run_display()[0], 0)
        self.assertEqual(len(self.api.spawned), 1)
        self.assertFalse(self.api.signaled)

    def test_restart_signals_only_exact_desktop(self):
        self.api.table[101] = identity(self.argv)
        self.api.table[202] = identity([*self.argv, '-num_times=1'], 202)
        self.run_display(restart=True)
        self.assertEqual(self.api.signaled, [101])
        self.assertIn(202, self.api.table)
        self.assertEqual(len(self.api.spawned), 1)

    def test_recorded_previous_config_can_be_restarted(self):
        self.api.table[101] = identity(self.argv)
        self.run_display()
        self.argv = [arg.replace('lambert', 'orthographic') for arg in self.argv]
        self.run_display(restart=True)
        self.assertEqual(self.api.signaled, [101])
        self.assertEqual(self.api.spawned, [self.argv])

    def test_native_prefilter_includes_saved_previous_executable_before_inspection(self):
        self.argv[0] = str(self.root / 'old/renamed-renderer')
        self.api.table[101] = identity(self.argv)
        self.run_display()
        old_executable = self.argv[0]
        self.argv = [str(self.root / 'new/another-renderer'), *self.argv[1:]]
        constructor_calls = []
        def fake_native(executables):
            constructor_calls.append(executables)
            return self.api
        with patch.object(display, 'MacProcesses', side_effect=fake_native):
            display.operate(self.root, self.argv, restart=True)
        self.assertIn(old_executable, constructor_calls[0])
        self.assertIn(self.argv[0], constructor_calls[0])
        self.assertEqual(self.api.signaled, [101])
        self.assertEqual(self.api.spawned, [self.argv])

    def test_unrecorded_changed_config_or_executable_refuses_duplicate(self):
        for field in ('argv', 'executable'):
            self.api.table = {101: identity(self.argv)}
            if field == 'argv':
                self.api.table[101]['argv'][3] = '-projection=orthographic'
            else:
                self.api.table[101]['executable'] = '/old/xplanet'
            with self.assertRaisesRegex(display.IdentityError, 'unrecorded desktop'):
                self.run_display(restart=True)
            self.assertFalse(self.api.spawned)
            self.assertFalse(self.api.signaled)

    def test_reused_pid_record_does_not_authorize_signal(self):
        self.api.table[101] = identity(self.argv)
        self.run_display()
        self.api.table[101] = identity([*self.argv, '-output=frame.png'])
        self.api.table[101]['start'][1] += 1
        self.run_display(restart=True)
        self.assertFalse(self.api.signaled)
        self.assertIn(101, self.api.table)

    def test_identity_change_immediately_before_term_refuses(self):
        value = identity(self.argv)
        self.api.table[101] = value
        original = self.api.snapshot
        count = 0
        def changing(pid):
            nonlocal count
            count += 1
            found = original(pid)
            if count >= 2:
                found['start'][1] += 1
            return found
        self.api.snapshot = changing
        with self.assertRaisesRegex(display.IdentityError, 'changed before stop'):
            self.run_display(restart=True)
        self.assertFalse(self.api.signaled)
        self.assertFalse(self.api.spawned)

    def test_multiple_matching_desktops_refuse_without_signaling(self):
        self.api.table = {101: identity(self.argv), 202: identity(self.argv, 202)}
        with self.assertRaisesRegex(display.IdentityError, 'multiple matching'):
            self.run_display(restart=True)
        self.assertFalse(self.api.signaled)

    def test_lingering_desktop_prevents_new_launch(self):
        self.api.table[101] = identity(self.argv)
        self.api.linger = True
        with self.assertRaisesRegex(display.IdentityError, 'still running'):
            self.run_display(restart=True)
        self.assertFalse(self.api.spawned)

    def test_renderer_failure_status_is_preserved(self):
        self.api.spawn_status = 37
        self.assertEqual(self.run_display(), (37, ''))
        self.assertFalse((self.root / '.state/xplanet/display.json').exists())

    def test_status_does_not_spawn_or_signal(self):
        self.assertEqual(self.run_display(status_only=True), (0, ''))
        self.api.table[101] = identity(self.argv)
        self.assertEqual(self.run_display(status_only=True), (0, '101'))
        self.assertFalse(self.api.spawned)
        self.assertFalse(self.api.signaled)

    def test_concurrent_lifecycle_lock_refuses(self):
        directory = self.root / '.state/xplanet'
        directory.mkdir(parents=True)
        with (directory / 'display.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(display.IdentityError, 'another desktop'):
                self.run_display()
        self.assertFalse(self.api.spawned)

    def test_state_symlink_is_refused_without_outside_write(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.root / '.state').symlink_to(outside)
        with self.assertRaises(OSError):
            self.run_display()
        self.assertEqual(list(outside.iterdir()), [])

    def test_record_symlink_is_refused_without_reading_or_replacing_target(self):
        directory = self.root / '.state/xplanet'
        directory.mkdir(parents=True)
        outside = self.base / 'outside-record'
        outside.write_text('keep')
        (directory / 'display.json').symlink_to(outside)
        with self.assertRaises(OSError):
            self.run_display()
        self.assertEqual(outside.read_text(), 'keep')
        self.assertTrue((directory / 'display.json').is_symlink())

    def test_parent_swap_does_not_redirect_record_publication(self):
        outside = self.base / 'outside'
        outside.mkdir()
        original = self.root / '.state-original'
        def swap():
            (self.root / '.state').rename(original)
            (self.root / '.state').symlink_to(outside)
        self.api.after_spawn = swap
        self.assertEqual(self.run_display()[0], 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue((original / 'xplanet/display.json').is_file())

    def test_atomic_record_failure_preserves_original_record(self):
        self.api.table[101] = identity(self.argv)
        self.run_display()
        path = self.root / '.state/xplanet/display.json'
        before = path.read_bytes()
        with patch.object(display.os, 'replace', side_effect=OSError('simulated')):
            with self.assertRaises(OSError):
                self.run_display()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob('.display-*')), [])


class NativeProcessPrefilterTests(unittest.TestCase):
    def test_renamed_truncated_command_keeps_exact_identity(self):
        executable = '/fixture/a-very-long-renamed-renderer'
        argv = [executable, '-searchdir=/fixture/root', '-config=/fixture/root/config/xp.conf', '-fork']
        info = display.BSDInfo()
        info.pid, info.uid = 101, os.geteuid()
        info.start_sec, info.start_usec = 1700000000, 123
        info.comm = os.fsencode(Path(executable).name)[:15]
        api = display.MacProcesses.__new__(display.MacProcesses)
        api.commands = display.command_names([executable])
        api.info = lambda pid: info
        encoded = [os.fsencode(arg) for arg in argv]
        raw = struct.pack('=i', len(argv)) + os.fsencode(executable) + b'\0\0' + b'\0'.join(encoded) + b'\0'
        class FakeLib:
            def proc_pidpath(self, pid, buffer, size):
                buffer.value = os.fsencode(executable)
                return len(buffer.value)
        class FakeLibC:
            def sysctl(self, mib, count, buffer, size, new, new_size):
                ctypes.memmove(buffer, raw, len(raw))
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value = len(raw)
                return 0
        api.lib, api.libc = FakeLib(), FakeLibC()
        found = api.snapshot(101)
        self.assertEqual(found['executable'], executable)
        self.assertEqual(found['argv'], argv)
        self.assertEqual(found['start'], [1700000000, 123])

    def test_unrelated_command_never_inspects_executable_or_argv(self):
        api = display.MacProcesses.__new__(display.MacProcesses)
        api.commands = display.command_names(['/fixture/renamed-renderer'])
        info = display.BSDInfo()
        info.pid, info.uid, info.comm = 202, os.geteuid(), b'unrelated'
        api.info = lambda pid: info
        class Forbidden:
            def __getattr__(self, name):
                raise AssertionError('unrelated process must not be inspected')
        api.lib, api.libc = Forbidden(), Forbidden()
        self.assertIsNone(api.snapshot(202))


class ProcessArgumentTests(unittest.TestCase):
    def test_exact_argument_boundaries_and_spaces(self):
        args = [b'/project with spaces/xplanet', b'-date_format=%D at %r', b'', b'-fork']
        raw = struct.pack('=i', len(args)) + b'/real/xplanet\0\0\0' + b'\0'.join(args) + b'\0ENV=value\0'
        self.assertEqual(display.parse_procargs(raw), [os.fsdecode(arg) for arg in args])

    def test_malformed_arguments_fail_closed(self):
        for raw in (b'', struct.pack('=i', 0) + b'\0',
                    struct.pack('=i', 2) + b'/exec\0\0one\0'):
            with self.subTest(raw=raw):
                with self.assertRaises(display.IdentityError):
                    display.parse_procargs(raw)

    def test_sdk_bsdinfo_layout(self):
        self.assertEqual(ctypes.sizeof(display.BSDInfo), 136)
        self.assertEqual(display.BSDInfo.start_sec.offset, 120)

    def test_native_api_is_not_initialized_on_import(self):
        with patch.object(display.ctypes, 'CDLL', side_effect=AssertionError('host API')):
            fresh_spec = importlib.util.spec_from_file_location(
                'fresh_display_process', PROJECT / 'scripts/lib/xplanet/display_process.py')
            fresh = importlib.util.module_from_spec(fresh_spec)
            fresh_spec.loader.exec_module(fresh)
            self.assertTrue(callable(fresh.parse_procargs))


spec = importlib.util.spec_from_file_location(
    'xplanet_launchd_registration', PROJECT / 'scripts/lib/xplanet/launchd_registration.py')
registration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registration)


class LaunchdRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'Label': 'local.xplanet.start',
                         'ProgramArguments': ['/project with spaces/scripts/xplanet.sh', 'start'],
                         'WorkingDirectory': '/project with spaces',
                         'EnvironmentVariables': {'TOTALMARKER_PYTHON': '/Python with spaces/bin/python3'}}
        self.text = (r'{"Label" = "local.xplanet.start"; "PID" = 123;'
                     r'"Program" = "/project with spaces/scripts/xplanet.sh";'
                     r'"LastExitStatus" = 0; "ProgramArguments" = ('
                     r'"/project with spaces/scripts/xplanet.sh"; "start";);'
                     r'"WorkingDirectory" = "/project with spaces";'
                     r'"EnvironmentVariables" = {"TOTALMARKER_PYTHON" = "/Python with spaces/bin/python3";};};')

    def test_actual_legacy_array_separators_and_spaces_match(self):
        self.assertTrue(registration.matches(registration.parse_registration(self.text), self.expected))

    def guest_dictionary(self):
        # Shape captured from real macOS 27 launchctl list in a disposable guest;
        # synthetic paths/label. WorkingDirectory/EnvironmentVariables are absent.
        return registration.parse_registration(r'''{
            "StandardOutPath" = "/project with spaces/logs/xplanet.log";
            "LimitLoadToSessionType" = "Aqua";
            "StandardErrorPath" = "/project with spaces/logs/xplanet-error.log";
            "Label" = "local.xplanet.start";
            "OnDemand" = true;
            "LastExitStatus" = 0;
            "Program" = "/project with spaces/scripts/xplanet.sh";
            "ProgramArguments" = (
                "/project with spaces/scripts/xplanet.sh";
                "start";
            );
        };''')

    def test_real_guest_dictionary_matches_identity_with_explicit_unknown_settings(self):
        status, unknown = registration.registration_status(self.guest_dictionary(), self.expected)
        self.assertEqual(status, 3)
        self.assertEqual(unknown, ['working directory', 'selected Python'])

    def test_omitted_facts_do_not_hide_reported_mismatches(self):
        original = self.guest_dictionary()
        for key, replacement in (('WorkingDirectory', '/wrong'),
                                 ('EnvironmentVariables', {'TOTALMARKER_PYTHON': '/wrong/python'}),
                                 ('EnvironmentVariables', 'malformed'),
                                 ('Program', '/wrong/program'),
                                 ('ProgramArguments', ['/wrong/program', 'start']),
                                 ('Label', 'other')):
            with self.subTest(key=key):
                value = copy.deepcopy(original)
                value[key] = replacement
                self.assertEqual(registration.registration_status(value, self.expected), (1, []))

    def test_missing_program_and_relative_invocation_cannot_verify_identity(self):
        value = self.guest_dictionary()
        del value['Program']
        self.assertEqual(registration.registration_status(value, self.expected), (1, []))
        expected = copy.deepcopy(self.expected)
        expected['ProgramArguments'][0] = './scripts/xplanet.sh'
        value.update(Program='./scripts/xplanet.sh', ProgramArguments=expected['ProgramArguments'])
        self.assertEqual(registration.registration_status(value, expected), (1, []))

    def test_only_unreported_facts_are_named_unknown(self):
        value = self.guest_dictionary()
        value['WorkingDirectory'] = self.expected['WorkingDirectory']
        value['EnvironmentVariables'] = {'OTHER': 'value'}
        self.assertEqual(registration.registration_status(value, self.expected),
                         (3, ['selected Python']))
        value['EnvironmentVariables'] = self.expected['EnvironmentVariables']
        del value['WorkingDirectory']
        self.assertEqual(registration.registration_status(value, self.expected),
                         (3, ['working directory']))

    def test_helper_exit_and_notice_distinguish_unknown_from_full_match(self):
        # Reconstruct legacy literals for the helper stdin contract.
        text = '{"Label" = "local.xplanet.start"; "Program" = "/project with spaces/scripts/xplanet.sh"; "ProgramArguments" = ("/project with spaces/scripts/xplanet.sh"; "start";);};'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'job.plist'
            path.write_bytes(plistlib.dumps(self.expected))
            output = io.StringIO()
            stdin = io.TextIOWrapper(io.BytesIO(text.encode()))
            with patch.object(registration.sys, 'argv', ['helper', str(path)]), \
                    patch.object(registration.sys, 'stdin', stdin), \
                    patch.object(registration.sys, 'stdout', output):
                self.assertEqual(registration.main(), 3)
            self.assertIn('working directory, selected Python', output.getvalue())
            self.assertIn('not verified', output.getvalue())
            self.assertNotIn('/project', output.getvalue())

    def test_changed_label_argv_directory_python_and_program_refuse(self):
        original = registration.parse_registration(self.text)
        for key, replacement in (('Label', 'other'), ('ProgramArguments', ['other', 'start']),
                                 ('WorkingDirectory', '/other'),
                                 ('EnvironmentVariables', {'TOTALMARKER_PYTHON': '/other/python'}),
                                 ('Program', '/other/program')):
            value = copy.deepcopy(original)
            value[key] = replacement
            self.assertFalse(registration.matches(value, self.expected))

    def test_duplicate_key_partial_array_unterminated_quote_and_trailing_data_refuse(self):
        for text in ('{"Label" = "a"; "Label" = "b";}',
                     '{"ProgramArguments" = ("start";',
                     '{"Label" = "unterminated;}',
                     self.text + '{"extra" = 1;}',
                     '{"ProgramArguments" = ("start" "extra");}',
                     '{"Label" = unquoted;}',
                     '{"Label" = "x"; "bad" = __import__("os");}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    registration.parse_registration(text)

    def test_size_token_and_depth_limits(self):
        for text in (' ' * 131073, '(' * 14 + '"x"' + ')' * 14,
                     '{"a" = (' + '"x";' * 8200 + ');}'):
            with self.assertRaises(ValueError):
                registration.parse_registration(text)

    def test_quoted_delimiters_remain_literal(self):
        original = 'a;(b)c'
        value = registration.parse_registration('{"path" = "' + original + '";};')
        self.assertEqual(value['path'], original)

    def test_ambiguous_backslash_sequences_cannot_normalize_into_other_arguments(self):
        for token in (r'"a\t"', r'"a\\b"', r'"a\u0062"', r'"a\q"'):
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, 'ambiguous'):
                    registration.parse_registration('{"path" = ' + token + ';};')
