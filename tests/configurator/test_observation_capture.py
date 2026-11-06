"""Frozen observation adapter tests use only disposable producer fixtures."""
import hashlib,json,os,struct,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
from configurator.model import ROOT
from configurator.observation_capture import (capture_existing,FrozenObservations,CaptureError,CaptureRace,native,names,png,describe,json_bytes)
from totalmarker.quake_geojson import render_marker as quake_marker
from totalmarker.volcano_cap import render_marker as volcano_marker
from totalmarker.storm_model import render_marker as storm_marker,render_arc


def icon():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\0\0'))+chunk(b'IEND',b'')


from tests.configurator.support_observations import ObservationCaptureFixture

class ObservationCaptureTests(ObservationCaptureFixture, unittest.TestCase):



    def test_capture_all_products_binds_hashes_and_sources_without_writes(self):
        self.state['products']['quake']['last_error']={'at':1700000001,'message':'PrivateErrorToken'};self.save_state()
        before=self.inventory()
        with patch('totalmarker.http.Fetcher.fetch',side_effect=AssertionError('network forbidden')):frozen=self.capture()
        self.assertEqual(before,self.inventory());self.assertEqual(set(frozen.metadata['products']),{'quake','storm','volcano'})
        self.assertEqual(frozen.freshness('quake',1700000100),'unknown')
        self.assertEqual(frozen.freshness('storm',1700000100),'current');self.assertEqual(frozen.freshness('storm',1700004000),'stale')
        self.assertEqual(frozen.freshness('volcano',1700000100),'unknown')
        self.assertEqual(frozen.metadata['products']['quake']['source_at'],1699999950)
        self.assertNotIn(str(self.root).encode(),frozen.provenance);self.assertNotIn(b'PrivateErrorToken',frozen.provenance)
        self.assertEqual(repr(frozen),'FrozenObservations()')
        self.assertIn('Provider access was not checked',describe(frozen))

    def test_storm_pair_and_every_pending_product_journal_fail_closed(self):
        (self.root/'arcs/storm').write_bytes(b'changed')
        with self.assertRaises(CaptureRace):self.capture(('storm',))
        for name in ('pending.json','quake-pending.json','santa-pending.json'):
            path=self.root/'.state/totalmarker'/name;path.write_text('private journal contents')
            with self.assertRaisesRegex(CaptureError,'Pending'):self.capture(('quake',))
            path.unlink()

    def test_source_record_and_icon_races_are_bounded_and_preserve_source(self):
        from configurator import observation_capture as module
        original=module.read_state;count=0
        def changing(*args):
            nonlocal count
            state=original(*args);count+=1
            if count%2==0:state['products']['quake']['checked_at']+=1
            return state
        before=self.inventory()
        with patch.object(module,'read_state',side_effect=changing),self.assertRaises(CaptureRace):self.capture(('quake',))
        self.assertEqual(count,4);self.assertEqual(before,self.inventory())

    def test_icons_are_frozen_and_prefixing_does_not_rewrite_label_text(self):
        self.config.write_text(self.config.read_text().replace('image = ""','image = "images/icon.png"'))
        (self.root/'images/icon.png').write_bytes(icon())
        self.install('quake',quake_marker(b'1 2 "image=observed-quake.png" color=Red image=images/icon.png\n',1700000000));self.save_state()
        frozen=self.capture(('quake',));files=frozen.files('summer.')
        self.assertIn(b'"image=observed-quake.png"',files['summer.observed-quake.markers'])
        self.assertIn(b' image=summer.observed-quake.png',files['summer.observed-quake.markers'])
        self.assertEqual(FrozenObservations.from_files(files,'summer.'),frozen)
        bad=dict(files);bad['summer.observed-quake.markers']=bad['summer.observed-quake.markers'].replace(b'image=summer.observed-quake.png',b'image=winter.observed-quake.png')
        with self.assertRaises(CaptureError):FrozenObservations.from_files(bad,'summer.')
        (self.root/'images/icon.png').write_bytes(b'not a png')
        with self.assertRaises(CaptureError):self.capture(('quake',))

    def test_strict_native_grammar_rejects_unsafe_unknown_and_oversized_inputs(self):
        for row in (b'1 2 "X" color=Red image=/private/icon.png\n',b'1 2 "X" color=Red font=/tmp/font\n',b'1 2 "X" color=Red color=Blue\n',b'91 2 "X" color=Red\n',b'1 2 "X" color=Red symbolsize=inf\n',b'1 2 "X" color=Red transparent=999,0,0\n',b'1 2 "X" color=Red label=unsafe\n'):
            with self.subTest(row=row),self.assertRaises(CaptureError):native(quake_marker(row,1700000000),'quake',source=True)
        with self.assertRaises(CaptureError):native(b'x'*300000,'quake')
        with self.assertRaises(CaptureError):native(render_arc(b'1 2 3 4 image=icon.png\n',1700000000),'storm',True,source=True)
        normalized,_=native(quake_marker(b'1 2 "Quote \\" and slash \\\\" color=Red\n',1700000000),'quake',source=True)
        self.assertEqual(native(normalized,'quake')[0],normalized)
        self.assertNotIn(b'\\',normalized)
        with self.assertRaisesRegex(CaptureError,'Unsafe older'):
            native(b'# Frozen TotalMarker quake markers v1\n1 2 "Quote \\" text" color=Red\n','quake')
        transparent,_=native(quake_marker(b'1 2 "X" color=Red image=icon.png transparent={0,30,255}\n',1700000000),'quake',source=True,icon='icon.png')
        self.assertIn(b'transparent={0,30,255}',transparent)
        self.assertEqual(native(transparent,'quake')[0],transparent)
        for value in ('30','0,30,255','{256,0,0}','{-1,0,0}','{0,0}'):
            with self.subTest(value=value),self.assertRaisesRegex(CaptureError,'RGB color key'):
                native(quake_marker(f'1 2 \"X\" color=Red transparent={value}\n'.encode(),1700000000),'quake',source=True)
        self.assertEqual(native(transparent,'quake')[0],transparent)


    def test_malformed_manifest_hashes_links_empty_data_and_failed_source_facts(self):
        frozen=self.capture(('quake',))
        with self.assertRaises(CaptureError):FrozenObservations(frozen.provenance,((names('quake')[0],b'changed'),))
        with self.assertRaises(CaptureError):FrozenObservations(b'['*10000,())
        marker=self.root/'markers/quake';marker.unlink();marker.symlink_to(self.root/'markers/volcano')
        with self.assertRaises(CaptureError):self.capture(('quake',))
        marker.unlink();self.install('quake',quake_marker(b'\n',1700000000));self.state['products']['quake']['last_outcome']='failed';self.save_state()
        frozen=self.capture(('quake',));self.assertEqual(frozen.metadata['products']['quake']['last_outcome'],'failed')
        self.assertEqual(frozen.metadata['products']['quake']['successful_at'],1700000000)
        self.assertEqual(dict(frozen.payload)[names('quake')[0]],b'# Frozen TotalMarker quake markers v1\n')

class ObservationSceneTests(unittest.TestCase):
    setUp=ObservationCaptureFixture.setUp
    install=ObservationCaptureFixture.install
    save_state=ObservationCaptureFixture.save_state
    capture=ObservationCaptureFixture.capture

    def test_named_and_legacy_saves_reopen_offline_and_preserve_source(self):
        import sys
        from configurator.model import View,recognized_body
        from configurator.library import save_named
        from configurator.workspace import save_view,open_view,configuration_issues
        frozen=self.capture();view=View(quake_layer='captured',volcano_layer='captured',storm_layer='captured',observations_id=frozen.identity,places='on',places_text='0 0 "Static"')
        for save,path in ((save_named,self.root/'library'/'earth.conf'),(save_view,self.root/'legacy')):
            target=save(path,view,sys.executable,observations=frozen)
            doc=open_view(target);self.assertEqual(doc.view,view);self.assertEqual(doc.observations,frozen)
            self.assertTrue(recognized_body(doc.config))
            self.assertFalse(any(i.severity=='blocking' for i in configuration_issues(view,sys.executable,doc.config,None,frozen)))
        (self.root/'markers').rename(self.root/'producer-offline')
        self.assertEqual(open_view(self.root/'library/earth.conf').observations,frozen)
        before={p.name:p.read_bytes() for p in (self.root/'library').iterdir()}
        with self.assertRaises(ValueError):save_named(self.root/'library/earth.conf',view,sys.executable,observations=frozen)
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'library').iterdir()})

    def test_fixed_time_other_body_and_disabled_choices_retain_bytes_but_omit_layers(self):
        from dataclasses import replace
        from configurator.model import View
        from configurator.library import save_named
        from configurator.workspace import open_view
        import sys
        frozen=self.capture();base=View(quake_layer='captured',storm_layer='captured',observations_id=frozen.identity)
        for index,view in enumerate((replace(base,time_mode='fixed'),replace(base,target='saturn'),replace(base,quake_layer='off',storm_layer='off'))):
            self.assertFalse(view.uses_observations());self.assertNotIn(b'observed-',view.body())
            self.assertNotIn(b'updatelabel',view.body())
            self.assertEqual(view.render_digest(),replace(view,observations_id='').render_digest())
            doc=open_view(save_named(self.root/'library'/f'inactive{index}.conf',view,sys.executable,observations=frozen))
            self.assertEqual(doc.view,view);self.assertEqual(doc.observations,frozen)
        with self.assertRaises(ValueError):base.definition(sys.executable,version=9)

    def test_missing_products_and_foreign_references_cannot_be_saved_or_opened(self):
        import sys
        from configurator.model import View,recognized_body
        from configurator.library import save_named
        from configurator.workspace import open_view
        frozen=self.capture(('quake',));view=View(quake_layer='captured',observations_id=frozen.identity)
        with self.assertRaises(ValueError):save_named(self.root/'missing.conf',View(storm_layer='captured',observations_id=frozen.identity),sys.executable,observations=frozen)
        target=save_named(self.root/'library'/'good.conf',view,sys.executable,observations=frozen)
        for wrong in (b'marker_file=other.observed-quake.markers',b'marker_file=/private/file',b'arc_file=good.observed-quake.arcs'):
            content=target.read_bytes().replace(b'marker_file=good.observed-quake.markers',wrong)
            self.assertEqual(recognized_body(content),wrong.startswith(b'marker_file=other.'));target.write_bytes(content)
            with self.assertRaises(ValueError):open_view(target)
            target.write_bytes(view.body('good.'))

    def test_manifest_asset_link_tamper_and_oversize_are_refused(self):
        import sys
        from configurator.model import View
        from configurator.library import save_named
        from configurator.workspace import open_view
        frozen=self.capture(('quake',));view=View(quake_layer='captured',observations_id=frozen.identity)
        target=save_named(self.root/'library'/'good.conf',view,sys.executable,observations=frozen)
        marker=target.parent/'good.observed-quake.markers';original=marker.read_bytes()
        marker.write_bytes(b'x'*300000)
        with self.assertRaises(ValueError):open_view(target)
        marker.unlink();marker.symlink_to(self.root/'markers/quake')
        with self.assertRaises(OSError):open_view(target)
        marker.unlink();marker.write_bytes(original+b'0 0 "Injected" color=Red\n')
        with self.assertRaises(ValueError):open_view(target)


class ObservationIconRaceTests(unittest.TestCase):
    setUp=ObservationCaptureFixture.setUp
    install=ObservationCaptureFixture.install
    save_state=ObservationCaptureFixture.save_state
    capture=ObservationCaptureFixture.capture

    def test_icon_is_rechecked_after_metadata_and_cannot_change_silently(self):
        from configurator import observation_capture as module
        self.config.write_text(self.config.read_text().replace('image = ""','image = "images/icon.png"'))
        (self.root/'images/icon.png').write_bytes(icon())
        self.install('quake',quake_marker(b'1 2 "M6" color=Red image=images/icon.png\n',1700000000));self.save_state()
        original=module.read_stable;count=0
        def read(fs,path,limit):
            nonlocal count
            data=original(fs,path,limit)
            if str(path)=='images/icon.png':
                count+=1
                if count%2==0:return data+b'changed'
            return data
        with patch.object(module,'read_stable',side_effect=read),self.assertRaises(CaptureRace):self.capture(('quake',))
        self.assertEqual(count,4)


import asyncio,sys

class ObservationWorkerTests(unittest.IsolatedAsyncioTestCase):
    setUp=ObservationCaptureFixture.setUp
    install=ObservationCaptureFixture.install
    save_state=ObservationCaptureFixture.save_state
    capture=ObservationCaptureFixture.capture

    async def test_real_worker_capture_retention_budget_and_private_cleanup(self):
        from configurator.model import View
        from configurator.workspace import Workspace
        workspace=Workspace();self.addCleanup(workspace.close)
        frozen=await workspace.capture_observations(str(self.root),'config/totalmarker.toml',('quake','storm'))
        view=View(observations_id=frozen.identity)
        self.assertIs(workspace.observations_for(view),frozen);self.assertFalse(workspace.busy)
        self.assertFalse(list(workspace.root.glob('capture-*')))
        changed=FrozenObservations(json_bytes({**frozen.metadata,'captured_at':frozen.metadata['captured_at']+1}),frozen.payload)
        with patch('configurator.workspace.CAPTURE_BUDGET',frozen.byte_size+1),self.assertRaisesRegex(ValueError,'128 MiB'):
            workspace.register_observations(changed)
        self.assertIs(workspace.observations_for(view),frozen)
        workspace.reset_captures();self.assertEqual(workspace.observations,{})

    async def test_timeout_and_cancel_stop_private_workers_without_new_capture(self):
        from configurator.workspace import Workspace
        original=asyncio.create_subprocess_exec;spawned=[]
        async def slow(*args,**kwargs):
            p=await original(sys.executable,'-c','import time;time.sleep(30)',**kwargs);spawned.append(p);return p
        workspace=Workspace();self.addCleanup(workspace.close)
        with patch('configurator.workspace.asyncio.create_subprocess_exec',side_effect=slow):
            with self.assertRaisesRegex(ValueError,'wait budget'):await workspace.capture_observations('/unused','unused',('quake',),timeout=.05)
            self.assertIsNotNone(spawned[-1].returncode);self.assertFalse(workspace.busy)
            task=asyncio.create_task(workspace.capture_observations('/unused','unused',('quake',)))
            while workspace.process is None:await asyncio.sleep(.001)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertIsNotNone(spawned[-1].returncode);self.assertFalse(workspace.busy)
        self.assertEqual(workspace.observations,{})
        self.assertFalse(list(workspace.root.glob('capture-*')))


class ObservationPrefixSizeTests(unittest.TestCase):
    setUp=ObservationCaptureFixture.setUp
    install=ObservationCaptureFixture.install
    save_state=ObservationCaptureFixture.save_state
    capture=ObservationCaptureFixture.capture

    def test_named_prefix_cannot_publish_a_marker_larger_than_its_reopen_bound(self):
        import sys
        from configurator.model import View
        from configurator.library import save_named
        from configurator.workspace import save_view,open_view
        self.config.write_text(self.config.read_text().replace('image = ""','image = "images/icon.png"'))
        (self.root/'images/icon.png').write_bytes(icon())
        self.install('quake',quake_marker(b'0 0 "" color=Red image=images/icon.png\n'*3000,1700000000));self.save_state()
        frozen=self.capture(('quake',));view=View(quake_layer='captured',observations_id=frozen.identity)
        with self.assertRaisesRegex(CaptureError,'scene prefix'):
            save_named(self.root/'library'/('a'*48+'.conf'),view,sys.executable,observations=frozen)
        self.assertEqual(list((self.root/'library').iterdir()),[])
        short=save_named(self.root/'library/x.conf',view,sys.executable,observations=frozen)
        self.assertEqual(open_view(short).observations,frozen)
        legacy=save_view(self.root/'legacy',view,sys.executable,observations=frozen)
        self.assertEqual(open_view(legacy).observations,frozen)
