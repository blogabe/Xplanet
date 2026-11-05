"""Local files are unverified inputs, never fabricated provider successes."""
import asyncio,hashlib,json,sys,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from configurator.astronomy_capture import local_eclipse,FrozenAstronomy,describe,reference_url
from configurator.cloud_capture import CaptureError,json_bytes
from configurator.model import View,SAMPLE
from configurator.workspace import Workspace,open_view
from configurator.library import save_named
from configurator.recovery import pack,raw_fields,RecoveryStore
from configurator.handoff import create_plan,stage_plan,check_bundle
from .test_eclipse import TOTAL,TOTAL_URL,ANNULAR_URL


class LocalEclipseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
        self.source=self.root/'private-local-name.html';self.source.write_bytes(TOTAL+b'<!--PrivateLocalToken-->' )
        self.w=Workspace();self.addCleanup(self.w.close)
    def load(self):return local_eclipse(self.source,TOTAL_URL,now=1800000000)

    async def test_import_is_readonly_no_fetch_no_private_path_or_fabricated_success(self):
        before=self.source.read_bytes(),self.source.stat().st_mtime_ns
        with patch('totalmarker.http.Fetcher.fetch',side_effect=AssertionError('network forbidden')):frozen=self.load()
        meta=frozen.metadata;self.assertEqual(meta['schema'],2);self.assertIsNone(meta['source_hashes']);self.assertTrue(all(value is None for value in meta['facts'].values()))
        self.assertEqual(meta['origin']['input_sha256'],hashlib.sha256(before[0]).hexdigest());self.assertFalse(meta['origin']['authorship_verified'])
        self.assertTrue(all(data.startswith(b'# Unverified local NASA-format central path;') for _,data in frozen.payload))
        self.assertNotIn(b'PrivateLocalToken',frozen.provenance);self.assertNotIn(str(self.source).encode(),frozen.provenance)
        self.assertEqual(before,(self.source.read_bytes(),self.source.stat().st_mtime_ns));self.assertIn('authorship NOT verified',describe(frozen))

    async def test_previous_local_headers_remain_readable_without_rewriting(self):
        frozen=self.load();meta=frozen.metadata
        header=f"# Eclipse Predictions by Fred Espenak, NASA's GSFC; {meta['kind']} {meta['event_date']} UTC\n".encode('ascii')
        payload=tuple((name,header+data.split(b'\n',1)[1]) for name,data in frozen.payload)
        meta['files']={name:hashlib.sha256(data).hexdigest() for name,data in payload}
        restored=FrozenAstronomy(json_bytes(meta),payload)
        self.assertEqual(restored.payload,payload);self.assertFalse(restored.metadata['origin']['authorship_verified'])

    async def test_event_and_reference_mismatch_credentials_host_queries_refuse(self):
        for url in (ANNULAR_URL,TOTAL_URL.replace('eclipse.gsfc.nasa.gov','example.invalid'),TOTAL_URL+'?token=secret',TOTAL_URL+'#fragment',TOTAL_URL.replace('https://','https://user:secret@')):
            with self.subTest(url=url),self.assertRaises(CaptureError):local_eclipse(self.source,url)
        for change in (TOTAL.replace(b'11:32',b'11:33'),TOTAL.replace(b'2027 Aug 02',b'2027 Aug 03'),TOTAL[:50]):
            self.source.write_bytes(change)
            with self.assertRaises(CaptureError):self.load()

    async def test_missing_link_loop_oversize_and_invalid_import_time_refuse(self):
        for name in ('absent','linked','loop'):
            source=self.root/name
            if name=='linked':source.symlink_to(self.source)
            if name=='loop':source.symlink_to(source)
            with self.assertRaises(CaptureError):local_eclipse(source,TOTAL_URL)
        self.source.write_bytes(b'x'*(2*1024*1024+1))
        with self.assertRaises(CaptureError):self.load()
        self.source.write_bytes(TOTAL)
        for moment in (True,float('nan')):
            with self.assertRaises(CaptureError):local_eclipse(self.source,TOTAL_URL,now=moment)

    async def test_provenance_tampering_or_claimed_provider_success_refuse(self):
        frozen=self.load()
        for change in ({'reference_url':ANNULAR_URL},{'authorship_verified':True},{'input_bytes':True},{'private_path':'secret'}):
            meta=frozen.metadata;meta['origin'].update(change)
            with self.assertRaises(CaptureError):FrozenAstronomy(json_bytes(meta),frozen.payload)
        meta=frozen.metadata;meta['facts']['successful_at']=1800000000
        with self.assertRaises(CaptureError):FrozenAstronomy(json_bytes(meta),frozen.payload)

    async def test_actual_worker_save_reopen_handoff_and_recovery_keep_origin(self):
        frozen=await self.w.import_eclipse_file(self.source,TOTAL_URL);self.assertEqual(frozen.product,'eclipse')
        view=View(eclipse_layer='captured',eclipse_id=frozen.identity,eclipse_window=frozen.window_token,time_mode='fixed',utc=frozen.window_token.split('/')[0])
        scene=save_named(self.root/'config/scenes/local.conf',view,sys.executable,astronomy={'eclipse':frozen})
        self.assertEqual(open_view(scene).astronomy,(frozen,))
        plan=create_plan(self.root,scene,sys.executable,'1920x1080');target=stage_plan(plan,self.root/'review');check_bundle(self.root,target)
        store=RecoveryStore(self.root);session=store.new_session()
        try:
            fields=raw_fields(view,sys.executable);await session.checkpoint(*pack(fields,fields,SAMPLE.read_bytes(),self.w));session.close()
            self.assertEqual(store.load(session.identity).astronomy,(frozen,))
        finally:session.close()
        self.assertFalse((self.root/'config/desktop.scene').exists())
