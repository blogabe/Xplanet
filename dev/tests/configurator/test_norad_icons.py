"""Bounded PNG dependency capture with no provider or desktop operations."""
from dataclasses import replace
import hashlib,json,struct,sys,zlib
from pathlib import Path
from unittest.mock import patch
from configurator.astronomy_capture import capture_existing,FrozenAstronomy,normalize_icon,FILES
from configurator.cloud_capture import CaptureError,CaptureRace,json_bytes
from configurator.model import View,SAMPLE
from configurator.workspace import Workspace,open_view
from configurator.library import save_named
from configurator.recovery import pack,raw_fields,RecoveryStore
from configurator.exchange import export_scene
from configurator.handoff import create_plan
from totalmarker.config import load
from totalmarker.features import norad
from totalmarker.http import Fetcher,Response
from tests.support import Sandbox, ScriptedTransport
from tests.test_norad import SAMPLE as TLE, EPOCH, sample_for
from tests.configurator.test_scene_exchange import png, chunk

class NoradIconTests(Sandbox):
    def fixture(self,ids=(25544,),raw=None):
        profiles=''.join(f'[[norad.profiles]]\ncatalog_id={i}\nicon="iss.png"\ncaption=""\n' for i in ids)
        (self.root/'config.toml').write_bytes(('[cloud]\nprovider="custom"\nurl="https://example.invalid/map"\n[norad]\nenabled=true\ncatalog_ids="'+','.join(map(str,ids))+'"\n'+profiles).encode())
        settings=load(self.fs,'config.toml');self.fs.write('images/iss.png',png() if raw is None else raw)
        norad.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(*(Response(200,{},sample_for(i,'SYNTHETIC')) for i in ids))),now=EPOCH+10)
        return settings
    def capture(self):return capture_existing(self.root.resolve(),'norad','config.toml',now=EPOCH+20)
    def test_raw_hash_sanitized_hash_distinct_source_readonly_no_network(self):
        self.fixture();before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('totalmarker.http.Fetcher.fetch',side_effect=AssertionError('network')):frozen=self.capture()
        name='frozen-norad-25544.png';meta=frozen.metadata
        self.assertEqual(meta['schema'],3);self.assertEqual(meta['icons'],{'25544':name})
        self.assertEqual(meta['source_hashes'][name],hashlib.sha256(png()).hexdigest());self.assertNotEqual(meta['source_hashes'][name],meta['files'][name])
        self.assertNotIn(b'/Users/secret',dict(frozen.payload)[name]);self.assertNotIn(b'iss.png',frozen.provenance)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertTrue(frozen.availability(target='earth',time_mode='now',now=EPOCH+30)[0])
    def test_same_source_icon_for_two_ids_and_sixteen_file_recovery_bound(self):
        self.fixture(tuple(range(25540,25556)));frozen=self.capture();self.assertEqual(len(frozen.files()),19)
        w=Workspace();self.addCleanup(w.close);w.register_astronomy(frozen)
        view=View(norad_layer='captured',norad_id=frozen.identity,time_mode='fixed')
        fields=raw_fields(view,sys.executable);record,blobs=pack(fields,fields,SAMPLE.read_bytes(),w)
        store=RecoveryStore(self.root);session=store.new_session();self.addCleanup(session.close)
        import asyncio
        asyncio.run(session.checkpoint(record,blobs));session.close()
        self.assertEqual(store.load(session.identity).astronomy,(frozen,))
        self.assertLessEqual(len(blobs),64)
    def test_named_prefix_reopen_inactive_handoff_and_exchange_refusal(self):
        self.fixture((25544,20580));frozen=self.capture();view=View(norad_layer='captured',norad_id=frozen.identity,time_mode='fixed')
        (self.root/'config').mkdir(exist_ok=True)
        source=save_named(self.root/'config/scenes'/'icons.conf',view,sys.executable,astronomy={'norad':frozen})
        selector=(source.parent/'icons.frozen-norad.satellites').read_bytes();self.assertIn(b'image=icons.frozen-norad-25544.png',selector)
        self.assertEqual(open_view(source).astronomy,(frozen,));create_plan(self.root,source,sys.executable,'1920x1080')
        with self.assertRaises(ValueError):export_scene(source,self.root/'exchange')
        changed=selector.replace(b'icons.frozen-norad-25544.png',b'frozen-norad-25544.png');(source.parent/'icons.frozen-norad.satellites').write_bytes(changed)
        with self.assertRaises(ValueError):open_view(source)
    def test_invalid_png_bounds_metadata_and_refusal_do_not_drop_icons(self):
        self.fixture();icon=self.root/'images/iss.png'
        huge=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',513,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'*(1+513*3)))+chunk(b'IEND',b'')
        for raw in (b'JPEG',png()[:-1],png().replace(b'IDAT',b'IDaT'),huge,b'x'*(1024*1024+1)):
            icon.write_bytes(raw)
            with self.assertRaises(CaptureError):self.capture()
        icon.write_bytes(png());frozen=self.capture()
        for icons in ({'25544':'../secret.png'},{'1':'frozen-norad-1.png'},{'25544':[]},{}):
            meta=frozen.metadata;meta['icons']=icons
            with self.assertRaises(CaptureError):FrozenAstronomy(json_bytes(meta),frozen.payload)
        icon.unlink();icon.symlink_to(self.root/'config.toml')
        with self.assertRaises(CaptureError):self.capture()
    def test_dependency_race_is_bounded_refusal(self):
        self.fixture();from configurator import astronomy_capture as module
        original=module.read_stable;calls=0
        def changing(fs,path,limit):
            nonlocal calls
            raw=original(fs,path,limit)
            if path=='images/iss.png':
                calls+=1
                if calls%2==0:return raw+b'changed'
            return raw
        with patch.object(module,'read_stable',side_effect=changing),self.assertRaises(CaptureRace):self.capture()
        self.assertEqual(calls,4)

    def test_duplicate_dependency_cannot_mix_two_icon_generations(self):
        self.fixture((25544,20580));from configurator import astronomy_capture as module
        original=module.read_stable;calls=0
        alternate=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\0\xff\0'))+chunk(b'IEND',b'')
        def changing(fs,path,limit):
            nonlocal calls
            raw=original(fs,path,limit)
            if path=='images/iss.png':
                calls+=1;return raw if calls%3==1 else alternate
            return raw
        with patch.object(module,'read_stable',side_effect=changing),self.assertRaises(CaptureRace):self.capture()
        self.assertEqual(calls,4)

    def test_excess_selector_rows_refuse_before_any_icon_read(self):
        settings=self.fixture(tuple(range(25540,25556)))
        selector=self.fs.read(settings.norad.satellite)+b'99999 "" color=Yellow trail={orbit,-30,30,5} image=iss.png\n'
        tle=self.fs.read(settings.norad.satellite+'.tle')+sample_for(99999,'SYNTHETIC')
        self.fs.write(settings.norad.satellite,selector);self.fs.write(settings.norad.satellite+'.tle',tle)
        state=json.loads(self.fs.read(settings.state));row=state['products']['norad']
        row.update(satellite_sha256=hashlib.sha256(selector).hexdigest(),tle_sha256=hashlib.sha256(tle).hexdigest(),body_sha256=hashlib.sha256(selector+b'\0'+tle).hexdigest())
        self.fs.write(settings.state,json.dumps(state).encode())
        from configurator import astronomy_capture as module
        original=module.read_stable;icons=[]
        def reading(fs,path,limit):
            if path.startswith('images/'):icons.append(path)
            return original(fs,path,limit)
        with patch.object(module,'read_stable',side_effect=reading),self.assertRaises(CaptureError):self.capture()
        self.assertEqual(icons,[])

    def test_png_palette_transparency_rules_and_valid_profiles(self):
        from configurator.exchange import preview_bytes
        def image(colour,extra=b'',depth=8):
            channels={0:1,2:3,3:1,4:2,6:4}[colour]
            return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,depth,colour,0,0,0))+extra+chunk(b'IDAT',zlib.compress(b'\0'*(1+channels)))+chunk(b'IEND',b'')
        valid=(image(3,chunk(b'PLTE',b'\xff\0\0')),image(3,chunk(b'PLTE',b'\xff\0\0')+chunk(b'tRNS',b'\xff')),image(6),image(0,chunk(b'tRNS',b'\0\0')))
        for raw in valid:self.assertEqual(normalize_icon(raw),raw);self.assertEqual(preview_bytes(raw),raw)
        bad=(image(2,chunk(b'tRNS',b'\0\0'*3)+chunk(b'PLTE',b'\0\0\0')),image(3),image(3,chunk(b'PLTE',b'\0')),image(6,chunk(b'tRNS',b'\0\0')),image(0,chunk(b'PLTE',b'\0\0\0')),image(3,chunk(b'tRNS',b'\xff')+chunk(b'PLTE',b'\0\0\0')),image(2,chunk(b'tRNS',b'\xff\xff'*3)),image(3,chunk(b'PLTE',b'\0\0\0')*2))
        for raw in bad:
            with self.assertRaises(CaptureError):normalize_icon(raw)
            with self.assertRaises(ValueError):preview_bytes(raw)

    def test_baseline_and_current_keep_distinct_sixteen_icon_sets(self):
        self.fixture(tuple(range(25540,25556)));first=self.capture();meta=first.metadata
        payload=dict(first.payload)
        for index,name in enumerate(meta['icons'].values()):
            payload[name]=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(bytes((0,index,200,30))))+chunk(b'IEND',b'')
        meta['files']={name:hashlib.sha256(raw).hexdigest() for name,raw in payload.items()}
        second=FrozenAstronomy(json_bytes(meta),tuple(payload.items()))
        w=Workspace();self.addCleanup(w.close);w.register_astronomy(first);w.register_astronomy(second)
        baseline=raw_fields(View(norad_id=first.identity),sys.executable);current=raw_fields(View(norad_id=second.identity),sys.executable)
        record,blobs=pack(current,baseline,SAMPLE.read_bytes(),w)
        self.assertEqual(set(record['astronomy']),{first.identity,second.identity});self.assertLessEqual(len(blobs),64)
        store=RecoveryStore(self.root);session=store.new_session();self.addCleanup(session.close)
        import asyncio
        asyncio.run(session.checkpoint(record,blobs));session.close()
        restored=store.load(session.identity)
        self.assertEqual({item.identity for item in restored.astronomy},{first.identity,second.identity})
