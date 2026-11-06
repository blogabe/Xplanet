"""Scene exchange is inert canonical data; never general archive extraction."""
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from configurator.exchange import export_scene, import_scene, preview_bytes, encode, digest, scene_files
from configurator.library import save_named
from configurator.model import View, ROOT
from configurator.workspace import open_view


def chunk(kind, raw):
    return len(raw).to_bytes(4,'big')+kind+raw+(zlib.crc32(kind+raw)&0xffffffff).to_bytes(4,'big')


def png():
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'tEXt',b'private path\0/Users/secret')+chunk(b'IDAT',zlib.compress(b'\0\0\0\0'))+chunk(b'IEND',b'')


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.view=View(places='on',places_text='10 20 "Home"\n')
        self.source=save_named(self.root/'private-scene.conf',self.view,sys.executable)
        self.before={path.name:path.read_bytes() for path in self.root.iterdir() if path.is_file()}

    def export(self, **kwargs):
        return export_scene(self.source,self.root/'package',**kwargs)/'scene.xplanet.zip'

    def import_(self, archive, name='imported'):
        return import_scene(archive,self.root/name,renderer=sys.executable)

    def rewrite(self, archive, mutate):
        with zipfile.ZipFile(archive) as source:files={row.filename:source.read(row) for row in source.infolist()}
        mutate(files)
        target=self.root/'changed.zip'
        with zipfile.ZipFile(target,'w') as out:
            for name,data in files.items():out.writestr(name,data)
        return target

    def test_named_roundtrip_rebases_only_local_paths_and_retains_fields(self):
        archive=self.export();raw=archive.read_bytes()
        self.assertNotIn(str(self.root).encode(),raw);self.assertNotIn(str(ROOT).encode(),raw)
        self.assertNotIn(sys.executable.encode(),raw)
        target=self.import_(archive);doc=open_view(target)
        self.assertEqual(doc.view,self.view)
        self.assertEqual({path.name:path.read_bytes() for path in self.root.iterdir() if path.name in self.before},self.before)
        self.assertEqual(Path(doc.saved_renderer),Path(sys.executable).resolve())
        self.assertIn(str(ROOT).encode(),(target/'xp.def').read_bytes())
        self.assertFalse(json.loads((target/'exchange-receipt.json').read_bytes())['activated'])
        self.assertTrue(all(path.stat().st_mode&0o777==0o600 for path in target.iterdir()))

    def test_legacy_scene_directory_roundtrip(self):
        source=self.root/'legacy';source.mkdir()
        for name,data in scene_files(View()).items():(source/name).write_bytes(data)
        archive=export_scene(source,self.root/'package')/'scene.xplanet.zip'
        self.assertEqual(open_view(self.import_(archive)).view,View())

    def test_preview_strips_ancillary_metadata_and_is_illustrative(self):
        image=self.root/'preview.png';image.write_bytes(png())
        archive=self.export(preview=image)
        with zipfile.ZipFile(archive) as source:
            raw=source.read('preview.png');self.assertNotIn(b'private path',raw)
            self.assertEqual(preview_bytes(raw),raw)
            self.assertIn('not verified',json.loads(source.read('exchange.json'))['preview'])
        self.assertEqual((self.import_(archive)/'preview.png').read_bytes(),raw)
        self.assertEqual(image.read_bytes(),png())

    def test_preview_corruption_truncation_and_dimensions_refused(self):
        for raw in (png()[:-1],png()[:20],png().replace(b'IDAT',b'IDaT'),b'JPEG'):
            with self.subTest(raw=raw[:12]),self.assertRaises(ValueError):preview_bytes(raw)
        raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',9000,1,8,2,0,0,0))+chunk(b'IDAT',b'')+chunk(b'IEND',b'')
        with self.assertRaises(ValueError):preview_bytes(raw)

    def test_captured_layers_refused_without_silent_loss(self):
        for view in (replace(self.view,capture_id='a'*64),replace(self.view,observations_id='b'*64)):
            with self.assertRaisesRegex(ValueError,'excludes frozen'):scene_files(view)

    def test_existing_destinations_and_symlink_inputs_untouched(self):
        archive=self.export();target=self.root/'imported';target.mkdir();(target/'keep').write_bytes(b'keep')
        with self.assertRaises(ValueError):self.import_(archive)
        with self.assertRaises(ValueError):export_scene(self.source,self.root/'package')
        linked=self.root/'link.zip';linked.symlink_to(archive)
        with self.assertRaises(ValueError):self.import_(linked,'linked')
        self.assertEqual((target/'keep').read_bytes(),b'keep')

    def test_hash_mismatch_and_extra_files_refused_before_destination(self):
        archive=self.export()
        for mutate in (lambda files:files.update({'xp.conf':b'changed'}),lambda files:files.update({'secret.txt':b'secret'})):
            with self.subTest(mutate=mutate):
                target=self.rewrite(archive,mutate)
                with self.assertRaises(ValueError):self.import_(target)
                self.assertFalse((self.root/'imported').exists())

    def test_archive_paths_links_directories_compression_duplicates_refused(self):
        archive=self.export()
        for name in ('../outside','/absolute','sub/file','sub\\file','bad\x1bname'):
            target=self.rewrite(archive,lambda files:files.update({name:b'evil'}))
            with self.subTest(name=name),self.assertRaises(ValueError):self.import_(target)
        for mode,compression,duplicate in ((stat.S_IFLNK|0o777,0,False),(stat.S_IFDIR|0o700,0,False),(stat.S_IFREG|0o600,zipfile.ZIP_DEFLATED,False),(stat.S_IFREG|0o600,0,True)):
            target=self.root/'malicious.zip'
            with zipfile.ZipFile(archive) as source,zipfile.ZipFile(target,'w') as out:
                for row in source.infolist():out.writestr(row,source.read(row))
                row=zipfile.ZipInfo('evil');row.create_system=3;row.external_attr=mode<<16;row.compress_type=compression
                out.writestr(row,b'evil')
                if duplicate:out.writestr('evil',b'again')
            with self.assertRaises(ValueError):self.import_(target)
        self.assertFalse((self.root/'outside').exists());self.assertFalse((self.root/'imported').exists())

    def test_forged_consistent_definition_still_not_executable_import(self):
        archive=self.export()
        def modify(files):
            files['xp.def']+=b'execute arbitrary shell\n'
            meta=json.loads(files['exchange.json']);meta['files']['xp.def']={'bytes':len(files['xp.def']),'sha256':digest(files['xp.def'])};files['exchange.json']=encode(meta)
        with self.assertRaises(ValueError):self.import_(self.rewrite(archive,modify))
        self.assertFalse((self.root/'imported').exists())

    def test_manifest_duplicates_unknown_schema_and_noncanonical_paths_refused(self):
        archive=self.export()
        for replacement in (b'{"schema":1,"schema":1}',b'[]',b'null'):
            changed=self.rewrite(archive,lambda files:files.update({'exchange.json':replacement}))
            with self.assertRaises(ValueError):self.import_(changed)
        def modify(files):
            files['xp.def']=files['xp.def'].replace(b'/xplanet-exchange/renderer',b'/private/evil/bin')
            meta=json.loads(files['exchange.json']);meta['files']['xp.def']={'bytes':len(files['xp.def']),'sha256':digest(files['xp.def'])};files['exchange.json']=encode(meta)
        with self.assertRaises(ValueError):self.import_(self.rewrite(archive,modify))

    def test_read_bounds_and_member_limits(self):
        archive=self.export()
        with patch('configurator.exchange.LIMIT',100),self.assertRaises(ValueError):self.import_(archive)
        with patch('configurator.exchange.MAX_FILES',2),self.assertRaises(ValueError):self.import_(archive)
        with patch('configurator.exchange.LIMIT',100),self.assertRaises(ValueError):export_scene(self.source,self.root/'too-big')
        self.assertFalse((self.root/'too-big').exists())

    def test_output_write_failure_preserves_existing_sources(self):
        archive=self.export()
        with patch('configurator.fileio.OwnedFiles.write',side_effect=OSError('fixture failure')),self.assertRaises(OSError):self.import_(archive)
        self.assertFalse((self.root/'imported').exists())
        self.assertEqual(self.source.read_bytes(),self.before[self.source.name])

    def test_no_renderer_execution_or_subprocess(self):
        archive=self.export()
        with patch('subprocess.Popen',side_effect=AssertionError('must not execute')):
            self.import_(archive)

    def test_cli_help_and_bad_input_without_textual(self):
        import subprocess
        env={**os.environ,'PYTHONPATH':str(ROOT/'scripts'),'PYTHONDONTWRITEBYTECODE':'1'}
        run=subprocess.run([sys.executable,'-B','-m','configurator.exchange','--help'],env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0);self.assertIn('--destination',run.stdout)
        run=subprocess.run([sys.executable,'-B','-m','configurator.exchange','--import',str(self.root/'missing'),'--destination',str(self.root/'new'),'--renderer',sys.executable],env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,2);self.assertIn('refused',run.stderr)

    def test_all_stock_scenes_exchange_without_copying_bundled_maps(self):
        sources=sorted((ROOT/'scripts/configurator/samples/scenes').glob('*.conf'))
        self.assertGreaterEqual(len(sources),24)
        for index,source in enumerate(sources):
            with self.subTest(scene=source.name):
                archive=export_scene(source,self.root/f'package-{index}')/'scene.xplanet.zip'
                target=self.import_(archive,f'scene-{index}')
                self.assertEqual(open_view(target).view,open_view(source).view)
                with zipfile.ZipFile(archive) as packaged:
                    self.assertFalse(any(name.endswith(('.jpg','.jpeg')) for name in packaged.namelist()))

    def test_png_decompression_bomb_and_pixel_mismatch_refused(self):
        header=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))
        for pixels in (b'a'*1_000_000,b'\0',b'\x05\0\0\0'):
            raw=header+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
            with self.assertRaises(ValueError):preview_bytes(raw)

    def test_symlink_destination_parent_is_refused_without_mutation(self):
        archive=self.export();link=self.root/'linked-parent';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):import_scene(archive,link/'new',renderer=sys.executable)
        self.assertFalse((self.root/'new').exists())

    def test_consistently_forged_unknown_file_is_refused(self):
        archive=self.export()
        def modify(files):
            files['unused.txt']=b'private content'
            meta=json.loads(files['exchange.json']);meta['files']['unused.txt']={'bytes':15,'sha256':digest(files['unused.txt'])};files['exchange.json']=encode(meta)
        with self.assertRaises(ValueError):self.import_(self.rewrite(archive,modify))
        self.assertFalse((self.root/'imported').exists())

    def test_control_character_destination_refused(self):
        archive=self.export()
        with self.assertRaises(ValueError):self.import_(archive,'bad\x1bname')
        self.assertFalse((self.root/'bad\x1bname').exists())

    def test_forged_small_entry_count_cannot_allocate_large_zip_index(self):
        target=self.root/'many.zip'
        with zipfile.ZipFile(target,'w') as archive:
            for index in range(100):archive.writestr(f'entry-{index}',b'')
        raw=bytearray(target.read_bytes());raw[-14:-12]=(3).to_bytes(2,'little');raw[-12:-10]=(3).to_bytes(2,'little');target.write_bytes(raw)
        with patch('configurator.exchange.zipfile.ZipFile',side_effect=AssertionError('index parser must not run')),self.assertRaises(ValueError):self.import_(target)

    def test_future_astronomy_associations_cannot_be_silently_omitted(self):
        from types import SimpleNamespace
        for product in ('norad','eclipse'):
            view=SimpleNamespace(capture_id='',observations_id='',norad_id='',eclipse_id='')
            setattr(view,product+'_id','a'*64)
            with self.assertRaisesRegex(ValueError,'excludes frozen'):scene_files(view)
