"""Explicit icon import uses only synthetic, disposable source/project roots."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

from configurator import installed_icons as icons
from configurator.astronomy_capture import normalize_icon
from tests.support import PROJECT


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def png(width=1, interlace=0):
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, 1, 8, 2, 0, 0, interlace)) +
            chunk(b'tEXt', b'Credit\0Synthetic test fixture') +
            chunk(b'IDAT', zlib.compress(b'\0' * (1 + 3 * width))) + chunk(b'IEND', b''))


class InstalledIconTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='installed-icons-', dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'installed'; self.project = self.root / 'project'
        for root in (self.source, self.project):
            (root / 'images').mkdir(parents=True)
        self.readme = b'Synthetic original attribution: iss.png, hubble.png, shuttle.png.\r\nNo real imagery.\n'
        (self.source / 'images/README').write_bytes(self.readme)
        for name in icons.ICONS:
            (self.source / 'images' / (name + '.png')).write_bytes(png())
        (self.project / 'images/existing.png').write_bytes(b'preserve existing content')
        (self.project / 'config').mkdir()
        (self.project / 'config/totalmarker.toml').write_text('unchanged producer settings')

    def inventory(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}

    def run_import(self, names=('iss',), **kwargs):
        return icons.import_icons(self.source, self.project, names, **kwargs)

    def test_default_preview_is_read_only_and_selected_only(self):
        before = self.inventory()
        with patch('totalmarker.http.Fetcher.fetch', side_effect=AssertionError('No network')):
            result = self.run_import()
        self.assertEqual(result['mode'], 'preview'); self.assertEqual(result['created'], [])
        self.assertEqual([row['name'] for row in result['icons']], ['iss'])
        self.assertEqual(before, self.inventory())
        self.assertEqual(set(p.name for p in (self.project / 'images').iterdir()), {'existing.png'})

    def test_explicit_import_preserves_exact_png_attribution_and_receipts(self):
        before = self.inventory()
        with patch('totalmarker.http.Fetcher.fetch', side_effect=AssertionError('No network')):
            result = self.run_import(icons.ICONS, apply=True)
        self.assertEqual(len(result['created']), 9)
        for name in icons.ICONS:
            image, attribution, receipt_name = icons.output_names(name)
            self.assertEqual((self.project / 'images' / image).read_bytes(), png())
            self.assertEqual((self.project / 'images' / attribution).read_bytes(), self.readme)
            raw = (self.project / 'images' / receipt_name).read_bytes(); receipt = json.loads(raw)
            self.assertEqual(receipt['sha256'], hashlib.sha256(png()).hexdigest())
            self.assertEqual(receipt['normalized_sha256'], hashlib.sha256(normalize_icon(png())).hexdigest())
            self.assertNotEqual(receipt['sha256'], receipt['normalized_sha256'])
            self.assertEqual(receipt['attribution']['sha256'], hashlib.sha256(self.readme).hexdigest())
            self.assertFalse(receipt['authorship_verified']); self.assertNotIn(str(self.root).encode(), raw)
        after = self.inventory()
        for name, raw in before.items():
            self.assertEqual(after[name], raw)
        self.assertFalse(any(p.name.startswith('.satellite-icon-import-') for p in (self.project / 'images').iterdir()))

    def test_allowlist_and_duplicate_selection_rejected_before_io(self):
        for names in ((), ('iss', 'iss'), ('../iss',), ('ISS',), ('mgs',), ('iss.png',), ('/tmp/image',)):
            with self.subTest(names=names), patch.object(icons.Directory, '__enter__', side_effect=AssertionError('No IO')):
                with self.assertRaises(icons.IconImportError):
                    self.run_import(names, apply=True)

    def test_any_destination_collision_refuses_whole_batch_without_overwriting(self):
        for name in icons.output_names('hubble'):
            target = self.project / 'images' / name
            for kind in ('file', 'directory', 'link', 'dangling', 'fifo'):
                with self.subTest(name=name, kind=kind):
                    if kind == 'file': target.write_bytes(b'existing')
                    elif kind == 'directory': target.mkdir()
                    elif kind == 'link': target.symlink_to(self.project / 'images/existing.png')
                    elif kind == 'dangling': target.symlink_to(self.root / 'absent')
                    else: os.mkfifo(target)
                    before = (self.project / 'images/existing.png').read_bytes()
                    with self.assertRaises(icons.IconImportError):
                        self.run_import(('iss', 'hubble'), apply=True)
                    self.assertFalse((self.project / 'images/iss.png').exists())
                    self.assertEqual((self.project / 'images/existing.png').read_bytes(), before)
                    if kind == 'directory': target.rmdir()
                    else: target.unlink()

    def test_missing_attribution_invalid_png_and_bounds_refuse_before_writes(self):
        readme = self.source / 'images/README'; image = self.source / 'images/iss.png'
        for raw in (b'JPEG', png()[:-1], png(513), png(interlace=1), b'x' * (icons.ICON_LIMIT + 1)):
            image.write_bytes(raw)
            with self.assertRaises(ValueError): self.run_import(apply=True)
        image.write_bytes(png())
        for raw in (b'', b'unrelated README', b'iss.png\0', b'iss.png\xff', b'x' * (icons.README_LIMIT + 1)):
            readme.write_bytes(raw)
            with self.assertRaises(ValueError): self.run_import(apply=True)
        readme.unlink()
        with self.assertRaises(OSError): self.run_import(apply=True)
        self.assertEqual(set(p.name for p in (self.project / 'images').iterdir()), {'existing.png'})

    def test_source_file_links_directories_and_fifos_fail_without_blocking(self):
        for name in ('README', 'iss.png'):
            target = self.source / 'images' / name; original = target.read_bytes(); target.unlink()
            for kind in ('directory', 'link', 'fifo'):
                with self.subTest(name=name, kind=kind):
                    if kind == 'directory': target.mkdir()
                    elif kind == 'link': target.symlink_to(self.project / 'images/existing.png')
                    else: os.mkfifo(target)
                    with self.assertRaises((OSError, ValueError)): self.run_import(apply=True)
                    if kind == 'directory': target.rmdir()
                    else: target.unlink()
            target.write_bytes(original)

    def test_roots_and_images_reject_symlink_components_and_relative_paths(self):
        alias = self.root / 'alias'; alias.symlink_to(self.source)
        with self.assertRaises(OSError): icons.import_icons(alias, self.project, ('iss',), apply=True)
        alias.unlink(); alias.symlink_to(self.project)
        with self.assertRaises(OSError): icons.import_icons(self.source, alias, ('iss',), apply=True)
        for root in (self.source, self.project):
            images = root / 'images'; saved = root / 'saved-images'; images.rename(saved); images.symlink_to(saved)
            with self.assertRaises(OSError): self.run_import(apply=True)
            images.unlink(); saved.rename(images)
        for source, project in (('relative', self.project), (self.source, 'relative'), (self.source, self.source)):
            with self.assertRaises(ValueError): icons.import_icons(source, project, ('iss',), apply=True)

    def test_source_mutation_during_read_and_before_publication_are_detected(self):
        original_read = os.read; changed = False
        def racing_read(fd, size):
            nonlocal changed
            raw = original_read(fd, size)
            if raw.startswith(b'\x89PNG') and not changed:
                changed = True
                (self.source / 'images/iss.png').write_bytes(png() + b'changed')
            return raw
        with patch.object(icons.os, 'read', side_effect=racing_read), self.assertRaises(ValueError):
            self.run_import(apply=True)
        (self.source / 'images/iss.png').write_bytes(png())
        original_publish = icons.publish
        def changed_before_publish(destination, files, verify):
            (self.source / 'images/README').write_bytes(self.readme + b'changed')
            return original_publish(destination, files, verify)
        with patch.object(icons, 'publish', side_effect=changed_before_publish), self.assertRaises(ValueError):
            self.run_import(apply=True)
        self.assertEqual(set(p.name for p in (self.project / 'images').iterdir()), {'existing.png'})

    def test_destination_directory_swap_before_publication_cannot_redirect_writes(self):
        original = icons.publish; outside = self.root / 'outside'; outside.mkdir()
        def changed(destination, files, verify):
            (self.project / 'images').rename(self.project / 'moved-images')
            (self.project / 'images').symlink_to(outside)
            return original(destination, files, verify)
        with patch.object(icons, 'publish', side_effect=changed), self.assertRaises(ValueError):
            self.run_import(apply=True)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual([p.name for p in (self.project / 'moved-images').iterdir()], ['existing.png'])

    def test_late_collision_retains_foreign_file_and_reports_prior_new_files(self):
        original = os.open
        def racing_open(path, flags, *args, **kwargs):
            if path == 'iss.png' and flags & os.O_CREAT:
                (self.project / 'images/iss.png').write_bytes(b'foreign race winner')
            return original(path, flags, *args, **kwargs)
        with patch.object(icons.os, 'open', side_effect=racing_open), self.assertRaisesRegex(ValueError, 'already created and retained') as error:
            self.run_import(apply=True)
        self.assertEqual((self.project / 'images/iss.png').read_bytes(), b'foreign race winner')
        self.assertIn('images/iss.png.source-readme.txt', str(error.exception))
        self.assertTrue((self.project / 'images/iss.png.import.json').exists())

    def test_write_failure_reports_only_created_incomplete_file_and_never_removes_it(self):
        with patch.object(icons.os, 'write', side_effect=OSError('synthetic write error')), self.assertRaisesRegex(ValueError, 'possibly incomplete') as error:
            self.run_import(apply=True)
        self.assertIn('images/iss.png.source-readme.txt', str(error.exception))
        self.assertEqual((self.project / 'images/iss.png.source-readme.txt').read_bytes(), b'')
        self.assertEqual((self.project / 'images/existing.png').read_bytes(), b'preserve existing content')
        self.assertFalse((self.project / 'images/iss.png').exists())

    def test_in_place_mutation_after_write_is_detected(self):
        original = icons.verify_copy; changed = False
        def mutate(destination, name, fd, raw):
            nonlocal changed
            if name == 'iss.png' and not changed:
                changed = True
                (self.project / 'images/iss.png').write_bytes(b'x' * len(raw))
            return original(destination, name, fd, raw)
        with patch.object(icons, 'verify_copy', side_effect=mutate), self.assertRaisesRegex(ValueError, 'changed during import'):
            self.run_import(apply=True)

    def test_new_file_symlink_swap_cannot_redirect_descriptor_writes(self):
        original = os.open; outside = self.root / 'outside.txt'; outside.write_bytes(b'untouched')
        def racing_open(path, flags, *args, **kwargs):
            fd = original(path, flags, *args, **kwargs)
            if path == 'iss.png' and flags & os.O_CREAT:
                (self.project / 'images/iss.png').unlink()
                (self.project / 'images/iss.png').symlink_to(outside)
            return fd
        with patch.object(icons.os, 'open', side_effect=racing_open), self.assertRaisesRegex(ValueError, 'changed during import'):
            self.run_import(apply=True)
        self.assertEqual(outside.read_bytes(), b'untouched')

    def test_cli_from_unrelated_cwd_uses_checkout_code_not_colliding_module(self):
        caller = self.root / 'caller'; caller.mkdir()
        (caller / 'configurator.py').write_text('raise RuntimeError("wrong module")\n')
        (caller / 'totalmarker.py').write_text('raise RuntimeError("wrong module")\n')
        command = [str(PROJECT / 'scripts/import-satellite-icons'), '--resource-root', str(self.source),
                   '--project-root', str(self.project), '--icon', 'iss', '--json']
        env = {**os.environ, 'TOTALMARKER_PYTHON': sys.executable, 'PYTHONPATH': str(caller)}
        before = self.inventory()
        result = subprocess.run(command, cwd=caller, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['mode'], 'preview'); self.assertEqual(before, self.inventory())
        result = subprocess.run(command + ['--import'], cwd=caller, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(json.loads(result.stdout)['mode'], 'imported')
        result = subprocess.run(command, cwd=caller, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2); self.assertNotIn('Traceback', result.stderr)
