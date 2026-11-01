"""Manual event-log retention in isolated roots; no installed logs are opened."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
import stat
from pathlib import Path
import threading
from unittest.mock import patch

from totalmarker.errors import ConfigError, StorageError
from totalmarker import log_trim
from .support import Sandbox

NOW = 100 * 86400


def event(stamp, *, feature="clouds", **fields):
    return (json.dumps({"time": stamp, "feature": feature, "outcome": "unchanged",
                        "message": "Event", **fields}) + "\n").encode()


class LogTrimTests(Sandbox):
    def setup_log(self, data):
        settings = self.config()
        self.fs.write(settings.log, data)
        return settings

    def snapshot(self):
        return {str(path.relative_to(self.root)): (path.stat().st_mode,
                path.stat().st_size, path.stat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None)
                for path in self.root.rglob('*')}

    def test_default_cutoff_uses_event_time_and_keeps_exact_boundary(self):
        cutoff = NOW - 30 * 86400
        lines = [event(cutoff - 1), event(cutoff), event(NOW), event(NOW + 1),
                 event(NOW, installed_at=0, source_at=0),
                 b'{"installed_at": 0, "feature": "clouds"}\n',
                 event(cutoff - 1, feature="unknown"), event(True), event(-1),
                 event(cutoff - 1, feature={"untrusted": "type"}),
                 b'[0, 1]\n']
        settings = self.setup_log(b''.join(lines))
        result = log_trim.trim(self.fs, settings, now=NOW)
        self.assertEqual((result['outcome'], result['scanned'], result['removed'], result['retained']),
                         ('changed', len(lines), 1, len(lines) - 1))
        self.assertEqual(self.fs.read(settings.log), b''.join(lines[1:]))
        self.assertEqual(result['files'][0]['status'], 'trimmed')

    def test_dry_run_does_not_create_lock_temporary_or_modify_files(self):
        settings = self.setup_log(event(NOW - 31 * 86400) + event(NOW))
        before = self.snapshot()
        with patch.object(self.fs, 'lock', side_effect=AssertionError('dry run acquired lock')):
            result = log_trim.trim(self.fs, settings, dry_run=True, now=NOW)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((result['outcome'], result['removed'], result['would_remove']),
                         ('unchanged', 0, 1))
        self.assertEqual(result['files'][0]['status'], 'would_trim')
        self.assertFalse((self.root / settings.lock).exists())

    def test_missing_and_disabled_log_do_not_create_runtime_files(self):
        settings = self.config()
        before = self.snapshot()
        for dry_run in (False, True):
            self.assertEqual(log_trim.trim(self.fs, settings, dry_run=dry_run, now=NOW)
                             ['files'][0]['status'], 'missing')
            self.assertEqual(log_trim.trim(self.fs, replace(settings, log=None),
                                           dry_run=dry_run, now=NOW)['files'], [])
        self.assertEqual(self.snapshot(), before)

    def test_custom_positive_days_and_invalid_values(self):
        settings = self.setup_log(event(NOW - 3 * 86400) + event(NOW - 86400))
        result = log_trim.trim(self.fs, settings, days=2, now=NOW)
        self.assertEqual(result['removed'], 1)
        self.assertEqual(self.fs.read(settings.log), event(NOW - 86400))
        for days in (0, -1, True, 1.5, '30'):
            with self.subTest(days=days), self.assertRaises(ConfigError):
                log_trim.trim(self.fs, settings, days=days, now=NOW)
        self.assertEqual(log_trim.trim(self.fs, settings, days=10**100, now=NOW)['removed'], 0)

    def test_all_project_features_use_the_same_event_contract(self):
        data = b''.join(event(0, feature=feature) for feature in sorted(log_trim.FEATURES))
        settings = self.setup_log(data)
        self.assertEqual(log_trim.trim(self.fs, settings, now=NOW)['removed'], 6)
        self.assertEqual(self.fs.read(settings.log), b'')

    def test_unknown_undated_and_incomplete_records_remain_byte_exact(self):
        old = event(0)
        partial = event(0).rstrip(b'\n')
        retained = b'{"message":"undated","installed_at":0}\n' + partial
        settings = self.setup_log(old + retained)
        self.assertEqual(log_trim.trim(self.fs, settings, now=NOW)['removed'], 1)
        self.assertEqual(self.fs.read(settings.log), retained)

    def test_malformed_multiline_duplicate_keys_and_invalid_utf8_preserve_whole_log(self):
        cases = [b'not JSON\n', b'{\n"metadata":\n' + event(0) + b'}\n',
                 b'{"time":0,"time":1}\n', b'{"time":NaN}\n', b'\xff\n']
        for bad in cases:
            with self.subTest(bad=bad):
                original = event(0) + bad + event(NOW)
                settings = self.setup_log(original)
                result = log_trim.trim(self.fs, settings, now=NOW)
                self.assertEqual((result['removed'], result['files'][0]['status']), (0, 'skipped'))
                self.assertEqual(self.fs.read(settings.log), original)

    def test_line_and_file_limits_preserve_without_unbounded_read(self):
        settings = self.setup_log(event(0, message='x' * 1024))
        original = self.fs.read(settings.log)
        for limit in ('MAX_LINE', 'MAX_FILE'):
            with self.subTest(limit=limit), patch.object(log_trim, limit, 64):
                result = log_trim.trim(self.fs, settings, now=NOW)
                self.assertEqual(result['files'][0]['status'], 'skipped')
                self.assertEqual(self.fs.read(settings.log), original)

    def test_unmanaged_stdout_and_stderr_are_reported_and_preserved(self):
        settings = self.setup_log(event(0))
        (self.root / 'logs/xplanet.log').write_bytes(b'2020-01-01 old-looking stdout\n')
        (self.root / 'logs/xplanet-storm.log').write_bytes(event(0))
        before = {path: (self.root / path).read_bytes()
                  for path in ('logs/xplanet.log', 'logs/xplanet-storm.log')}
        result = log_trim.trim(self.fs, settings, now=NOW)
        self.assertEqual(result['removed'], 1)
        for row in result['files'][1:]:
            self.assertEqual(row['status'], 'skipped')
            self.assertIn('shared writer lock', row['reason'])
            self.assertEqual((self.root / row['path']).read_bytes(), before[row['path']])

    def test_other_extensions_paths_and_configured_collisions_are_ineligible(self):
        settings = self.setup_log(event(0))
        for changed in (replace(settings, log='logs/xplanet.log'),
                        replace(settings, log='markers/events.jsonl'),
                        replace(settings, state=settings.log),
                        replace(settings, lock=settings.log),
                        replace(settings, image=settings.log)):
            with self.subTest(log=changed.log, state=changed.state):
                before = self.snapshot()
                result = log_trim.trim(self.fs, changed, now=NOW)
                self.assertEqual(result['files'][0]['status'], 'skipped')
                self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / settings.lock).exists())

    def test_broken_disabled_product_path_skips_without_creating_lock(self):
        settings = self.setup_log(event(0))
        self.fs.write('markers/obstacle', b'not a directory')
        settings = replace(settings, eclipse=replace(settings.eclipse,
                           marker='markers/obstacle/private-looking-path'))
        before = self.snapshot()
        result = log_trim.trim(self.fs, settings, now=NOW)
        self.assertEqual(result['files'][0]['status'], 'skipped')
        self.assertNotIn('private-looking-path', str(result))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / settings.lock).exists())

    def test_directory_sync_failure_reports_that_replacement_already_occurred(self):
        settings = self.setup_log(event(0) + event(NOW))
        real_sync = os.fsync
        def failed_directory_sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('simulated directory sync failure')
            real_sync(fd)
        with patch.object(log_trim.os, 'fsync', failed_directory_sync), self.assertRaisesRegex(
                StorageError, 'replaced but directory sync failed'):
            log_trim.trim(self.fs, settings, now=NOW)
        self.assertEqual(self.fs.read(settings.log), event(NOW))
        self.assertEqual(list((self.root / 'logs/totalmarker').glob('.totalmarker-trim-*')), [])

    def test_symlink_and_hardlink_aliases_are_never_replaced(self):
        settings = self.setup_log(event(0))
        path = self.root / settings.log
        original = self.fs.read(settings.log)
        alias = path.with_name('alias.jsonl')
        alias.symlink_to(path.name)
        self.assertEqual(log_trim.trim(self.fs, replace(settings, log=str(alias)), now=NOW)
                         ['files'][0]['status'], 'skipped')
        alias.unlink()
        os.link(path, alias)
        self.assertEqual(log_trim.trim(self.fs, settings, now=NOW)['files'][0]['status'], 'skipped')
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)

    def test_configured_protected_symlink_target_is_not_trimmed(self):
        settings = self.setup_log(event(0))
        state = self.root / settings.state
        state.parent.mkdir(parents=True)
        state.symlink_to(self.root / settings.log)
        result = log_trim.trim(self.fs, settings, now=NOW)
        self.assertEqual(result['files'][0]['status'], 'skipped')
        self.assertEqual(self.fs.read(settings.log), event(0))

    def test_cooperating_append_waits_for_trim_and_is_not_lost(self):
        settings = self.setup_log(event(0) + event(NOW))
        reading, writer_started, writer_acquired = (threading.Event() for _ in range(3))
        scan = log_trim._scan
        def paused_scan(*args, **kwargs):
            if not reading.is_set():
                reading.set()
                self.assertTrue(writer_started.wait(3))
                self.assertFalse(writer_acquired.is_set())
            return scan(*args, **kwargs)
        def append():
            self.assertTrue(reading.wait(3))
            writer_started.set()
            with self.fs.lock(settings.lock):
                writer_acquired.set()
                self.fs.append(settings.log, event(NOW + 1))
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(log_trim, '_scan', paused_scan):
            appending = pool.submit(append)
            trimming = pool.submit(log_trim.trim, self.fs, settings, now=NOW)
            result = trimming.result(timeout=5)
            appending.result(timeout=5)
        self.assertEqual(result['removed'], 1)
        self.assertTrue(writer_acquired.is_set())
        self.assertEqual(self.fs.read(settings.log), event(NOW) + event(NOW + 1))

    def test_uncoordinated_append_detected_before_replacement(self):
        settings = self.setup_log(event(0))
        scan = log_trim._scan
        appended = False
        def racing_scan(*args, **kwargs):
            nonlocal appended
            result = scan(*args, **kwargs)
            if not appended:
                appended = True
                self.fs.append(settings.log, event(NOW))
            return result
        with patch.object(log_trim, '_scan', racing_scan):
            result = log_trim.trim(self.fs, settings, now=NOW)
        self.assertEqual(result['files'][0]['status'], 'skipped')
        self.assertEqual(self.fs.read(settings.log), event(0) + event(NOW))

    def test_pathname_replacement_detected_before_atomic_publish(self):
        settings = self.setup_log(event(0) + event(NOW))
        scan, passes = log_trim._scan, 0
        replacement = event(NOW + 2)
        def racing_scan(*args, **kwargs):
            nonlocal passes
            result = scan(*args, **kwargs)
            passes += 1
            if passes == 2:
                other = self.root / 'logs/totalmarker/replacement.jsonl'
                other.write_bytes(replacement)
                os.replace(other, self.root / settings.log)
            return result
        with patch.object(log_trim, '_scan', racing_scan):
            result = log_trim.trim(self.fs, settings, now=NOW)
        self.assertEqual(result['files'][0]['status'], 'skipped')
        self.assertEqual(self.fs.read(settings.log), replacement)
        self.assertEqual(list((self.root / 'logs/totalmarker').glob('.totalmarker-trim-*')), [])
