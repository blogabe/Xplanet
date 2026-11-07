"""Portable configurator contracts without Textual or real desktop processes."""
from tests.support import prepare_fixture
from configurator.resources import identity
import asyncio
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from configurator.model import ROOT, SAMPLE, View, parse_saved_view, utc_date, number
from configurator.workspace import Workspace, renderer_path, save_view, open_view, configuration_issues


class ModelTests(unittest.TestCase):
    def test_supported_arguments_are_finite_file_preview_inputs(self):
        args = View(45, -80, 'orthographic').arguments()
        self.assertIn('orthographic', args)
        self.assertNotIn('-fork', args)
        self.assertNotIn('-prev_command', args)

    def test_validation_rejects_nonfinite_out_of_range_and_unknown_projection(self):
        for view in (View(float('nan')), View(91), View(0, float('inf')), View(0, 181), View(projection='random')):
            with self.subTest(view=view), self.assertRaises(ValueError):
                view.validate()

    def test_native_definition_quotes_binary_and_has_one_camera_strategy(self):
        text = View(-90, 180).definition('/Applications/a renderer')
        self.assertIn("XPLANET_BIN='/Applications/a renderer'", text)
        self.assertNotIn('localtime', text)
        self.assertNotIn('origin=', text)


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.binary = Path(sys.executable).resolve()

    def test_save_preserves_sample_bytes_and_does_not_apply(self):
        destination = self.root / 'view with spaces'
        self.assertEqual(save_view(destination, View(10, 20), self.binary), destination)
        self.assertEqual((destination / 'xp.conf').read_bytes(), SAMPLE.read_bytes())
        self.assertEqual(sorted(x.name for x in destination.iterdir()), ['xp.conf', 'xp.def'])
        self.assertIn('XPLANET_LATITUDE=10', (destination / 'xp.def').read_text())

    def test_existing_directory_files_or_links_are_never_overwritten(self):
        original = self.root / 'existing'
        original.mkdir()
        sentinel = original / 'xp.conf'
        sentinel.write_text('user content')
        link = self.root / 'link'
        link.symlink_to(original)
        for destination in (original, sentinel, link):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                save_view(destination, View(), self.binary)
        self.assertEqual(sentinel.read_text(), 'user content')

    def test_invalid_destination_does_not_create_parents(self):
        for destination in (Path('relative'), self.root / 'missing' / 'view', self.root / 'bad\nname'):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                save_view(destination, View(), self.binary)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_parent_is_refused(self):
        (self.root / 'alias').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            save_view(self.root / 'alias' / 'new', View(), self.binary)
        self.assertFalse((self.root / 'new').exists())

    def test_invalid_camera_and_renderer_do_not_write(self):
        for view, renderer in ((View(100), self.binary), (View(), '/nonexistent/renderer')):
            with self.assertRaises(ValueError):
                save_view(self.root / 'new', view, renderer)
        self.assertEqual(list(self.root.iterdir()), [])


class PreviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.binary = Path(self.tmp.name).resolve() / 'fixture renderer'

    def renderer(self, body):
        self.binary.write_text('#!' + sys.executable + '\n' + body)
        self.binary.chmod(0o700)
        return self.binary

    async def test_preview_uses_own_workdir_and_finite_output(self):
        binary = self.renderer('import sys,pathlib,json\na=sys.argv[1:]\nassert a[a.index("-num_times")+1]=="1"\nassert "-fork" not in a\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n')
        image = await self.workspace.preview(View(), binary)
        self.assertTrue(image.is_relative_to(self.workspace.root))
        self.assertIsNone(self.workspace.process)
        self.workspace.close()
        self.assertFalse(image.exists())

    async def test_timeout_stops_process_and_retains_no_success(self):
        binary = self.renderer('import time\ntime.sleep(30)\n')
        with self.assertRaisesRegex(ValueError, 'exceeded'):
            await self.workspace.preview(View(), binary, timeout=.05)
        self.assertIsNone(self.workspace.image)
        self.assertIsNone(self.workspace.process)

    async def test_cancel_stops_process(self):
        binary = self.renderer('import time\ntime.sleep(30)\n')
        task = asyncio.create_task(self.workspace.preview(View(), binary))
        while self.workspace.process is None:
            await asyncio.sleep(.001)
        pid = self.workspace.process.pid
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertIsNone(self.workspace.process)

    async def test_preview_stops_descendants_after_leader_exit_and_timeout(self):
        import signal
        for finish in (True, False):
            with self.subTest(success=finish):
                pid_file=Path(self.tmp.name)/'child.pid'
                pid_file.unlink(missing_ok=True)
                heartbeat=Path(self.tmp.name)/'heartbeat'
                heartbeat.unlink(missing_ok=True)
                child=None
                binary=self.renderer(
                    'import os,signal,time,sys,pathlib\n'
                    'if os.fork()==0:\n'
                    ' signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                    f' pathlib.Path({str(heartbeat)!r}).touch()\n'
                    f' pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n'
                    ' while True:\n'
                    f'  with pathlib.Path({str(heartbeat)!r}).open("ab") as stream:stream.write(b"x")\n'
                    '  time.sleep(.01)\n'
                    f'while not pathlib.Path({str(pid_file)!r}).exists():time.sleep(.001)\n'+
                    ('a=sys.argv;pathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n'
                     if finish else 'time.sleep(30)\n'))
                try:
                    if finish:
                        started=asyncio.get_running_loop().time()
                        await self.workspace.preview(View(),binary)
                        self.assertLess(asyncio.get_running_loop().time()-started,6,'leader exit must not wait for a descendant-held stdout pipe')
                    else:
                        with self.assertRaisesRegex(ValueError,'exceeded'):
                            await self.workspace.preview(View(),binary,timeout=.5)
                    child=int(pid_file.read_text())
                    # Observe actual work rather than PID disappearance: dead
                    # orphaned children may briefly remain zombies on Linux.
                    size=heartbeat.stat().st_size
                    await asyncio.sleep(.15)
                    self.assertEqual(heartbeat.stat().st_size,size,
                                     'renderer child continued writing after finite preview cleanup')
                    self.assertIsNone(self.workspace.process)
                finally:
                    if child is None and pid_file.exists():child=int(pid_file.read_text())
                    if child is not None:
                        try:os.kill(child,signal.SIGKILL)
                        except ProcessLookupError:pass

    async def test_explicit_stop_during_pending_preview_is_a_render_failure_not_waiter_crash(self):
        binary=self.renderer('import time;time.sleep(30)\n')
        task=asyncio.create_task(self.workspace.preview(View(),binary))
        while self.workspace.process is None:await asyncio.sleep(.001)
        await self.workspace.stop()
        with self.assertRaisesRegex(ValueError,'Xplanet failed'):await task
        self.assertIsNone(self.workspace.process);self.assertIsNone(self.workspace.image)

    async def test_nonzero_missing_output_and_invalid_png_are_failures(self):
        for body in ('import sys\nprint("fixture failure")\nsys.exit(7)', 'pass',
                     'import pathlib,sys\na=sys.argv;pathlib.Path(a[a.index("-output")+1]).write_text("not PNG")'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                await self.workspace.preview(View(), self.renderer(body))
        self.assertIsNone(self.workspace.image)


@unittest.skipUnless(Path('/bin/zsh').exists(), 'zsh command boundary')
class LauncherTests(unittest.TestCase):
    def test_help_and_noninteractive_config_need_no_dependencies_or_setup(self):
        from tests.support import copy_launcher
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            scripts = root / 'scripts'
            scripts.mkdir()
            copy_launcher(scripts / 'xplanet.sh')
            shutil.copy2(ROOT / 'scripts/run-configurator', scripts / 'run-configurator')
            guide = root / 'docs/configurator/user-guide.md'
            guide.parent.mkdir(parents=True)
            shutil.copy2(ROOT / 'docs/configurator/user-guide.md', guide)
            unexpected = root / 'unexpected-runtime'
            runner = scripts / 'run-totalmarker'
            runner.write_text('#!/bin/sh\ntouch '+shlex.quote(str(unexpected))+'\nexit 91\n')
            runner.chmod(0o700)
            environment = {'PATH': '/usr/bin:/bin', 'HOME': str(root),
                           'PYTHONDONTWRITEBYTECODE': '1'}
            for arguments, status in ((['config', '--help'], 0), (['config','--guide'],0), (['config'], 2)):
                with self.subTest(arguments=arguments):
                    done = subprocess.run([str(scripts / 'xplanet.sh'), *arguments],
                                          cwd=root, env=environment,
                                          capture_output=True, text=True)
                    self.assertEqual(done.returncode, status, done.stderr)
                    self.assertFalse(unexpected.exists(), 'help/non-TTY entry must not invoke a runtime')
            self.assertIn('interactive terminal', done.stderr)

    def test_configurator_helper_propagates_result_without_parsing_output(self):
        root = ROOT
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'run-configurator'
            for status, expected in ((0, 'saved'), (3, 'cancelled'), (4, 'unavailable'), (9, 'failed')):
                script.write_text('#!/bin/sh\nexit ' + str(status) + '\n');script.chmod(0o700)
                command = ('script_dir=' + shlex.quote(directory) + '; source ' +
                           shlex.quote(str(root / 'scripts/lib/xplanet/configurator.zsh')) +
                           '; configure_xplanet; print -r -- "$?:$configuration_result"')
                done = subprocess.run(['/bin/zsh', '-c', command], capture_output=True, text=True)
                self.assertEqual(done.stdout.strip(), f'{status}:{expected}')
            script.write_text('#!/bin/sh\nexit 0\n')
            for option, expected in (('--prepare', 'prepared'), ('--help', 'info'), ('--guide','info')):
                command = ('script_dir=' + shlex.quote(directory) + '; source ' +
                           shlex.quote(str(root / 'scripts/lib/xplanet/configurator.zsh')) +
                           '; configure_xplanet ' + option + '; print -r -- "$configuration_result"')
                done = subprocess.run(['/bin/zsh', '-c', command], capture_output=True, text=True)
                self.assertEqual(done.stdout.strip(), expected)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'scripts/configurator').mkdir(parents=True)
        (self.root / 'scripts/configurator/requirements.txt').write_text('textual==8.2.8 --hash=sha256:fixture\n')

    def test_check_missing_runtime_is_read_only(self):
        from configurator.runtime import ready
        self.assertFalse(ready(self.root))
        self.assertFalse((self.root / '.state').exists())

    def test_preparation_is_isolated_hash_checked_and_explicit(self):
        from configurator.runtime import prepare, lock_digest
        with patch('configurator.runtime.venv.EnvBuilder') as builder, patch('configurator.runtime.subprocess.run') as run:
            prepare(self.root)
        args = run.call_args.args[0]
        self.assertIn(str(self.root / '.state/configurator/venv/bin/python'), args)
        self.assertIn('--require-hashes', args)
        self.assertIn('--isolated', args)
        self.assertIn('--no-cache-dir', args)
        self.assertEqual((self.root / '.state/configurator/lock.sha256').read_text().strip(), lock_digest(self.root))
        builder.return_value.create.assert_called_once()

    def test_existing_runtime_or_symlink_is_not_replaced(self):
        from configurator.runtime import prepare
        location = self.root / '.state/configurator'
        location.mkdir(parents=True)
        (location / 'venv').mkdir()
        with patch('configurator.runtime.subprocess.run') as run, self.assertRaises(ValueError):
            prepare(self.root)
        run.assert_not_called()
        shutil.rmtree(self.root / '.state')
        outside = self.root / 'outside';outside.mkdir()
        (self.root / '.state').symlink_to(outside)
        with self.assertRaises(ValueError):
            prepare(self.root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_failed_install_has_no_ready_marker(self):
        from configurator.runtime import prepare
        with patch('configurator.runtime.venv.EnvBuilder'), patch('configurator.runtime.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'fixture')):
            with self.assertRaises(subprocess.CalledProcessError):
                prepare(self.root)
        self.assertFalse((self.root / '.state/configurator/lock.sha256').exists())

    def test_stale_lock_or_wrong_dependency_version_is_not_ready(self):
        from configurator.runtime import ready, lock_digest
        location = self.root / '.state/configurator';location.mkdir(parents=True)
        (location / 'lock.sha256').write_text('old')
        self.assertFalse(ready(self.root))
        (location / 'lock.sha256').write_text(lock_digest(self.root))
        with patch('configurator.runtime.version', return_value='0.0.0'):
            self.assertFalse(ready(self.root))


class ReopenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'saved with spaces'
        save_view(self.source, View(25, -80, 'orthographic'), sys.executable)
        self.original = {p.name: p.read_bytes() for p in self.source.iterdir()}

    def test_roundtrip_load_and_revise_to_new_copy_preserves_original(self):
        document = open_view(self.source)
        self.assertEqual(document.view, View(25, -80, 'orthographic'))
        self.assertEqual(document.config, SAMPLE.read_bytes())
        destination = self.root / 'revised copy'
        save_view(destination, View(10, 20), sys.executable, config_bytes=document.config)
        self.assertEqual(open_view(destination).view, View(10, 20))
        self.assertEqual({p.name: p.read_bytes() for p in self.source.iterdir()}, self.original)

    def test_renderer_path_is_literal_and_need_not_be_executed_or_present(self):
        renderer = '/not-installed/a name with \' and $(touch sentinel)'
        for renderer in (renderer, '/not-installed/texture\u2028name'):
            document = parse_saved_view(View().definition(renderer).encode(), SAMPLE.read_bytes())
            self.assertEqual(document.saved_renderer, renderer)
            self.assertEqual(document.view, View())

    def test_shell_injection_duplicates_unknowns_and_reordering_are_refused(self):
        marker = self.root / 'must-not-run'
        original = self.original['xp.def']
        changes = [original + ('touch ' + str(marker) + '\n').encode(),
                   original.replace(b'XPLANET_BIN=', ('XPLANET_BIN=$(touch ' + str(marker) + ') #').encode(), 1),
                   original + b'XPLANET_LATITUDE=0\n',
                   original.replace(b'EARTH_MAP_PRE=stock', b'EARTH_MAP_PRE=other/other'),
                   original.replace(b'XPLANET_GEOMETRY=1920x1080', b'XPLANET_GEOMETRY=invalid'),
                   original.replace(b'XPLANET_LATITUDE=25', b'XPLANET_LATITUDE=nan'),
                   original.replace(b'XPLANET_LONGITUDE=-80', b'XPLANET_LONGITUDE=181'),
                   original.replace(b'XPLANET_PROJECTION=orthographic', b'XPLANET_PROJECTION=random'),
                   b'\n'.join(original.splitlines()[::-1]),
                   original.replace(b'\n', b'\r\n'), b'\xff', b'']
        for definition in changes:
            with self.subTest(definition=definition), self.assertRaises(ValueError):
                parse_saved_view(definition, self.original['xp.conf'])
        self.assertFalse(marker.exists())

    def test_body_edits_and_partial_or_missing_pair_are_refused(self):
        for content in (b'[earth]\nmap=other.jpg\n', self.original['xp.conf'] + b'# extra\n'):
            with self.assertRaises(ValueError):
                parse_saved_view(self.original['xp.def'], content)
        (self.source / 'xp.conf').unlink()
        with self.assertRaises(OSError):
            open_view(self.source)

    def test_symlink_directory_files_and_fifo_are_refused(self):
        loop = self.root / 'loop';loop.symlink_to(loop)
        with self.assertRaises(ValueError):
            open_view(loop)
        alias = self.root / 'alias';alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            open_view(alias)
        config = self.source / 'xp.conf';config.unlink();config.symlink_to(SAMPLE)
        with self.assertRaises((ValueError, OSError)):
            open_view(self.source)
        config.unlink();os.mkfifo(config)
        with self.assertRaises(ValueError):
            open_view(self.source)

    def test_oversized_inputs_are_bounded(self):
        (self.source / 'xp.def').write_bytes(b'x' * 16385)
        with self.assertRaisesRegex(ValueError, '16 KiB'):
            open_view(self.source)

    def test_source_change_during_read_is_detected(self):
        real_read = os.read
        def changing_read(fd, size):
            result = real_read(fd, size)
            (self.source / 'xp.conf').write_bytes(self.original['xp.conf'] + b'\n')
            return result
        with patch('configurator.workspace.os.read', side_effect=changing_read):
            with self.assertRaisesRegex(ValueError, 'changed while opening'):
                open_view(self.source)

    def test_loaded_snapshot_does_not_overwrite_later_source_edits(self):
        document = open_view(self.source)
        (self.source / 'xp.conf').write_bytes(b'user edits made after open')
        save_view(self.root / 'copy', document.view, sys.executable, config_bytes=document.config)
        self.assertEqual((self.source / 'xp.conf').read_bytes(), b'user edits made after open')
        self.assertEqual((self.root / 'copy/xp.conf').read_bytes(), self.original['xp.conf'])

    def test_relative_and_control_character_source_paths_are_refused(self):
        for source in ('relative', '/', str(self.source) + '\n'):
            with self.assertRaises(ValueError):
                open_view(source)


class CameraTimeTests(unittest.TestCase):
    def test_map_and_space_emit_distinct_coherent_camera_arguments(self):
        mapped = View(25, -80, observer='moon', framing='fov', fov=5).arguments()
        self.assertIn('-projection', mapped)
        self.assertIn('-latitude', mapped)
        for flag in ('-origin', '-fov', '-radius'):
            self.assertNotIn(flag, mapped)
        for observer, expected in (('moon', 'moon'), ('sun', 'sun'), ('opposite_sun', '-sun')):
            args = View(projection='space', observer=observer).arguments()
            self.assertEqual(args[args.index('-origin') + 1], expected)
            for flag in ('-projection', '-latitude', '-longitude'):
                self.assertNotIn(flag, args)
        geographic = View(25, -80, 'space').arguments()
        self.assertIn('-latitude', geographic)
        self.assertNotIn('-origin', geographic)
        self.assertIn('geographic 25, -80', View(25, -80, 'space').summary())
        self.assertNotIn('2000-01-01', View().summary())

    def test_space_framing_is_exclusive(self):
        for framing in ('radius', 'fov'):
            args = View(projection='space', framing=framing, radius=40, fov=5).arguments()
            self.assertIn('-' + framing, args)
            self.assertNotIn('-' + ('fov' if framing == 'radius' else 'radius'), args)

    def test_fixed_utc_is_explicit_while_now_does_not_emit_a_date(self):
        value = '2024-02-29T23:59:59Z'
        args = View(time_mode='fixed', utc=value).arguments()
        self.assertEqual(args[args.index('-date') + 1], '20240229.235959')
        self.assertNotIn('-date', View(time_mode='now', utc=value).arguments())
        self.assertEqual(utc_date(value).utcoffset().total_seconds(), 0)

    def test_invalid_calendar_timezone_and_studio_boundaries_are_rejected(self):
        for value in ('2023-02-29T12:00:00Z', '1900-02-29T12:00:00Z', '2024-01-01',
                      '2024-01-01T00:00:00+01:00', '2024-1-01T00:00:00Z',
                      '2024-01-01T24:00:00Z', '2024-01-01T00:00:60Z',
                      '1799-12-31T23:59:59Z', '2201-01-01T00:00:00Z'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                View(utc=value).validate()
        for value in ('1800-01-01T00:00:00Z', '2200-12-31T23:59:59Z', '2000-02-29T00:00:00Z'):
            View(time_mode='fixed', utc=value).validate()

    def test_invalid_framing_and_retained_values_cannot_be_silently_discarded(self):
        for kwargs in ({'radius':0}, {'radius':101}, {'fov':180}, {'fov':float('nan')},
                       {'observer':'random'}, {'framing':'both'}, {'time_mode':'local'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                View(**kwargs).arguments()

    def test_current_roundtrip_preserves_full_precision_and_inactive_preferences(self):
        for projection in ('rectangular', 'orthographic', 'space'):
            for observer in ('geographic', 'moon', 'sun', 'opposite_sun'):
                for framing in ('radius', 'fov'):
                    for clock in ('now', 'fixed'):
                        view = View(23.1234567890123, -80.9876543210987, projection, observer,
                                    framing, 43.1234567890123, 4.9876543210987, clock, '2024-02-29T23:59:59Z')
                        document = parse_saved_view(view.definition('/trusted/xplanet').encode(), SAMPLE.read_bytes())
                        self.assertEqual(document.view, view)
                        self.assertEqual(document.config, SAMPLE.read_bytes())
        self.assertEqual(float(number(23.1234567890123)), 23.1234567890123)

    def test_legacy_pairs_remain_readable_and_save_as_v3_without_losing_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve();source = root / 'legacy';source.mkdir()
            view = View(25, -80, 'orthographic',geometry='800x600')
            definition = view.legacy_definition('/old/xplanet').encode()
            (source / 'xp.def').write_bytes(definition);(source / 'xp.conf').write_bytes(SAMPLE.read_bytes())
            document = open_view(source)
            self.assertEqual(document.view, view)
            save_view(root / 'v2-copy', document.view, sys.executable, config_bytes=document.config)
            self.assertEqual(open_view(root / 'v2-copy').view, view)
            self.assertEqual((source / 'xp.def').read_bytes(), definition)
            self.assertIn(b'scene v17', (root / 'v2-copy/xp.def').read_bytes())
        with self.assertRaises(ValueError):
            View(observer='moon').legacy_definition('/trusted/xplanet')

    def test_versioned_format_rejects_ambiguous_mode_and_executable_payloads(self):
        definition = View(projection='space', observer='moon', time_mode='fixed').definition('/trusted/xplanet')
        for changed in (definition.replace('scene v17', 'scene v999'),
                        definition.replace('XPLANET_SCENE_MODE=space', 'XPLANET_SCENE_MODE=map'),
                        definition.replace('XPLANET_PROJECTION=\n', 'XPLANET_PROJECTION=orthographic\n'),
                        definition + 'XPLANET_OBSERVER=sun\n',
                        definition.replace('XPLANET_UTC=2000-01-01T12:00:00Z', 'XPLANET_UTC=$(echo unsafe)')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                parse_saved_view(changed.encode(), SAMPLE.read_bytes())
        with self.assertRaises(ValueError):
            parse_saved_view(View(geometry='800x600').legacy_definition('/trusted/xplanet').replace('XPLANET_PROJECTION=rectangular', 'XPLANET_PROJECTION=space').encode(), SAMPLE.read_bytes())


class ConfigurationHealthTests(unittest.TestCase):
    def test_health_and_validation_share_blocking_rules(self):
        values = {name:getattr(View(), name) for name in View.__dataclass_fields__}
        values['radius'] = 'bad retained text';values['utc'] = 'not UTC'
        view = View.from_fields(values)
        blocking = [issue for issue in view.issues() if issue.severity == 'blocking']
        self.assertEqual({issue.field for issue in blocking}, {'radius', 'utc'})
        with self.assertRaises(ValueError) as error:
            view.validate()
        for issue in blocking:
            self.assertIn(issue.message, str(error.exception))
        self.assertNotIn('radius', view.active_fields())

    def test_warnings_are_not_validation_failures_and_asset_unknowns_are_explicit(self):
        view = View(projection='space', observer='opposite_sun', time_mode='fixed')
        view.validate()
        issues = configuration_issues(view, sys.executable)
        self.assertFalse(any(issue.severity=='blocking' for issue in issues))
        self.assertTrue(any(issue.severity=='warning' and issue.field=='utc' for issue in issues))
        self.assertTrue(any(issue.severity=='warning' and issue.field=='observer' for issue in issues))
        self.assertTrue(any(issue.field=='assets' and 'unverified' in issue.message for issue in issues))

    def test_preflight_never_executes_renderer_and_rejects_unknown_body(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'renderer';marker = Path(directory) / 'marker'
            binary.write_text('#!/bin/sh\ntouch ' + str(marker) + '\n');binary.chmod(0o700)
            self.assertFalse(any(i.severity=='blocking' for i in configuration_issues(View(),binary)))
            self.assertFalse(marker.exists())
            self.assertTrue(any(i.severity=='blocking' and i.field=='assets'
                                for i in configuration_issues(View(),binary,b'unreviewed config')))
            self.assertTrue(any(i.severity=='blocking' and i.field=='renderer'
                                for i in configuration_issues(View(),'/missing/xplanet')))


class PreviewRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.workspace = Workspace();self.addCleanup(self.workspace.close)
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.binary = Path(self.temp.name).resolve() / 'renderer'
        self.good()

    def good(self):
        self.binary.write_text('#!' + sys.executable + '\nimport pathlib,sys\na=sys.argv\nprint("fixture diagnostic")\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n');self.binary.chmod(0o700)

    async def test_failure_timeout_and_preflight_keep_success_and_clean_failed_work(self):
        original = await self.workspace.preview(View(), self.binary)
        self.binary.write_text('#!' + sys.executable + '\nimport sys\nsys.exit(7)\n')
        with self.assertRaisesRegex(ValueError, 'retained'):
            await self.workspace.preview(View(10), self.binary)
        self.assertEqual(self.workspace.image,original);self.assertTrue(original.exists())
        with self.assertRaises(ValueError):
            await self.workspace.preview(View(), '/missing/renderer')
        self.binary.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(30)\n')
        with self.assertRaisesRegex(ValueError, 'exceeded'):
            await self.workspace.preview(View(),self.binary,timeout=.05)
        self.assertEqual(self.workspace.image,original)
        self.assertEqual(len(list(self.workspace.root.iterdir())),1)
        self.assertEqual(self.workspace.last_outcome,'failed')
        self.assertFalse(self.workspace.busy)

    async def test_cancel_preserves_success_and_reaps_process(self):
        original = await self.workspace.preview(View(),self.binary)
        self.binary.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(30)\n')
        task = asyncio.create_task(self.workspace.preview(View(10),self.binary))
        while self.workspace.process is None:await asyncio.sleep(.001)
        pid = self.workspace.process.pid;task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)
        self.assertEqual(self.workspace.image,original);self.assertTrue(original.exists())
        self.assertEqual(self.workspace.last_outcome,'cancelled')
        self.assertEqual(len(list(self.workspace.root.iterdir())),1)

    async def test_two_successful_snapshots_compare_and_oldest_is_removed(self):
        first = await self.workspace.preview(View(),self.binary)
        second = await self.workspace.preview(View(10),self.binary)
        self.assertEqual(self.workspace.previous.path,first)
        self.assertEqual(self.workspace.latest.path,second)
        self.assertIn('fixture diagnostic',self.workspace.latest.diagnostics)
        third = await self.workspace.preview(View(20),self.binary)
        self.assertFalse(first.exists());self.assertTrue(second.exists());self.assertTrue(third.exists())
        self.assertEqual(len(list(self.workspace.root.iterdir())),2)
        self.assertTrue(self.workspace.latest.matches(View(20,observer='moon'),self.binary,SAMPLE.read_bytes()))
        self.assertFalse(self.workspace.latest.matches(View(30),self.binary,SAMPLE.read_bytes()))
        self.assertFalse(self.workspace.latest.matches(View(20),self.binary,b'changed'))
        self.assertTrue(self.workspace.latest.completed_utc.endswith('+00:00'))

    async def test_launch_error_is_actionable_and_does_not_replace_success(self):
        original = await self.workspace.preview(View(),self.binary)
        self.binary.write_text('not an executable format')
        with self.assertRaisesRegex(ValueError,'binary architecture'):
            await self.workspace.preview(View(10),self.binary)
        self.assertEqual(self.workspace.image,original)
        self.assertIsNone(self.workspace.process);self.assertFalse(self.workspace.busy)

    async def test_workspace_write_error_is_actionable_and_preserves_success(self):
        original = await self.workspace.preview(View(),self.binary)
        with patch('configurator.workspace.tempfile.mkdtemp',side_effect=PermissionError('read only fixture')):
            with self.assertRaisesRegex(ValueError,'permissions and free space'):
                await self.workspace.preview(View(10),self.binary)
        self.assertEqual(self.workspace.image,original)


class AppearanceTests(unittest.TestCase):
    def test_all_bundled_months_have_explicit_native_references_and_roundtrip(self):
        from configurator.model import MAP_FAMILIES, MONTHS, ROOT, recognized_body
        for family in MAP_FAMILIES:
            for month in MONTHS:
                view = View(map_family=family, month=month, night='lights2002', twilight=12, grid='15', label='utc')
                for relative in view.resource_paths():
                    self.assertTrue((ROOT / relative).is_file(), relative)
                self.assertTrue(recognized_body(view.body()))
                reopened = parse_saved_view(view.definition('/trusted/xplanet').encode(), view.body())
                self.assertEqual(reopened.view, view)
                self.assertIn('-gmtlabel', reopened.view.arguments())
                if family != 'stock':
                    self.assertIn(f'{family}.2004{month}.3x5400x2700.png'.encode(), view.body())

    def test_v2_pairs_reopen_with_appearance_defaults(self):
        view = View(projection='space', observer='moon', time_mode='fixed',geometry='800x600')
        definition = view.definition('/trusted/xplanet', version=2).encode()
        document = parse_saved_view(definition, SAMPLE.read_bytes())
        self.assertEqual(document.view, view)
        self.assertEqual(document.view.map_family, 'stock')
        self.assertNotIn('XPLANET_MAP_FAMILY', definition.decode())

    def test_appearance_rejects_invalid_and_inactive_values(self):
        for options in ({'month':'13'}, {'map_family':'../evil'}, {'night':'arbitrary.png'},
                        {'twilight':float('nan')}, {'twilight':-1}, {'twilight':91},
                        {'twilight':1.5}, {'grid':'0'}, {'label':'$(command)'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                View(**options).body()
        for value in (0, 6, 90):
            View(twilight=value).validate()

    def test_appearance_body_rejects_extra_or_mismatched_config(self):
        from configurator.model import recognized_body
        view = View(map_family='world', month='07', grid='30')
        definition = view.definition('/trusted/xplanet').encode()
        for body in (view.body()+b'prev_command=bad\n', view.body().replace(b'grid1=3',b'grid1=0'),
                     view.body().replace(b'200407',b'200408'), view.body().replace(b'map=maps/',b'map=/outside/')):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_saved_view(definition,body)
        self.assertFalse(recognized_body(view.body()+b'# altered\n'))

    def test_reopen_records_old_asset_root_without_adopting_it(self):
        from configurator.model import ROOT
        view = View(map_family='world.topo', month='12')
        definition = view.definition('/untrusted/not-adopted', asset_root='/old checkout with spaces').encode()
        doc = parse_saved_view(definition,view.body())
        self.assertEqual(doc.view,view)
        self.assertNotIn(b'/old checkout',doc.config)
        self.assertIn(str(ROOT),doc.view.definition(sys.executable))
        self.assertNotIn('/old checkout',doc.view.definition(sys.executable))

    def test_missing_bundled_asset_blocks_without_renderer_execution(self):
        with tempfile.TemporaryDirectory() as temporary, patch('configurator.workspace.ROOT',Path(temporary)):
            issues = configuration_issues(View(map_family='world',month='06'),sys.executable)
            self.assertTrue(any(i.severity=='blocking' and 'world.200406' in i.message for i in issues))

    def test_save_revised_appearance_from_old_snapshot_does_not_copy_old_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = save_view(root/'old',View(),sys.executable)
            original = (source/'xp.conf').read_bytes()
            doc = open_view(source)
            view = View(map_family='world.topo.bathy',month='04',night='lights2002',grid='10',label='utc',twilight=0)
            destination = save_view(root/'revised',view,sys.executable,config_bytes=doc.config)
            self.assertEqual(open_view(destination).view,view)
            self.assertEqual((destination/'xp.conf').read_bytes(),view.body())
            self.assertEqual((source/'xp.conf').read_bytes(),original)
            self.assertEqual(sorted(p.name for p in destination.iterdir()),['xp.conf','xp.def'])

    def test_appearance_changes_mark_retained_preview_stale(self):
        from configurator.workspace import PreviewSnapshot
        import hashlib
        base = View()
        snap = PreviewSnapshot(Path('/tmp/unused.png'),base,Path(sys.executable).resolve(),base.render_digest(),'test','',binary_identity=identity(Path(sys.executable).resolve()))
        self.assertTrue(snap.matches(base,sys.executable,SAMPLE.read_bytes()))
        for view in (View(month='05'),View(grid='15'),View(label='utc'),View(twilight=20),View(night='lights2002')):
            self.assertEqual(snap.matches(view,sys.executable,SAMPLE.read_bytes()),view==View(month='05'))


class AppearancePreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_generates_new_body_and_passes_checkout_searchdir_as_single_arg(self):
        from configurator.model import ROOT
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); binary=root/'renderer'
            binary.write_text('#!'+sys.executable+'\nimport sys,pathlib\na=sys.argv[1:]\nassert '+repr(str(ROOT))+' in a\nbody=pathlib.Path(a[a.index("-config")+1]).read_text()\nassert "200409" in body and "grid1=6" in body\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n')
            binary.chmod(0o700)
            workspace=Workspace()
            try:
                view=View(map_family='world',month='09',grid='15')
                image=await workspace.preview(view,binary,config_bytes=SAMPLE.read_bytes())
                self.assertTrue(image.exists())
                self.assertTrue(workspace.latest.matches(view,binary,SAMPLE.read_bytes()))
            finally:
                workspace.close()


class DraftHistoryTests(unittest.TestCase):
    def base(self):
        return {'latitude':'0','month':'01','projection':'rectangular','renderer':'/local/xplanet'}

    def test_invalid_edit_run_is_grouped_and_roundtrips_without_validation(self):
        from configurator.history import DraftHistory
        h=DraftHistory(self.base()); edited=self.base()
        for text in ('-', '-2', '-wrong'):
            edited['latitude']=text;h.record(edited,group='latitude')
        self.assertTrue(h.dirty);self.assertEqual(h.undo()['latitude'],'0')
        self.assertFalse(h.dirty);self.assertEqual(h.redo()['latitude'],'-wrong')

    def test_new_edit_after_undo_discards_only_redo_branch(self):
        from configurator.history import DraftHistory
        h=DraftHistory(self.base());a=self.base();a['latitude']='10';h.record(a)
        b=dict(a,month='08');h.record(b);self.assertEqual(h.undo(),a)
        c=dict(a,month='12');h.record(c)
        self.assertFalse(h.can_redo);self.assertEqual(h.undo(),a)
        self.assertEqual(h.redo(),c)

    def test_numeric_formatting_is_undoable_but_not_dirty(self):
        from configurator.history import DraftHistory
        h=DraftHistory(self.base());h.record(dict(self.base(),latitude='-0.000'))
        self.assertTrue(h.can_undo);self.assertFalse(h.dirty)
        self.assertEqual(h.changes(),[]);self.assertEqual(h.undo()['latitude'],'0')

    def test_inactive_settings_and_renderer_are_real_changes(self):
        from configurator.history import DraftHistory
        h=DraftHistory(self.base());h.record(dict(self.base(),month='12',renderer='/different/xplanet'))
        self.assertEqual({field for field,_,_ in h.changes()},{'month','renderer'})

    def test_history_bound_keeps_baseline_even_when_oldest_undo_is_evicted(self):
        from configurator.history import DraftHistory
        h=DraftHistory(self.base(),limit=2)
        for latitude in ('1','2','3','4'):h.record(dict(self.base(),latitude=latitude))
        self.assertEqual(h.undo()['latitude'],'3');self.assertEqual(h.undo()['latitude'],'2')
        self.assertFalse(h.can_undo);self.assertTrue(h.dirty)
        self.assertEqual(h.baseline['latitude'],'0')

    def test_snapshot_copies_noop_boundaries_and_reset(self):
        from configurator.history import DraftHistory
        base=self.base();h=DraftHistory(base);base['month']='03'
        self.assertEqual(h.current['month'],'01');h.current['month']='12'
        self.assertEqual(h.undo()['month'],'01');self.assertEqual(h.redo()['month'],'01')
        h.record(h.current);self.assertFalse(h.can_undo)
        h.record(base);h.reset(base)
        self.assertFalse(h.dirty or h.can_undo or h.can_redo)
        with self.assertRaises(ValueError):h.record({'latitude':'5'})
        with self.assertRaises(ValueError):DraftHistory(base,limit=0)

    def test_blur_boundary_separates_edits_in_the_same_field(self):
        from configurator.history import DraftHistory
        h=DraftHistory(self.base());h.record(dict(self.base(),latitude='1'),group='latitude')
        h.break_group();h.record(dict(self.base(),latitude='12'),group='latitude')
        self.assertEqual(h.undo()['latitude'],'1');self.assertEqual(h.undo()['latitude'],'0')


class GeographyTests(unittest.TestCase):
    def view(self,**extra):
        return View(places='on',places_text='51.5 -0.1 "London"\n40.7 -74 "New York"\n',
                    routes='on',routes_text='51.5 -0.1 40.7 -74\n',**extra)

    def test_rows_are_bounded_native_surface_data_without_extra_options(self):
        from configurator.geography import validate_rows
        self.assertEqual(validate_rows('90 180 "Pole"\n-90 -180 "South"',True),2)
        self.assertEqual(validate_rows('0 170 0 -170',False),1)
        for text,places in [('91 0 "bad"',True),('0 inf "bad"',True),('0 0 "x" image=/private/file',True),
                            ('0 0 "x" timezone=UTC',True),('0 0 "a\\b"',True),('0 0 ""',True),
                            ('0 0 "'+('é'*41)+'"',True),('0 0 1 1 spacing=0',False),
                            ('0 0 91 1',False),('0 0 1e999 1',False),('0 0 1',False),
                            ('0 0 "a"\r',True),('0 0 "a"\n'*33,True),(' '*8193,False)]:
            with self.subTest(text=text),self.assertRaises(ValueError):validate_rows(text,places)
        self.assertEqual(validate_rows('0 0 "$(uname) # literal"',True),1)

    def test_native_annotation_roundtrip_preserves_text_order_and_precision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();view=self.view(place_size=18,route_width=4)
            source=save_view(root/'source',view,sys.executable)
            doc=open_view(source);self.assertEqual(doc.view,view)
            self.assertEqual(sorted(p.name for p in source.iterdir()),['places.markers','routes.arcs','xp.conf','xp.def'])
            before={p.name:p.read_bytes() for p in source.iterdir()}
            edited=View(places_text=doc.view.places_text,routes_text=doc.view.routes_text)
            copy=save_view(root/'copy',edited,sys.executable,config_bytes=doc.config)
            self.assertEqual(open_view(copy).view,edited)
            self.assertNotIn(b'marker_file=',(copy/'xp.conf').read_bytes())
            self.assertEqual((copy/'places.markers').read_bytes(),before['places.markers'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})

    def test_missing_invalid_and_symlinked_optional_files_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();source=save_view(root/'source',self.view(),sys.executable)
            places=source/'places.markers';original=places.read_bytes();places.unlink()
            with self.assertRaises(OSError):open_view(source)
            target=root/'outside';target.write_bytes(original);places.symlink_to(target)
            with self.assertRaises(OSError):open_view(source)
            places.unlink();os.mkfifo(places)
            with self.assertRaises(ValueError):open_view(source)
            places.unlink()
            for content in (original+b'0 0 "extra" image=bad\n',b'X'*17000,b'\xff'):
                places.write_bytes(content)
                with self.assertRaises(ValueError):open_view(source)

    def test_optional_file_change_during_read_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=save_view(Path(temporary).resolve()/'source',self.view(),sys.executable)
            original=os.read
            def read(fd,size):
                value=original(fd,size)
                if value.startswith(b'# Xplanet configurator surface places'):
                    (source/'places.markers').write_bytes(value+b'0 0 "changed"')
                return value
            with patch('configurator.workspace.os.read',side_effect=read),self.assertRaisesRegex(ValueError,'changed while opening'):
                open_view(source)

    def test_auxiliary_write_failure_leaves_no_partial_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();original=os.open
            def opened(name,*args,**kwargs):
                if name=='routes.arcs':raise PermissionError('fixture write failure')
                return original(name,*args,**kwargs)
            with patch('configurator.workspace.os.open',side_effect=opened),self.assertRaises(PermissionError):
                save_view(root/'failed',self.view(),sys.executable)
            self.assertEqual(list(root.iterdir()),[])

    def test_prior_formats_keep_defaults_and_reject_geographic_downconversion(self):
        view=View(map_family='world',month='08',label='utc',geometry='800x600')
        doc=parse_saved_view(view.definition('/trusted/xplanet',version=3).encode(),view.body())
        self.assertEqual(doc.view,view);self.assertEqual(doc.view.places_text,'')
        for version in (2,3):
            with self.assertRaises(ValueError):self.view().definition('/trusted/xplanet',version=version)

    def test_inactive_invalid_rows_and_invalid_style_are_blocking(self):
        for options in ({'places_text':'wrong'}, {'routes_text':'wrong'}, {'place_size':9},
                        {'place_size':14.5},{'route_width':0},{'route_width':2.5},{'route_color':'unknown'}):
            with self.subTest(options=options),self.assertRaises(ValueError):View(**options).validate()

    def test_active_auxiliary_content_affects_preview_digest_but_inactive_content_does_not(self):
        from dataclasses import replace
        view=self.view();self.assertNotEqual(view.render_digest(),replace(view,places_text='0 0 "Different"').render_digest())
        disabled=replace(view,places='off',routes='off')
        self.assertEqual(disabled.render_digest(),View().render_digest())
        self.assertNotEqual(view.render_digest(),replace(view,routes_text='0 0 20 20').render_digest())

    def test_native_file_reference_cannot_redirect_loader_outside_scene(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();source=save_view(root/'source',self.view(),sys.executable)
            definition=source/'xp.def';definition.write_bytes(definition.read_bytes().replace(b'XPLANET_PLACES_FILE=places.markers',b'XPLANET_PLACES_FILE=/outside/not-read'))
            original=os.open;seen=[]
            def opened(name,*args,**kwargs):
                seen.append(str(name));return original(name,*args,**kwargs)
            with patch('configurator.workspace.os.open',side_effect=opened),self.assertRaises(ValueError):open_view(source)
            self.assertNotIn('/outside/not-read',seen)


class EarthLayerTests(unittest.TestCase):
    def test_layer_combinations_roundtrip_and_use_only_whitelisted_resources(self):
        from configurator.model import recognized_body,ROOT
        for relief in ('off','gebco'):
            for shadow in ('night','shade'):
                for specular in ('off','bundled'):
                    for clouds in ('off','snapshot2011'):
                        view=View(relief=relief,relief_scale=2.5,relief_shadow=shadow,relief_shade=20,
                                  specular=specular,clouds=clouds,cloud_gamma=1.4,cloud_threshold=110)
                        self.assertTrue(recognized_body(view.body()))
                        doc=parse_saved_view(view.definition('/trusted/xplanet').encode(),view.body())
                        self.assertEqual(doc.view,view)
                        for path in view.resource_paths():self.assertTrue((ROOT/path).is_file())
                        self.assertEqual(b'bump_map=' in view.body(),relief!='off')
                        self.assertEqual(b'bump_shade=' in view.body(),relief!='off' and shadow=='shade')
                        self.assertEqual(b'cloud_map=' in view.body(),clouds!='off')

    def test_layer_bounds_are_finite_and_inactive_values_still_validate(self):
        for options in ({'relief':'other'},{'clouds':'current'},{'specular':'other'},
                        {'relief_scale':0},{'relief_scale':5.1},{'cloud_gamma':float('inf')},
                        {'cloud_gamma':0},{'cloud_threshold':256},{'cloud_threshold':90.5},
                        {'relief_shade':-1},{'relief_shade':30.5},{'relief_shadow':'other'}):
            with self.subTest(options=options),self.assertRaises(ValueError):View(**options).validate()
        for options in ({'relief_scale':.1},{'relief_scale':5},{'cloud_gamma':.1},
                        {'cloud_gamma':5},{'cloud_threshold':0},{'cloud_threshold':255},
                        {'relief_shade':0},{'relief_shade':100}):View(**options).validate()

    def test_native_v4_annotations_reopen_and_revise_without_changing_source(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();old=View(places='on',places_text='0 0 "Center"',geometry='800x600')
            source=save_view(root/'old-v4',old,sys.executable)
            (source/'xp.def').write_text(old.definition(sys.executable,version=4))
            before={p.name:p.read_bytes() for p in source.iterdir()}
            doc=open_view(source);self.assertEqual(doc.view,old)
            changed=replace(doc.view,clouds='snapshot2011',relief='gebco')
            target=save_view(root/'revised',changed,sys.executable,config_bytes=doc.config)
            self.assertEqual(open_view(target).view,changed)
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})
            for version in (2,3,4):
                with self.assertRaises(ValueError):changed.definition(sys.executable,version=version)

    def test_historical_cloud_warning_does_not_claim_current_access_or_refresh(self):
        issues=configuration_issues(View(clouds='snapshot2011',relief='gebco',specular='bundled'),sys.executable)
        self.assertFalse(any(i.severity=='blocking' for i in issues))
        self.assertTrue(any(i.field=='clouds' and '2011' in i.message and i.severity=='warning' for i in issues))
        self.assertTrue(any(i.field=='layers' and 'memory' in i.message for i in issues))
        self.assertTrue(any(i.field=='assets' and 'clouds_26Aug2011' in i.message for i in issues))

    def test_missing_layer_and_redirected_native_reference_fail_closed(self):
        from configurator.model import recognized_body
        view=View(clouds='snapshot2011')
        with tempfile.TemporaryDirectory() as temporary,patch('configurator.workspace.ROOT',Path(temporary)):
            self.assertTrue(any(i.severity=='blocking' and 'Missing bundled' in i.message for i in configuration_issues(view,sys.executable)))
        wrong=view.body().replace(b'cloud_map=maps/clouds/clouds_26Aug2011_2048.jpeg',b'cloud_map=/outside/not-read')
        self.assertFalse(recognized_body(wrong))
        with self.assertRaises(ValueError):parse_saved_view(view.definition('/trusted/xplanet').encode(),wrong)

    def test_disabled_layer_parameters_are_preserved_without_affecting_active_render(self):
        from dataclasses import replace
        base=View();inactive=View(relief_scale=4,relief_shadow='shade',relief_shade=80,cloud_gamma=2,cloud_threshold=140)
        self.assertEqual(base.render_digest(),inactive.render_digest())
        enabled=replace(inactive,clouds='snapshot2011')
        self.assertNotEqual(enabled.render_digest(),base.render_digest())
        self.assertNotEqual(enabled.render_digest(),replace(enabled,cloud_gamma=1).render_digest())
        self.assertEqual(parse_saved_view(inactive.definition('/trusted/xplanet').encode(),inactive.body()).view,inactive)


from tests.configurator.support_cloud import CloudCaptureFixture

class CloudCaptureTests(CloudCaptureFixture, unittest.TestCase):



    def test_capture_is_read_only_and_provenance_excludes_source_secrets_and_paths(self):
        from totalmarker.paths import RootFS
        from totalmarker.http import Fetcher
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(RootFS,'write',side_effect=AssertionError('write')),patch.object(RootFS,'lock',side_effect=AssertionError('lock')),patch.object(Fetcher,'fetch',side_effect=AssertionError('network')):
            frozen=self.capture()
        self.assertEqual(frozen.image,self.image);self.assertEqual(frozen.freshness(now=1700000040),'unknown')
        for value in (b'PrivateUser',b'PrivatePassword',b'Private error details',str(self.root).encode(),b'https://'):
            self.assertNotIn(value,frozen.provenance)
        self.assertEqual(before,{str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(frozen.metadata['last_outcome'],'failed')

    def test_pending_publication_never_replays_or_discards_journal(self):
        journal=self.root/'.state/totalmarker/pending.json';journal.write_bytes(b'PRIVATE JOURNAL DO NOT READ')
        with self.assertRaisesRegex(ValueError,'Pending TotalMarker publication'):self.capture()
        self.assertEqual(journal.read_bytes(),b'PRIVATE JOURNAL DO NOT READ')
        journal.unlink();other=self.root/'.state/totalmarker/storm-pending.json';other.write_bytes(b'UNRELATED PENDING INTENT')
        with self.assertRaisesRegex(ValueError,'Pending TotalMarker publication'):self.capture()
        self.assertEqual(other.read_bytes(),b'UNRELATED PENDING INTENT')

    def test_hash_mismatch_missing_state_and_malformed_state_fail_closed(self):
        self.record['image_sha256']='0'*64;self.save_state()
        with self.assertRaisesRegex(ValueError,'do not match'):self.capture()
        for raw in (b'not json',b'['*2000+b']'*2000):
            self.state_path.write_bytes(raw)
            with self.assertRaises(ValueError):self.capture()
        self.state_path.unlink()
        with self.assertRaises(ValueError):self.capture()

    def test_bounded_retry_accepts_only_a_new_coherent_published_generation(self):
        import hashlib
        from configurator import cloud_capture as cc
        original=cc.read_stable;changed=False
        payload=b'additional JPEG comment';new=self.image[:2]+b'\xff\xfe'+(len(payload)+2).to_bytes(2,'big')+payload+self.image[2:]
        def read(fs,path,limit):
            nonlocal changed
            if str(path)=='images/clouds-2048.jpg' and not changed:
                changed=True;self.image_path.write_bytes(new)
                self.record['image_sha256']=self.record['source_image_sha256']=hashlib.sha256(new).hexdigest();self.save_state()
            return original(fs,path,limit)
        with patch.object(cc,'read_stable',side_effect=read):frozen=self.capture()
        self.assertEqual(frozen.image,new)

    def test_unsafe_nonregular_and_unbounded_source_files_are_refused(self):
        self.image_path.unlink();outside=self.root.parent/(self.root.name+'-outside')
        outside.write_bytes(b'not read');self.addCleanup(outside.unlink)
        self.image_path.symlink_to(outside)
        with self.assertRaises(ValueError):self.capture()
        self.image_path.unlink();os.mkfifo(self.image_path)
        with self.assertRaises(ValueError):self.capture()
        self.image_path.unlink()
        with self.image_path.open('wb') as stream:stream.truncate(33*1024*1024)
        with self.assertRaises(ValueError):self.capture()

    def test_forged_or_deep_provenance_is_normalized_and_rejected(self):
        import json
        from configurator.cloud_capture import FrozenCloud,json_bytes
        frozen=self.capture();meta=frozen.metadata;meta['private_path']='/outside'
        with self.assertRaises(ValueError):FrozenCloud(frozen.image,json_bytes(meta))
        with self.assertRaises(ValueError):FrozenCloud(frozen.image,b'['*2000+b']'*2000)
        with self.assertRaises(ValueError):FrozenCloud(b'not jpeg',frozen.provenance)

    def test_snapshot_save_reopen_and_fixed_utc_policy_preserve_bytes(self):
        from configurator.cloud_capture import IMAGE_FILE,META_FILE
        frozen=self.capture();view=View(clouds='captured',capture_id=frozen.identity,label='utc')
        target=save_view(self.root/'view',view,sys.executable,capture=frozen)
        doc=open_view(target);self.assertEqual(doc.view,view);self.assertEqual(doc.capture,frozen)
        self.assertIn(b'cloud_map=cloud-capture.jpg',doc.config)
        from dataclasses import replace
        historical=replace(view,time_mode='fixed')
        self.assertNotIn(b'cloud_map=',historical.body());self.assertIn('-gmtlabel',historical.arguments())
        self.assertNotIn(b'updatelabel',historical.body())
        other=save_view(self.root/'historical',historical,sys.executable,capture=frozen)
        self.assertEqual((other/IMAGE_FILE).read_bytes(),frozen.image)
        self.assertEqual(open_view(other).view,historical)
        self.assertIn(b'cloud_map=',View(clouds='snapshot2011',time_mode='fixed').body())
        (target/META_FILE).write_bytes(b'{}')
        with self.assertRaises(ValueError):open_view(target)

    def test_missing_capture_blocks_now_but_fixed_retained_intent_can_be_saved(self):
        current=View(clouds='captured')
        with self.assertRaises(ValueError):save_view(self.root/'no-data',current,sys.executable)
        fixed=View(clouds='captured',time_mode='fixed')
        target=save_view(self.root/'fixed-intent',fixed,sys.executable)
        self.assertEqual(open_view(target).view,fixed)
        self.assertIsNone(open_view(target).capture)

    def test_known_image_creation_time_and_shared_freshness_policy(self):
        import hashlib
        from datetime import datetime,timezone
        from configurator.cloud_capture import capture_existing
        created=datetime(2026,11,3,12,tzinfo=timezone.utc)
        payload=b'EarthDesk Cloud Image Created Tue Nov 03 12:00:00 UTC 2026'
        raw=self.image[:2]+b'\xff\xfe'+(len(payload)+2).to_bytes(2,'big')+payload+self.image[2:]
        self.image_path.write_bytes(raw);self.record.update(image_sha256=hashlib.sha256(raw).hexdigest(),source_image_sha256=hashlib.sha256(raw).hexdigest(),source_created_at=created.timestamp())
        self.save_state();frozen=capture_existing(self.root,now=created.timestamp()+60)
        self.assertEqual(frozen.freshness(created.timestamp()+60),'current')
        self.assertEqual(frozen.freshness(created.timestamp()+100000),'stale')


class CloudCaptureWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_timeout_and_cancellation_reap_only_private_worker(self):
        original=asyncio.create_subprocess_exec
        spawned=[]
        async def slow(*args,**kwargs):
            process=await original(sys.executable,'-c','import time;time.sleep(30)',**kwargs)
            spawned.append(process);return process
        workspace=Workspace();self.addCleanup(workspace.close)
        with patch('configurator.workspace.asyncio.create_subprocess_exec',side_effect=slow):
            with self.assertRaisesRegex(ValueError,'wait budget'):await workspace.capture_cloud('/unused','unused',timeout=.05)
            self.assertIsNotNone(spawned[-1].returncode);self.assertFalse(workspace.busy)
            task=asyncio.create_task(workspace.capture_cloud('/unused','unused'))
            while workspace.process is None:await asyncio.sleep(.001)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertIsNotNone(spawned[-1].returncode);self.assertFalse(workspace.busy)
        self.assertEqual(workspace.captures,{})
        self.assertFalse(list(workspace.root.glob('capture-*')))

    async def test_capture_history_has_an_explicit_budget_without_eviction(self):
        from configurator.cloud_capture import FrozenCloud,json_bytes
        from configurator.model import ROOT
        import hashlib
        data=(ROOT/'maps/clouds/clouds_26Aug2011_2048.jpeg').read_bytes()
        meta={'schema':1,'product':'clouds','image_sha256':hashlib.sha256(data).hexdigest(),'width':2048,'height':1024,
              'source_time_origin':'unavailable','warning_seconds':100,'last_outcome':None,
              'captured_at':1700000000,'source_created_at':None,'last_check_at':None,'last_attempt_at':None,
              'last_success_at':None,'last_publication_at':None}
        frozen=FrozenCloud(data,json_bytes(meta));workspace=Workspace();self.addCleanup(workspace.close)
        identity=workspace.register_capture(frozen);self.assertIs(workspace.capture_for(View(capture_id=identity)),frozen)
        changed=dict(meta,captured_at=1700000001);second=FrozenCloud(data,json_bytes(changed))
        with patch('configurator.workspace.CAPTURE_BUDGET',len(data)+1),self.assertRaisesRegex(ValueError,'128 MiB'):
            workspace.register_capture(second)
        self.assertEqual(list(workspace.captures),[identity])
        workspace.reset_captures(frozen);self.assertEqual(len(workspace.captures),1)
        workspace.reset_captures();self.assertEqual(workspace.captures,{})


class NamedSceneTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.library=self.root/'scenes'

    def test_multiple_named_pairs_and_all_owned_assets_stay_associated(self):
        from configurator.library import save_named,list_scenes
        fixture=prepare_fixture(self,CloudCaptureFixture)
        frozen=fixture.capture();view=View(places='on',places_text='0 0 "Center"',routes='on',routes_text='0 0 30 30',clouds='captured',capture_id=frozen.identity)
        target=save_named(self.library/'summer.conf',view,sys.executable,capture=frozen)
        save_named(self.library/'winter.conf',View(30),sys.executable)
        doc=open_view(target);self.assertEqual(doc.view,view);self.assertEqual(doc.capture,frozen);self.assertTrue(doc.named_source)
        self.assertEqual(open_view(self.library/'summer.def').view,view)
        self.assertEqual({p.name for p in list_scenes(self.library)},{'summer.conf','winter.conf'})
        self.assertIn(b'marker_file=summer.places.markers',doc.config)
        self.assertIn(b'cloud_map=summer.cloud-capture.jpg',doc.config)
        self.assertEqual((self.library/'summer.cloud-capture.jpg').read_bytes(),frozen.image)
        self.assertEqual(configuration_issues(view,sys.executable,doc.config,frozen)[0].severity,'info')

    def test_legacy_directory_and_even_dot_conf_directory_remain_readable(self):
        from configurator.library import save_named
        legacy=save_view(self.root/'old.conf',View(35,places='on',places_text='0 0 "Here"'),sys.executable)
        before={p.name:p.read_bytes() for p in legacy.iterdir()};doc=open_view(legacy)
        self.assertFalse(doc.named_source)
        target=save_named(self.library/'copy.conf',doc.view,sys.executable,config_bytes=doc.config)
        self.assertEqual(open_view(target).view,doc.view)
        self.assertEqual(before,{p.name:p.read_bytes() for p in legacy.iterdir()})

    def test_case_alias_and_unrelated_prefix_collision_never_overwrite(self):
        from configurator.library import save_named
        save_named(self.library/'Summer.conf',View(),sys.executable)
        before={p.name:p.read_bytes() for p in self.library.iterdir()}
        with self.assertRaises(ValueError):save_named(self.library/'summer.conf',View(40),sys.executable)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.library.iterdir()})
        (self.library/'notes.private').write_text('keep')
        with self.assertRaises(ValueError):save_named(self.library/'notes.conf',View(),sys.executable)
        self.assertEqual((self.library/'notes.private').read_text(),'keep')

    def test_bad_names_links_and_incomplete_saves_fail_safely(self):
        from configurator.library import save_named,list_scenes
        for name in ('.hidden.conf','bad name.conf','a.b.conf','x;bad.conf','x'*49+'.conf'):
            with self.subTest(name=name),self.assertRaises(ValueError):save_named(self.library/name,View(),sys.executable)
        self.assertFalse(self.library.exists())
        target=save_named(self.library/'okay.conf',View(),sys.executable)
        marker=self.library/'.saving-okay';marker.mkdir()
        with self.assertRaisesRegex(ValueError,'unfinished'):open_view(target)
        self.assertEqual(list_scenes(self.library),[])
        with self.assertRaises(ValueError):save_named(self.library/'Okay.conf',View(),sys.executable)
        self.assertTrue(marker.is_dir())
        alias=self.root/'alias';alias.symlink_to(self.library,target_is_directory=True)
        with self.assertRaises(ValueError):save_named(alias/'other.conf',View(),sys.executable)

    def test_partial_write_cleanup_keeps_other_scenes_and_removes_only_its_files(self):
        from configurator.library import save_named
        keep=save_named(self.library/'keep.conf',View(10),sys.executable);before=keep.read_bytes()
        original=os.open
        def opened(name,*args,**kwargs):
            if name=='failed.def':raise PermissionError('fixture')
            return original(name,*args,**kwargs)
        with patch('configurator.library.os.open',side_effect=opened),self.assertRaises(PermissionError):
            save_named(self.library/'failed.conf',View(places='on',places_text='0 0 "X"'),sys.executable)
        self.assertEqual(keep.read_bytes(),before)
        self.assertFalse(any(p.name.startswith('failed.') or p.name=='.saving-failed' for p in self.library.iterdir()))

    def test_associated_file_reference_cannot_select_another_scene(self):
        from configurator.library import save_named
        target=save_named(self.library/'one.conf',View(places='on',places_text='0 0 "One"'),sys.executable)
        save_named(self.library/'two.conf',View(places='on',places_text='1 1 "Two"'),sys.executable)
        definition=target.with_suffix('.def');definition.write_bytes(definition.read_bytes().replace(b'one.places.markers',b'two.places.markers'))
        with self.assertRaises(ValueError):open_view(target)

    def test_concurrent_case_alias_writers_have_exactly_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from configurator.library import save_named,list_scenes
        self.library.mkdir()
        def writer(name):
            try:return save_named(self.library/(name+'.conf'),View(),sys.executable)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(writer,['same','SAME']))
        self.assertEqual(sum(p is not None for p in results),1);self.assertEqual(len(list_scenes(self.library)),1)


from dataclasses import replace

class CompositionTests(unittest.TestCase):
    def test_solar_strategy_never_passes_conflicting_longitude(self):
        for projection in ('rectangular','orthographic','space'):
            view=View(20,50,projection,longitude_mode='solar',solar_hour=18,distance=4)
            args=view.arguments()
            self.assertIn('-localtime',args);self.assertNotIn('-longitude',args)
            self.assertEqual(args[args.index('-localtime')+1],'18')
            self.assertEqual('-range' in args,projection=='space')
        view=View(projection='space',observer='moon',longitude_mode='solar',distance=4)
        for option in ('-localtime','-longitude','-range'):self.assertNotIn(option,view.arguments())
        self.assertNotIn('solar_hour',view.active_fields())
        self.assertEqual(View().arguments()[View().arguments().index('-longitude')+1],'0')

    def test_orientation_and_distance_are_space_only_and_roundtrip(self):
        from configurator.model import parse_saved_view
        view=View(projection='space',longitude_mode='solar',solar_hour=6.5,distance=3,north='orbit',rotation=-35)
        args=view.arguments();self.assertEqual(args[args.index('-north')+1],'orbit')
        self.assertEqual(args[args.index('-rotate')+1],'-35')
        self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),view.body()).view,view)
        inactive=replace(view,projection='rectangular',observer='moon')
        self.assertEqual(parse_saved_view(inactive.definition('/renderer').encode(),inactive.body()).view,inactive)
        for option in ('-range','-north','-rotate'):self.assertNotIn(option,inactive.arguments())
        with self.assertRaises(ValueError):view.definition('/renderer',version=6)

    def test_composition_validation_including_inactive_and_old_v6(self):
        from configurator.model import parse_saved_view
        for values in ({'distance':1},{'distance':float('inf')},{'solar_hour':24.1},{'rotation':181},{'north':'path'},{'longitude_mode':'both'}):
            with self.subTest(values=values),self.assertRaises(ValueError):View(**values).validate()
        for values in ({'distance':1.01},{'solar_hour':0},{'solar_hour':24},{'rotation':-180}):View(**values).validate()
        old=View(places='on',places_text='0 0 "Old"',geometry='800x600')
        doc=parse_saved_view(old.definition('/renderer',version=6).encode(),old.body(),places=old.auxiliary_files()['places.markers'])
        self.assertEqual(doc.view,old)


class PriorVersionAssetTests(unittest.TestCase):
    def test_v6_capture_and_geography_open_after_new_camera_version(self):
        from configurator.cloud_capture import FrozenCloud,json_bytes
        from configurator.model import ROOT
        import hashlib
        data=(ROOT/'maps/clouds/clouds_26Aug2011_2048.jpeg').read_bytes()
        meta={'schema':1,'product':'clouds','image_sha256':hashlib.sha256(data).hexdigest(),'width':2048,'height':1024,
              'source_time_origin':'unavailable','warning_seconds':100,'last_outcome':None,
              'captured_at':1700000000,'source_created_at':None,'last_check_at':None,'last_attempt_at':None,
              'last_success_at':None,'last_publication_at':None}
        frozen=FrozenCloud(data,json_bytes(meta))
        view=View(clouds='captured',capture_id=frozen.identity,places='on',places_text='0 0 "Legacy"',geometry='800x600')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();(root/'xp.def').write_text(view.definition(sys.executable,version=6))
            (root/'xp.conf').write_bytes(view.body())
            for name,data in {**view.auxiliary_files(),**frozen.files()}.items():(root/name).write_bytes(data)
            self.assertEqual(open_view(root).view,view)
            self.assertEqual(open_view(root).capture,frozen)


class ConfiguratorAuditTests(unittest.TestCase):
    def test_failed_named_save_retains_concurrently_edited_output_and_guard(self):
        from configurator.library import save_named,list_scenes
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();original=os.open
            def opened(name,*args,**kwargs):
                if name=='scene.def':
                    (root/'scene.conf').write_text('external change preserved')
                    raise PermissionError('fixture')
                return original(name,*args,**kwargs)
            with patch('configurator.library.os.open',side_effect=opened),self.assertRaises(PermissionError):
                save_named(root/'scene.conf',View(),sys.executable)
            self.assertEqual((root/'scene.conf').read_text(),'external change preserved')
            self.assertTrue((root/'.saving-scene').is_dir());self.assertEqual(list_scenes(root),[])

    def test_failed_legacy_save_retains_concurrently_replaced_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();target=root/'scene';original=os.open
            def opened(name,*args,**kwargs):
                if name=='xp.def':
                    (target/'xp.conf').unlink();(target/'xp.conf').write_text('replacement preserved')
                    raise PermissionError('fixture')
                return original(name,*args,**kwargs)
            with patch('configurator.fileio.os.open',side_effect=opened),self.assertRaises(PermissionError):
                save_view(target,View(),sys.executable)
            self.assertEqual((target/'xp.conf').read_text(),'replacement preserved')

    def test_capture_repr_is_bounded_and_does_not_dump_image_or_provenance(self):
        fixture=prepare_fixture(self,CloudCaptureFixture)
        frozen=fixture.capture();self.assertEqual(repr(frozen),'FrozenCloud()')
        self.assertNotIn('source_created_at',repr(frozen))

    def test_runtime_preparation_refuses_symlink_marker_before_creating_environment(self):
        from configurator.runtime import prepare,ready
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();location=root/'.state/configurator';location.mkdir(parents=True)
            outside=root/'keep';outside.write_text('keep');(location/'lock.sha256').symlink_to(outside)
            with patch('configurator.runtime.venv.EnvBuilder') as builder,self.assertRaisesRegex(ValueError,'symlink'):
                prepare(root)
            builder.assert_not_called();self.assertEqual(outside.read_text(),'keep')
            self.assertFalse((location/'venv').exists());self.assertFalse(ready(root))

    def test_named_save_respects_final_library_capacity_before_publishing(self):
        from configurator.library import save_named,list_scenes
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            for index in range(3):(root/f'keep-{index}').write_text('preserved')
            with patch('configurator.library.MAX_ENTRIES',4):
                with self.assertRaisesRegex(ValueError,'no room'):
                    save_named(root/'too-full.conf',View(),sys.executable)
                self.assertEqual(sorted(p.name for p in root.iterdir()),['keep-0','keep-1','keep-2'])
                self.assertEqual(list_scenes(root),[])
                # A scene exactly filling the final bound remains browsable.
                (root/'keep-2').unlink()
                save_named(root/'fits.conf',View(),sys.executable)
                self.assertEqual(list_scenes(root),[root/'fits.conf'])

    def test_library_candidate_removed_during_browse_is_skipped(self):
        from configurator.library import save_named,list_scenes
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();save_named(root/'scene.conf',View(),sys.executable)
            original=os.stat
            def inspected(name,*args,**kwargs):
                if name=='scene.def':raise FileNotFoundError('fixture race')
                return original(name,*args,**kwargs)
            with patch('configurator.library.os.stat',side_effect=inspected):self.assertEqual(list_scenes(root),[])


class PlanetaryTests(unittest.TestCase):
    def test_target_camera_matrix_roundtrips_native_v8(self):
        from configurator.model import parse_saved_view,recognized_body
        for target in ('earth','moon','mars'):
            for projection in ('rectangular','orthographic','space'):
                for observer in ('geographic','earth','moon','sun','opposite_sun'):
                    view=View(target=target,projection=projection,observer=observer,longitude_mode='solar',solar_hour=6,rotation=25,grid='30')
                    with self.subTest(target=target,projection=projection,observer=observer):
                        if projection=='space' and target==observer:
                            with self.assertRaises(ValueError):view.arguments()
                            continue
                        self.assertEqual(view.arguments()[1],target)
                        self.assertTrue(recognized_body(view.body()))
                        self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),view.body()).view,view)

    def test_earth_layers_and_geography_are_retained_but_not_rendered_on_other_targets(self):
        from configurator.model import PLANET_MAPS
        view=View(target='mars',places='on',places_text='0 0 "Earth only"',routes='on',routes_text='0 0 10 10',
                  clouds='captured',map_family='world',relief='gebco',night='lights2002',specular='bundled')
        self.assertFalse(view.uses_capture());self.assertIsNone(view.capture_problem(None))
        self.assertEqual(view.resource_paths(),[Path(PLANET_MAPS['mars'])])
        self.assertNotIn(b'marker_file',view.body());self.assertNotIn(b'cloud_map',view.body());self.assertNotIn(b'bump_map',view.body())
        self.assertEqual(view.auxiliary_files(active_only=True),{})
        for key in ('clouds','relief','places_text','map_family'):self.assertNotIn(key,view.active_fields())
        self.assertEqual(view.render_digest(),View(target='mars').render_digest())
        with tempfile.TemporaryDirectory() as temp:
            from configurator.library import save_named
            path=save_named(Path(temp).resolve()/'mars.conf',view,sys.executable)
            self.assertEqual(open_view(path).view,view)
            self.assertEqual(open_view(path).view.places_text,'0 0 "Earth only"')
        self.assertIsNotNone(replace(view,target='earth').capture_problem(None))

    def test_retained_frozen_cloud_survives_planet_save_without_entering_render_body(self):
        fixture=prepare_fixture(self,CloudCaptureFixture);frozen=fixture.capture()
        view=View(target='moon',clouds='captured',capture_id=frozen.identity)
        with tempfile.TemporaryDirectory() as temp:
            from configurator.library import save_named
            path=save_named(Path(temp).resolve()/'moon.conf',view,sys.executable,capture=frozen)
            doc=open_view(path);self.assertEqual(doc.capture,frozen);self.assertEqual(doc.view,view)
            self.assertNotIn(b'cloud_map',doc.config);self.assertFalse(doc.view.uses_capture())
            self.assertTrue(replace(doc.view,target='earth').uses_capture())
            self.assertFalse(replace(doc.view,target='earth',time_mode='fixed').uses_capture())

    def test_prior_v7_camera_and_v8_unknown_content_are_checked(self):
        from configurator.model import parse_saved_view,recognized_body
        old=View(projection='space',longitude_mode='solar',solar_hour=6,rotation=30,geometry='800x600')
        self.assertEqual(parse_saved_view(old.definition('/renderer',version=7).encode(),old.body()).view,old)
        with self.assertRaises(ValueError):View(target='mars').definition('/renderer',version=7)
        for target in ('sun','triton','../mars'):
            with self.subTest(target=target),self.assertRaises(ValueError):View(target=target).validate()
        view=View(target='moon');definition=view.definition('/renderer').encode()
        for data in (view.body()+b'[earth]\nmap=evil.jpg\n',view.body().replace(b'moon-4k.png',b'other.png')):
            self.assertFalse(recognized_body(data))
            with self.assertRaises(ValueError):parse_saved_view(definition,data)
        with self.assertRaises(ValueError):View(target='mars',places_text='unsafe native options').validate()


class StockSceneTests(unittest.TestCase):
    def test_shipped_presets_are_valid_snapshots_and_copy_without_source_changes(self):
        from configurator.library import list_scenes,save_named
        from configurator.model import ROOT
        library=ROOT/'scripts/configurator/samples/scenes';paths=list_scenes(library)
        self.assertEqual({p.stem for p in paths},{'earth-solar-dawn','earth-september','earth-from-moon','moon-from-earth','jupiter-cloudtops','saturn-rings','europa-from-jupiter','mars-from-phobos','saturn-from-titan','pluto-from-charon','jupiter-inner-enlarged','saturn-inner-enlarged','pluto-charon-system','jupiter-orbit-guides','saturn-orbit-guides','pluto-charon-guides','jupiter-europa-enlarged','saturn-titan-enlarged','mars-from-deimos','jupiter-from-io','jupiter-from-europa','saturn-from-iapetus','uranus-from-miranda','earthrise-lunar-orbit'})
        before={p.name:p.read_bytes() for p in library.iterdir()}
        with tempfile.TemporaryDirectory() as temp:
            for path in paths:
                doc=open_view(path);self.assertEqual(doc.view.target,{'moon-from-earth':'moon','jupiter-cloudtops':'jupiter','saturn-rings':'saturn','europa-from-jupiter':'europa','mars-from-phobos':'mars','saturn-from-titan':'saturn','pluto-from-charon':'pluto','jupiter-inner-enlarged':'jupiter','saturn-inner-enlarged':'saturn','pluto-charon-system':'pluto','jupiter-orbit-guides':'jupiter','saturn-orbit-guides':'saturn','pluto-charon-guides':'pluto','jupiter-europa-enlarged':'jupiter','saturn-titan-enlarged':'saturn','mars-from-deimos':'mars','jupiter-from-io':'jupiter','jupiter-from-europa':'jupiter','saturn-from-iapetus':'saturn','uranus-from-miranda':'uranus'}.get(path.stem,'earth'));self.assertFalse(doc.view.capture_id)
                self.assertEqual(doc.saved_renderer,'/path/to/xplanet')
                target=save_named(Path(temp).resolve()/(path.stem+'-copy.conf'),doc.view,sys.executable,config_bytes=doc.config)
                self.assertEqual(open_view(target).view,doc.view)
                self.assertEqual(open_view(target).saved_renderer,str(Path(sys.executable).resolve()))
        self.assertEqual(before,{p.name:p.read_bytes() for p in library.iterdir()})


class MajorPlanetTests(unittest.TestCase):
    def test_supported_major_targets_origins_and_native_roundtrip_matrix(self):
        from configurator.model import TARGETS,OBSERVERS,parse_saved_view,recognized_body
        for target in TARGETS:
            for observer in OBSERVERS:
                for projection in ('orthographic','space'):
                    view=View(target=target,observer=observer,projection=projection,planet_shade=15,time_mode='fixed',utc='2000-01-01T12:00:00Z')
                    with self.subTest(target=target,observer=observer,projection=projection):
                        if target==observer and projection=='space':
                            with self.assertRaises(ValueError):view.arguments()
                            continue
                        self.assertTrue(recognized_body(view.body()))
                        self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),view.body()).view,view)
                        self.assertEqual(view.arguments()[1],target)
                        if projection=='orthographic':self.assertNotIn('-origin',view.arguments())

    def test_new_shadow_setting_is_bounded_retained_and_earth_inactive(self):
        from configurator.model import parse_saved_view
        for value in (-1,101,10.5,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):View(planet_shade=value).validate()
        dark=View(target='jupiter',planet_shade=0);light=replace(dark,planet_shade=100)
        self.assertIn(b'max_radius_for_label=0\n',dark.body());self.assertNotIn(b'label=false',dark.body());
        self.assertIn(b'shade=0\n',dark.body());self.assertIn(b'shade=100\n',light.body())
        self.assertNotEqual(dark.render_digest(),light.render_digest())
        self.assertEqual(replace(dark,target='earth').render_digest(),replace(light,target='earth').render_digest())
        self.assertNotIn('planet_shade',View().active_fields());self.assertIn('planet_shade',dark.active_fields())
        self.assertEqual(parse_saved_view(dark.definition('/renderer').encode(),dark.body()).view,dark)
        for view in (dark,View(observer='jupiter'),View(target='saturn')):
            with self.assertRaises(ValueError):view.definition('/renderer',version=8)
        old=View(target='moon',projection='space',observer='earth',geometry='800x600')
        self.assertEqual(parse_saved_view(old.definition('/renderer',version=8).encode(),old.body()).view,old)

    def test_body_context_dates_and_resources_do_not_overclaim(self):
        from configurator.model import TARGETS,PLANET_MAPS,ROOT
        for target in TARGETS:
            for year in (1799,2201):
                with self.subTest(target=target,year=year),self.assertRaises(ValueError):View(target=target,utc=f'{year}-01-01T12:00:00Z').validate()
        for target,path in PLANET_MAPS.items():
            self.assertEqual(View(target=target).resource_paths(),[Path(path)])
            self.assertTrue((ROOT/path).is_file(),path)
        self.assertTrue(any('surface texture' in i.message for i in View(target='venus').issues()))
        self.assertTrue(any('Choose space mode' in i.message for i in View(target='saturn').issues()))
        self.assertTrue(any('outer rings' in i.message for i in View(target='saturn',projection='space').issues()))
        for target in ('triton','nereid','sun','random'):
            with self.assertRaises(ValueError):View(target=target).validate()
