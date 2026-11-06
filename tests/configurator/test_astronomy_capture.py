"""Only synthetic/disposable producer fixtures; never real source operations."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from unittest.mock import patch

from configurator.astronomy_capture import capture_existing, FrozenAstronomy, satellite_pair, eclipse_pair, FILES
from configurator.cloud_capture import CaptureError, CaptureRace, json_bytes
from totalmarker.features import norad, eclipse
from totalmarker.http import Fetcher, Response
from tests.support import Sandbox, ScriptedTransport
from tests.test_norad import SAMPLE, EPOCH
from tests.test_eclipse import TOTAL, TOTAL_URL


class AstronomyCaptureTests(Sandbox):
    def norad(self):
        settings=self.config('NoradEnabled=On\nNoradCatalogIds=25544\n')
        norad.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(Response(200,{},SAMPLE))),now=EPOCH+10)
        return settings

    def eclipse(self, active=True):
        settings=self.config('EclipseEnabled=On\nEclipsePathURL='+TOTAL_URL+'\n')
        path=eclipse.parse_path(TOTAL,TOTAL_URL)
        eclipse.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(Response(200,{},TOTAL))),now=path.start_at-(3600 if active else 10*86400))
        return settings,path

    def capture(self,product,now):return capture_existing(self.root.resolve(),product,'config.ini',now=now)
    def inventory(self):return {str(path.relative_to(self.root)):(path.read_bytes(),path.stat().st_mtime_ns) for path in self.root.rglob('*') if path.is_file()}
    def edit_state(self,settings,edit):
        state=json.loads(self.fs.read(settings.state));edit(state['products']);self.fs.write(settings.state,json.dumps(state).encode())

    def test_norad_capture_is_readonly_and_no_network_metadata_is_redacted(self):
        settings=self.norad();self.edit_state(settings,lambda p:p['norad'].update(last_error={'at':EPOCH+10,'message':'PRIVATE_TOKEN'}))
        before=self.inventory()
        with patch('totalmarker.http.Fetcher.fetch',side_effect=AssertionError('network forbidden')):frozen=self.capture('norad',EPOCH+20)
        self.assertEqual(before,self.inventory());self.assertEqual(set(frozen.files()),{'frozen-norad.json',*FILES['norad']})
        self.assertEqual(frozen.metadata['selected_ids'],[25544]);self.assertEqual(frozen.metadata['oldest_epoch_at'],EPOCH)
        self.assertNotIn(str(self.root).encode(),frozen.provenance);self.assertNotIn(b'PRIVATE_TOKEN',frozen.provenance)
        self.assertEqual(repr(frozen),'FrozenAstronomy()')

    def test_norad_is_now_earth_only_and_expires_without_relabeling(self):
        self.norad();frozen=self.capture('norad',EPOCH+20)
        self.assertTrue(frozen.availability(target='earth',time_mode='now',now=EPOCH+50)[0])
        self.assertFalse(frozen.availability(target='mars',time_mode='now',now=EPOCH+50)[0])
        self.assertFalse(frozen.availability(target='earth',time_mode='fixed',utc='2001-10-13T00:00:00Z',now=EPOCH+50)[0])
        limit=frozen.metadata['max_age_seconds']
        self.assertTrue(frozen.availability(target='earth',time_mode='now',now=EPOCH+limit)[0])
        self.assertFalse(frozen.availability(target='earth',time_mode='now',now=EPOCH+limit+1)[0])
        self.assertFalse(frozen.availability(target='earth',time_mode='now',now=EPOCH-86401)[0])

    def test_stale_norad_checksum_and_oldest_epoch_are_not_accepted(self):
        settings=self.norad()
        with self.assertRaises(CaptureError):self.capture('norad',EPOCH+settings.norad.max_age+1)
        self.edit_state(settings,lambda p:p['norad'].update(oldest_epoch_at=EPOCH+1))
        with self.assertRaises(CaptureError):self.capture('norad',EPOCH+20)

    def test_pair_hash_mismatch_pending_journal_and_source_links_fail_closed(self):
        settings=self.norad();output=self.root/settings.norad.satellite;original=output.read_bytes();output.write_bytes(original+b'changed')
        with self.assertRaises(CaptureRace):self.capture('norad',EPOCH+20)
        output.write_bytes(original)
        journal=self.root/settings.eclipse.journal;journal.parent.mkdir(parents=True,exist_ok=True);journal.write_text('never read private journal')
        with self.assertRaisesRegex(CaptureError,'Pending'):self.capture('norad',EPOCH+20)
        journal.unlink();output.unlink();outside=self.root/'outside';outside.write_bytes(original);output.symlink_to(outside)
        with self.assertRaises(CaptureError):self.capture('norad',EPOCH+20)
        self.assertEqual(outside.read_bytes(),original)

    def test_state_and_output_races_are_bounded(self):
        self.norad();from configurator import astronomy_capture as module
        original=module.read_state;calls=0
        def changing(*args):
            nonlocal calls
            result=original(*args);calls+=1
            if calls%2==0:result['products']['norad']['checked_at']+=1
            return result
        before=self.inventory()
        with patch.object(module,'read_state',side_effect=changing),self.assertRaises(CaptureRace):self.capture('norad',EPOCH+20)
        self.assertEqual(calls,4);self.assertEqual(before,self.inventory())

    def test_unsupported_norad_icon_is_refused_not_silently_dropped(self):
        self.norad();frozen=self.capture('norad',EPOCH+20);first,second=(data for _,data in frozen.payload)
        for changed in (first.replace(b' color=',b' image=private.png color='),first.replace(b'25544 ',b'12345 '),first+first):
            with self.assertRaises(CaptureError):satellite_pair(changed,second,frozen.metadata)

    def test_eclipse_capture_strips_current_countdowns_preserves_dated_prediction(self):
        settings,path=self.eclipse();before=self.inventory()
        with patch('totalmarker.http.Fetcher.fetch',side_effect=AssertionError('network forbidden')):frozen=self.capture('eclipse',path.start_at-1800)
        self.assertEqual(before,self.inventory());self.assertTrue(frozen.metadata['wallclock_notices_removed'])
        data=dict(frozen.payload);self.assertNotIn(b'position=pixel',data[FILES['eclipse'][0]])
        self.assertNotIn(b'begin in',data[FILES['eclipse'][0]]);self.assertIn(b'11:30 UTC',data[FILES['eclipse'][0]])
        self.assertIn(b'# center path',data[FILES['eclipse'][1]])
        meta=frozen.metadata;self.assertNotEqual(meta['source_hashes'][FILES['eclipse'][0]],meta['files'][FILES['eclipse'][0]])

    def test_eclipse_event_coverage_inclusive_and_not_weather_now_policy(self):
        _,path=self.eclipse();frozen=self.capture('eclipse',path.start_at-1800)
        self.assertFalse(frozen.availability(target='earth',time_mode='now',now=path.start_at-1)[0])
        for moment in (path.start_at,path.end_at):
            self.assertTrue(frozen.availability(target='earth',time_mode='now',now=moment)[0])
            utc=datetime.fromtimestamp(moment,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            self.assertTrue(frozen.availability(target='earth',time_mode='fixed',utc=utc)[0])
        self.assertFalse(frozen.availability(target='earth',time_mode='now',now=path.end_at+1)[0])
        self.assertFalse(frozen.availability(target='moon',time_mode='fixed',utc='2027-08-02T11:32:00Z')[0])
        self.assertFalse(frozen.availability(target='earth',time_mode='fixed',utc='not a date')[0])

    def test_inactive_empty_eclipse_is_not_reconstructed_from_state(self):
        settings,path=self.eclipse(False)
        with self.assertRaisesRegex(CaptureError,'incomplete'):self.capture('eclipse',path.start_at-9*86400)

    def test_eclipse_unknown_pixels_coordinates_and_event_mismatch_rejected(self):
        settings,path=self.eclipse();frozen=self.capture('eclipse',path.start_at-1800)
        first,second=(data for _,data in frozen.payload);meta=frozen.metadata
        for changed in (first+b'-55 1 "secret" position=pixel\n',re.sub(rb'\n[+-]?[0-9]+\.[0-9]+ ',b'\n9999 ',first,count=1),first.replace(b'11:30 UTC',b'00:01 UTC')):
            with self.assertRaises(CaptureError):eclipse_pair(changed,second,meta,source=True)
        for values in ({'event_date':'2027-08-03'},{'start_at':path.end_at+1},{'kind':'Partial'}):
            with self.assertRaises(CaptureError):eclipse_pair(first,second,{**meta,**values})

    def test_frozen_manifest_payload_tampering_and_quota_refused(self):
        self.norad();frozen=self.capture('norad',EPOCH+20)
        with self.assertRaises(CaptureError):FrozenAstronomy(frozen.provenance,tuple(reversed(frozen.payload)))
        with self.assertRaises(CaptureError):FrozenAstronomy(frozen.provenance,((frozen.payload[0][0],b'changed'),frozen.payload[1]))
        for changes in ({'private_path':'secret'},{'schema':2},{'captured_at':True}):
            with self.assertRaises(CaptureError):FrozenAstronomy(json_bytes({**frozen.metadata,**changes}),frozen.payload)
        with self.assertRaises(CaptureError):FrozenAstronomy(b' '*9000,frozen.payload)

    def test_frozen_eclipse_validates_hash_consistent_malicious_payload(self):
        _,path=self.eclipse();frozen=self.capture('eclipse',path.start_at-1800)
        name,raw=frozen.payload[0];raw+=b'1 2 "secret" image=/private/data\n';meta=frozen.metadata;meta['files'][name]=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(CaptureError):FrozenAstronomy(json_bytes(meta),((name,raw),frozen.payload[1]))

    def test_malformed_saved_metadata_and_capture_times_refuse_normally(self):
        settings=self.norad();original=self.fs.read(settings.state)
        for changes in ({'selected_ids':[[1]]},{'selected_ids':[True]},{'oldest_epoch_at':float('nan')},{'count':17}):
            self.fs.write(settings.state,original)
            self.edit_state(settings,lambda products:products['norad'].update(changes))
            with self.assertRaises(CaptureError):self.capture('norad',EPOCH+20)
        self.fs.write(settings.state,original)
        for moment in (True,float('nan'),-1):
            with self.assertRaises(CaptureError):self.capture('norad',moment)

    def test_missing_coherent_pair_and_empty_selection_are_not_fabricated(self):
        settings=self.norad();original=self.fs.read(settings.state)
        self.edit_state(settings,lambda products:products['norad'].pop('body_sha256'))
        with self.assertRaisesRegex(CaptureError,'coherent'):self.capture('norad',EPOCH+20)
        self.fs.write(settings.state,original)
        self.edit_state(settings,lambda products:products['norad'].update(selected_ids=[],count=0,oldest_epoch_at=None))
        with self.assertRaises(CaptureError):self.capture('norad',EPOCH+20)

    def test_accepted_norad_styles_and_rejected_numeric_options(self):
        self.norad();frozen=self.capture('norad',EPOCH+20);first,second=(data for _,data in frozen.payload)
        styled=first.rstrip(b'\n')+b' transparent={0,10,255} altcirc=45 align=below\n'
        self.assertEqual(satellite_pair(styled,second,frozen.metadata),(styled,second))
        for changed in (styled.replace(b'altcirc=45',b'altcirc=91'),styled.replace(b'0,10,255',b'0,10,256'),styled.replace(b'color=Yellow',b'color=256,0,0'),first.replace(b',30,5}',b',30,0}')):
            with self.assertRaises(CaptureError):satellite_pair(changed,second,frozen.metadata)
        with self.assertRaises(CaptureError):satellite_pair(first,second,{**frozen.metadata,'selected_ids':[[1]]})

    def test_publication_becoming_pending_after_read_keeps_source_unchanged(self):
        self.norad();before=self.inventory()
        with patch('configurator.astronomy_capture.publication_pending',side_effect=[False,True]),self.assertRaisesRegex(CaptureError,'became pending'):
            self.capture('norad',EPOCH+20)
        self.assertEqual(before,self.inventory())

    def test_eclipse_requires_full_coverage_and_valid_rgb(self):
        _,path=self.eclipse();frozen=self.capture('eclipse',path.start_at-1800)
        first,second=(data for _,data in frozen.payload);meta=frozen.metadata
        for changed in (first.replace(b'color=Grey',b'color=999,0,0'),first.replace(b'11:34 UTC',b'11:32 UTC')):
            with self.assertRaises(CaptureError):eclipse_pair(changed,second,meta)
        for changes in ({'start_at':meta['start_at']-60},{'end_at':None},{'start_at':True}):
            with self.assertRaises(CaptureError):eclipse_pair(first,second,{**meta,**changes})

    def test_cross_midnight_incomplete_old_pair_remains_refused(self):
        _,path=self.eclipse();frozen=self.capture('eclipse',path.start_at-1800)
        first,second=(data for _,data in frozen.payload)
        midnight=datetime(2027,8,3,tzinfo=timezone.utc).timestamp()
        with self.assertRaises(CaptureError):eclipse_pair(first,second,{**frozen.metadata,'end_at':midnight+60})

    def test_invalid_now_is_unavailable_for_both_products(self):
        self.norad();norad_frozen=self.capture('norad',EPOCH+20)
        _,path=self.eclipse();eclipse_frozen=self.capture('eclipse',path.start_at-1800)
        for frozen in (norad_frozen,eclipse_frozen):
            for value in (True,float('nan'),-1):
                self.assertFalse(frozen.availability(target='earth',time_mode='now',now=value)[0])

    def test_mutable_nested_payload_is_refused(self):
        self.norad();frozen=self.capture('norad',EPOCH+20)
        with self.assertRaises(CaptureError):FrozenAstronomy(frozen.provenance,tuple(list(row) for row in frozen.payload))

    def test_product_scoped_files_allow_combined_named_snapshots_without_collision(self):
        self.norad();norad_frozen=self.capture('norad',EPOCH+20)
        _,path=self.eclipse();eclipse_frozen=self.capture('eclipse',path.start_at-1800)
        files={**norad_frozen.files('scene.'),**eclipse_frozen.files('scene.')}
        self.assertEqual(len(files),6)
        for frozen in (norad_frozen,eclipse_frozen):
            clone=FrozenAstronomy.from_files(files,frozen.product,'scene.')
            self.assertEqual(clone,frozen)
            self.assertEqual(clone.byte_size,len(clone.provenance)+sum(len(raw) for _,raw in clone.payload))
        for product in ('norad','eclipse'):
            with self.assertRaises(CaptureError):FrozenAstronomy.from_files(files,product,'../')
            with self.assertRaises(CaptureError):FrozenAstronomy.from_files({},product)
        altered=dict(files);altered['scene.frozen-norad.json']=eclipse_frozen.provenance
        with self.assertRaises(CaptureError):FrozenAstronomy.from_files(altered,'norad','scene.')
