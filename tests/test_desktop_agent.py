"""Desktop LaunchAgents ownership and migration, without touching host launchd."""
import json
import plistlib
import shlex
import shutil
import stat
import unittest

from .support import prepare_fixture
from . import test_launcher_render


class DesktopAgentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = prepare_fixture(self, test_launcher_render.LauncherRenderTests)
        self.base, self.root = self.fixture.base, self.fixture.root
        self.bin = self.fixture.desktop_bin
        self.plist = self.base / 'Library/LaunchAgents/local.xplanet.desktop.plist'
        self.state = self.bin / 'launchctl.json'
        self.trace = self.base / 'launchctl.trace'
        self.renders = self.base / 'renders'
        self.fixture.environment.update(HOME=str(self.base),
                                        MOCK_LAUNCHCTL_TRACE=str(self.trace),
                                        MOCK_RENDER_TRACE=str(self.renders))
        # The renderer and every process-control command are fixture-only.
        self.fixture.mock.write_text('#!/bin/sh\nprintf "render\\n" >> "$MOCK_RENDER_TRACE"\n')
        kill = self.bin / 'kill'
        kill.write_text('#!/bin/sh\nexit 99\n')
        kill.chmod(0o700)

    def invoke(self, command):
        return self.fixture.invoke(command)

    def success(self, command):
        result = self.invoke(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def calls(self):
        return self.trace.read_text().splitlines() if self.trace.exists() else []

    def document(self, root=None):
        root = root or self.root
        return {'Label': 'local.xplanet.desktop',
                'ProgramArguments': ['/bin/zsh', str(root / 'scripts/lib/xplanet/desktop.zsh')],
                'WorkingDirectory': str(root),
                'StandardOutPath': str(root / 'logs/xplanet.log'),
                'StandardErrorPath': str(root / 'logs/xplanet-error.log')}

    def install(self, path=None, root=None):
        path = path or self.plist
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(self.document(root)))
        path.chmod(0o600)
        return path

    def register(self, path, root=None, **extra):
        self.state.write_text(json.dumps({**self.document(root), '_path': str(path),
                                          '_running': True, **extra}))

    def snapshot(self, path):
        return (path.read_bytes(), stat.S_IMODE(path.stat().st_mode), path.stat().st_ino)

    def assert_not_started_or_stopped(self):
        self.assertFalse(any(line.startswith(('bootstrap ', 'kickstart ', 'bootout '))
                             for line in self.calls()), self.calls())

    def test_start_stop_start_is_idempotent_and_has_no_login_or_respawn_trigger(self):
        self.success('start')
        original = self.snapshot(self.plist)
        self.success('start')
        self.assertEqual(self.renders.read_text().splitlines(), ['render'])
        self.success('stop')
        self.success('stop')
        self.assertFalse(self.state.exists())
        self.success('start')
        self.assertEqual(self.renders.read_text().splitlines(), ['render', 'render'])
        self.assertEqual(self.snapshot(self.plist), original)
        self.assertEqual(plistlib.loads(self.plist.read_bytes()), self.document())
        self.assertEqual(sum(line.startswith('bootstrap ') for line in self.calls()), 2)
        self.assertFalse((self.root / '.state/xplanet/desktop.plist').exists())

    def test_legacy_registration_start_preserves_and_restart_migrates(self):
        legacy = self.install(self.root / '.state/xplanet/desktop.plist')
        original = self.snapshot(legacy)
        self.register(legacy)
        job = self.state.read_bytes()
        result = self.invoke('start')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('restart', result.stderr)
        self.assertEqual(self.state.read_bytes(), job)
        self.assertFalse(self.plist.exists())
        self.assert_not_started_or_stopped()
        self.success('restart')
        self.assertEqual(json.loads(self.state.read_text())['_path'], str(self.plist))
        self.assertEqual(self.snapshot(legacy), original)
        self.assertEqual(self.renders.read_text().splitlines(), ['render'])

    def test_own_existing_plist_and_parent_permissions_are_preserved(self):
        self.install()
        self.plist.chmod(0o640)
        self.plist.parent.chmod(0o750)
        self.plist.parent.parent.chmod(0o710)
        original = self.snapshot(self.plist)
        modes = [stat.S_IMODE(p.stat().st_mode) for p in
                 (self.base, self.plist.parent.parent, self.plist.parent)]
        self.success('start')
        self.success('restart')
        self.assertEqual(self.snapshot(self.plist), original)
        self.assertEqual([stat.S_IMODE(p.stat().st_mode) for p in
                          (self.base, self.plist.parent.parent, self.plist.parent)], modes)

    def test_reusing_own_plist_recreates_missing_logs(self):
        self.install()
        original = self.snapshot(self.plist)
        logs = self.root / 'logs'
        self.assertFalse(logs.exists())
        self.success('start')
        self.assertTrue(logs.is_dir())
        self.assertEqual(stat.S_IMODE(logs.stat().st_mode), 0o700)
        self.assertEqual(self.snapshot(self.plist), original)
        self.assertEqual(self.renders.read_text().splitlines(), ['render'])

    def test_restart_missing_logs_readonly_project_preserves_running_job(self):
        self.install()
        self.register(self.plist)
        self.assertFalse((self.root / 'logs').exists())
        original, job = self.snapshot(self.plist), self.state.read_bytes()
        mode = stat.S_IMODE(self.root.stat().st_mode)
        try:
            self.root.chmod(0o500)
            result = self.invoke('restart')
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('log parent', result.stderr)
            self.assertEqual(self.state.read_bytes(), job)
            self.assertEqual(self.snapshot(self.plist), original)
            self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o500)
            self.assertFalse((self.root / 'logs').exists())
            self.assert_not_started_or_stopped()
        finally:
            self.root.chmod(mode)

    def test_stop_works_with_readonly_launchagents_directory(self):
        self.success('start')
        original = self.snapshot(self.plist)
        mode = stat.S_IMODE(self.plist.parent.stat().st_mode)
        self.trace.unlink()
        try:
            self.plist.parent.chmod(0o500)
            self.success('stop')
            self.assertFalse(self.state.exists())
            self.assertEqual(self.snapshot(self.plist), original)
            self.assertEqual(stat.S_IMODE(self.plist.parent.stat().st_mode), 0o500)
            self.assertEqual(sum(line.startswith('bootout ') for line in self.calls()), 1)
            self.assertFalse(any(line.startswith(('bootstrap ', 'kickstart ')) for line in self.calls()))
        finally:
            self.plist.parent.chmod(mode)

    def test_publication_directory_race_cannot_deposit_plist_inside_directory(self):
        helper = self.root / 'scripts/lib/xplanet/desktop-agent.zsh'
        stub = self.bin / 'race-link'
        stub.write_text('#!/bin/sh\nmkdir -m 700 "$2" || exit 98\nexec /bin/link "$@"\n')
        stub.chmod(0o700)
        text = helper.read_text()
        original = '/bin/link "$temporary" "$desktop_plist"'
        self.assertIn(original, text)
        helper.write_text(text.replace(original, shlex.quote(str(stub)) + ' "$temporary" "$desktop_plist"'))
        result = self.invoke('start')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('appeared during preparation', result.stderr)
        self.assertTrue(self.plist.is_dir())
        self.assertEqual(list(self.plist.iterdir()), [])
        self.assertEqual(list(self.plist.parent.iterdir()), [self.plist])
        self.assert_not_started_or_stopped()

    def test_other_managed_checkout_requires_explicit_restart(self):
        other = self.base / 'other checkout'
        shutil.copytree(self.root, other)
        self.install(root=other)
        self.plist.chmod(0o640)
        self.register(self.plist, root=other)
        original, job = self.snapshot(self.plist), self.state.read_bytes()
        result = self.invoke('start')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.snapshot(self.plist), original)
        self.assertEqual(self.state.read_bytes(), job)
        self.assert_not_started_or_stopped()
        self.success('restart')
        self.assertEqual(plistlib.loads(self.plist.read_bytes()), self.document())
        self.assertEqual(stat.S_IMODE(self.plist.stat().st_mode), 0o640)

    def test_foreign_or_modified_plist_is_never_overwritten(self):
        for modification in ({'Label': 'unrelated'}, {'RunAtLoad': True},
                             {'KeepAlive': False}, {'UserProperty': 'keep'},
                             {'ProgramArguments': ['/bin/sh', '/other/program']}):
            with self.subTest(modification=modification):
                self.install()
                self.plist.write_bytes(plistlib.dumps({**self.document(), **modification}))
                original = self.snapshot(self.plist)
                for command in ('start', 'restart'):
                    result = self.invoke(command)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(self.snapshot(self.plist), original)
                self.assert_not_started_or_stopped()

    def test_linked_plist_does_not_change_link_or_target(self):
        target = self.install(self.base / 'outside.plist')
        original = self.snapshot(target)
        self.plist.parent.mkdir(parents=True)
        self.plist.symlink_to(target)
        for command in ('start', 'restart'):
            self.assertEqual(self.invoke(command).returncode, 2)
            self.assertEqual(self.plist.readlink(), target)
            self.assertEqual(self.snapshot(target), original)
        self.assert_not_started_or_stopped()

    def test_writable_plist_is_refused_without_chmod(self):
        self.install()
        self.plist.chmod(0o666)
        original = self.snapshot(self.plist)
        for command in ('start', 'restart'):
            self.assertEqual(self.invoke(command).returncode, 2)
            self.assertEqual(self.snapshot(self.plist), original)
        self.assert_not_started_or_stopped()

    def test_file_in_place_of_launchagents_directory_is_preserved(self):
        self.plist.parent.parent.mkdir(mode=0o700)
        self.plist.parent.write_bytes(b'user file, not a directory')
        self.plist.parent.chmod(0o600)
        original = self.snapshot(self.plist.parent)
        for command in ('start', 'restart'):
            self.assertEqual(self.invoke(command).returncode, 2)
            self.assertEqual(self.snapshot(self.plist.parent), original)
        self.assert_not_started_or_stopped()

    def test_unsafe_directory_modes_are_refused_without_chmod(self):
        self.install()
        original = self.snapshot(self.plist)
        for directory in (self.base, self.plist.parent.parent, self.plist.parent):
            mode = stat.S_IMODE(directory.stat().st_mode)
            try:
                directory.chmod(0o777)
                for command in ('start', 'restart'):
                    self.assertEqual(self.invoke(command).returncode, 2)
                    self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o777)
                    self.assertEqual(self.snapshot(self.plist), original)
            finally:
                directory.chmod(mode)
        self.assert_not_started_or_stopped()

    def test_linked_launchagents_directory_is_refused(self):
        outside = self.base / 'outside'
        outside.mkdir()
        sentinel = outside / 'keep'
        sentinel.write_bytes(b'untouched')
        self.plist.parent.parent.mkdir()
        self.plist.parent.symlink_to(outside, target_is_directory=True)
        original = self.snapshot(sentinel)
        for command in ('start', 'restart'):
            self.assertEqual(self.invoke(command).returncode, 2)
            self.assertEqual(self.plist.parent.readlink(), outside)
            self.assertEqual(list(outside.iterdir()), [sentinel])
            self.assertEqual(self.snapshot(sentinel), original)
        self.assert_not_started_or_stopped()

    def test_foreign_loaded_job_is_not_kickstarted_or_stopped(self):
        self.install()
        original = self.snapshot(self.plist)
        for modification in ({'ProgramArguments': ['/bin/sh', '/unrelated']},
                             {'_path': str(self.base / 'foreign.plist')},
                             {'WorkingDirectory': str(self.base)}):
            with self.subTest(modification=modification):
                self.register(self.plist, **modification)
                job = self.state.read_bytes()
                for command in ('start', 'stop', 'restart'):
                    self.assertEqual(self.invoke(command).returncode, 2)
                    self.assertEqual(self.state.read_bytes(), job)
                    self.assertEqual(self.snapshot(self.plist), original)
        self.assert_not_started_or_stopped()

    def test_foreign_bootstrap_winner_is_not_kickstarted(self):
        stub = self.bin / 'launchctl'
        text = stub.read_text()
        text = text.replace("if args[0]=='bootstrap':", """if args[0]=='bootstrap':
    doc=plistlib.loads(Path(args[2]).read_bytes())
    doc.update(_path=args[2], ProgramArguments=['/bin/sh', '/foreign'])
    state.write_text(json.dumps(doc))
    raise SystemExit(5)
if False:""")
        stub.write_text(text)
        result = self.invoke('start')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(any(line.startswith('bootstrap ') for line in self.calls()))
        self.assertFalse(any(line.startswith(('kickstart ', 'bootout ')) for line in self.calls()))
        self.assertEqual(json.loads(self.state.read_text())['ProgramArguments'], ['/bin/sh', '/foreign'])

    def test_restart_configuration_preflight_preserves_running_job(self):
        self.success('start')
        original, job = self.snapshot(self.plist), self.state.read_bytes()
        self.trace.unlink()
        selector = self.root / 'config/desktop.scene'
        selector.write_text('v1 ' + 'a' * 64 + '\n')
        result = self.invoke('restart')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('selected scene', result.stderr)
        self.assertEqual(self.state.read_bytes(), job)
        self.assertEqual(self.snapshot(self.plist), original)
        self.assert_not_started_or_stopped()

    def test_native_lifecycle_never_invokes_python(self):
        attempted = self.base / 'python-attempted'
        for name in ('python', 'python3'):
            stub = self.bin / name
            stub.write_text('#!/bin/sh\ntouch "' + str(attempted) + '"\nexit 97\n')
            stub.chmod(0o700)
        for command in ('start', 'start', 'restart', 'stop'):
            self.success(command)
        self.assertFalse(attempted.exists())
