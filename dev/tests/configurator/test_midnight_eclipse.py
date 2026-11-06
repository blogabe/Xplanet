"""Explicitly synthetic midnight timestamps exercise rollover, not eclipse science."""
from dataclasses import replace
from datetime import datetime,timezone
import asyncio,hashlib,sys
from configurator.astronomy_capture import local_eclipse,capture_existing,eclipse_pair,FrozenAstronomy,FILES
from configurator.cloud_capture import CaptureError,json_bytes
from configurator.model import View,SAMPLE
from configurator.workspace import Workspace,open_view
from configurator.library import save_named
from configurator.handoff import create_plan,stage_plan,check_bundle
from configurator.selection import stage_revision,read_revision
from configurator.recovery import pack,raw_fields,RecoveryStore
from totalmarker.features import eclipse
from totalmarker.http import Fetcher,Response
from tests.support import Sandbox, ScriptedTransport
from tests.test_eclipse import TOTAL, TOTAL_URL

MIDNIGHT=TOTAL.replace(b'11:30',b'23:58').replace(b'11:32',b'00:00').replace(b'11:34',b'00:02')

class MidnightEclipseTests(Sandbox):
    def frozen(self,first_row_date="2027-08-02"):
        source=self.root/'midnight.html';source.write_bytes(MIDNIGHT)
        return local_eclipse(source,TOTAL_URL,first_row_date=first_row_date,now=1800000000)
    def test_exact_coverage_both_days_and_reuse_after_wallclock_event(self):
        item=self.frozen();meta=item.metadata
        self.assertEqual(item.window_token,'2027-08-02T23:58:00Z/2027-08-03T00:02:00Z')
        for utc,allowed in (('2027-08-02T23:57:59Z',False),('2027-08-02T23:58:00Z',True),('2027-08-03T00:00:00Z',True),('2027-08-03T00:02:00Z',True),('2027-08-03T00:02:01Z',False)):
            self.assertEqual(item.availability(target='earth',time_mode='fixed',utc=utc,now=2000000000)[0],allowed)
            view=View(eclipse_layer='captured',eclipse_id=item.identity,eclipse_window=item.window_token,time_mode='fixed',utc=utc)
            self.assertEqual('eclipse' in view.uses_astronomy(),allowed)
        self.assertNotIn(b'position=pixel',dict(item.payload)[FILES['eclipse'][0]])
    def test_invalid_rollover_cadence_and_metadata_refuse(self):
        source=self.root/'bad.html'
        for raw in (MIDNIGHT.replace(b'00:02',b'23:56'),MIDNIGHT.replace(b'00:00',b'00:01'),MIDNIGHT.replace(b'00:02',b'00:00')):
            source.write_bytes(raw)
            with self.assertRaises(CaptureError):local_eclipse(source,TOTAL_URL)
        item=self.frozen()
        for change in ({'end_at':item.metadata['end_at']+86400},{'start_at':item.metadata['start_at']-86400},{'event_date':'2027-08-03'}):
            meta=item.metadata;meta.update(change)
            with self.assertRaises(CaptureError):FrozenAstronomy(json_bytes(meta),item.payload)
        first,second=(data for _,data in item.payload)
        for changed in (first.replace(b'00:00',b'23:56'),first.replace(b'00:02',b'00:00')):
            with self.assertRaises(CaptureError):eclipse_pair(changed,second,item.metadata)
    def test_producer_midnight_without_independent_day_is_refused(self):
        settings=self.config('EclipseEnabled=On\nEclipsePathURL='+TOTAL_URL+'\n');path=eclipse.parse_path(MIDNIGHT,TOTAL_URL)
        eclipse.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(Response(200,{},MIDNIGHT))),now=path.start_at-30)
        with self.assertRaisesRegex(CaptureError,'Ambiguous midnight'):capture_existing(self.root.resolve(),'eclipse','config.ini',now=path.start_at-10)

    def test_explicit_day_previous_to_event_and_missing_wrong_dates(self):
        source=self.root/'midnight.html';source.write_bytes(MIDNIGHT);before=source.read_bytes(),source.stat().st_mtime_ns
        for date in (None,'','2027-07-31','2027-08-03','2027-02-30',True):
            with self.assertRaises(CaptureError):local_eclipse(source,TOTAL_URL,first_row_date=date)
        item=local_eclipse(source,TOTAL_URL,first_row_date='2027-08-01')
        self.assertEqual(item.window_token,'2027-08-01T23:58:00Z/2027-08-02T00:02:00Z')
        self.assertEqual(item.metadata['origin']['first_row_utc_date'],'2027-08-01')
        self.assertTrue(item.availability(target='earth',time_mode='fixed',utc='2027-08-02T00:00:00Z')[0])
        self.assertEqual(before,(source.read_bytes(),source.stat().st_mtime_ns))
        meta=item.metadata;del meta['origin']['first_row_utc_date'];meta['schema']=2
        with self.assertRaises(CaptureError):FrozenAstronomy(json_bytes(meta),item.payload)

    def test_named_scene_recovery_and_immutable_handoff_keep_both_dates(self):
        for day,utc in (('2027-08-01','2027-08-02T00:00:00Z'),('2027-08-02','2027-08-03T00:00:00Z')):
            item=self.frozen(day);(self.root/'config').mkdir(exist_ok=True)
            view=View(eclipse_layer='captured',eclipse_id=item.identity,eclipse_window=item.window_token,time_mode='fixed',utc=utc)
            source=save_named(self.root/('config/scenes/midnight'+day[-1]+'.conf'),view,sys.executable,astronomy={'eclipse':item})
            self.assertEqual(open_view(source).astronomy,(item,))
            plan=create_plan(self.root,source,sys.executable,'1920x1080');bundle=stage_plan(plan,self.root/('review'+day[-1]));check_bundle(self.root,bundle)
            revision=stage_revision(self.root,bundle);record=read_revision(self.root,revision)
            args=record['proposed_argv'];self.assertIn('-timewarp',args);self.assertEqual(args[args.index('-timewarp')+1],'0')
            w=Workspace();self.addCleanup(w.close);w.register_astronomy(item)
            fields=raw_fields(view,sys.executable);store=RecoveryStore(self.root);session=store.new_session();self.addCleanup(session.close)
            asyncio.run(session.checkpoint(*pack(fields,fields,SAMPLE.read_bytes(),w)));session.close()
            self.assertEqual(store.load(session.identity).astronomy,(item,))
            from configurator.comparison import plan as compare
            review=compare(replace(view,map_family='world'),kind='months',months=('01','06','12'))
            self.assertTrue(all(v.uses_astronomy()==('eclipse',) for v in review.views))
