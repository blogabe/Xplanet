"""Bounded native orbital guides and complete sampled-date policy."""
from configurator.resources import identity
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys,tempfile,unittest
from configurator.model import View,SYSTEMS,SYSTEM_PERIOD_DAYS,parse_saved_view,recognized_body
from configurator.library import save_named
from configurator.workspace import open_view,configuration_issues

class OrbitTests(unittest.TestCase):
    def scene(self,**changes):return replace(View(target='jupiter',projection='space',composition='system',orbit_paths='on',time_mode='fixed',utc='2000-01-01T12:00:00Z'),**changes)

    def test_exact_bounded_native_options_apply_to_companions_only(self):
        for target,members in SYSTEMS.items():
            view=self.scene(target=target,orbit_color='yellow',orbit_width=3)
            body=view.body();self.assertTrue(recognized_body(body))
            self.assertEqual(body.count(b'draw_orbit=true\n'),len(members))
            self.assertEqual(body.count(b'orbit={-0.5,0.5,5}\n'),len(members))
            self.assertEqual(body.count(b'orbit_color=yellow\narc_thickness=3\n'),len(members))
            first=body.split(f'[{target}]\n'.encode())[1].split(b'\n\n',1)[0]
            self.assertNotIn(b'draw_orbit',first)
            self.assertFalse(body.endswith(b'\n\n'))
            self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),body).view,view)

    def test_sample_padding_covers_actual_engine_extra_segment_and_avoids_zero_divisions(self):
        self.assertEqual(set(SYSTEM_PERIOD_DAYS),set(SYSTEMS))
        for target,period in SYSTEM_PERIOD_DAYS.items():
            n_before=int(abs(-360*.5/5+.5));n_after=int(abs(360*.5/5+.5))
            self.assertGreater(n_before,0);self.assertGreater(n_after,0)
            before,after=self.scene(target=target).orbit_padding()
            self.assertGreaterEqual(before,.5*period)
            self.assertGreaterEqual(after,period*(.5+.5/n_after))
            self.assertGreaterEqual(after,period*.5/n_before)
            self.assertLessEqual(len(SYSTEMS[target])*(n_before+n_after+2),657)
        self.assertEqual(self.scene(target='saturn').orbit_padding(),(276,283))

    def test_complete_fixed_time_footprint_is_inside_policy_for_each_family(self):
        for target in SYSTEMS:
            view=self.scene(target=target);before,after=view.orbit_padding()
            lower=datetime(1800,1,1,tzinfo=timezone.utc)+timedelta(days=before)
            upper=datetime(2100 if target=='pluto' else 2201,1,1,tzinfo=timezone.utc)-timedelta(days=after)
            for date in (lower,upper-timedelta(seconds=1)):
                replace(view,utc=date.strftime('%Y-%m-%dT%H:%M:%SZ')).validate()
            for date in (lower-timedelta(seconds=1),upper):
                bad=replace(view,utc=date.strftime('%Y-%m-%dT%H:%M:%SZ'))
                with self.assertRaisesRegex(ValueError,'Orbital path samples'):bad.body()
                self.assertTrue(any(i.severity=='blocking' and i.field=='utc' for i in configuration_issues(bad,sys.executable)))
                replace(bad,orbit_paths='off').validate()

    def test_inactive_settings_do_not_add_paths_or_footprint_limits_and_reopen_losslessly(self):
        active=self.scene(target='saturn',orbit_color='red',orbit_width=3,utc='1800-01-01T00:00:00Z')
        for inactive in (replace(active,projection='orthographic'),replace(active,composition='target'),replace(active,target='earth')):
            inactive.validate();self.assertFalse(inactive.uses_orbits())
            self.assertNotIn(b'draw_orbit=',inactive.body())
            self.assertEqual(inactive.render_digest(),replace(inactive,orbit_paths='off',orbit_color='cyan',orbit_width=1).render_digest())
            self.assertEqual(parse_saved_view(inactive.definition('/renderer').encode(),inactive.body()).view,inactive)
        replace(active,time_mode='now').validate()

    def test_v11_and_earlier_scenes_keep_defaults_and_new_settings_require_v12(self):
        old=View(target='jupiter',projection='space',composition='system',satellite_scale=3,geometry='800x600')
        self.assertEqual(parse_saved_view(old.definition('/renderer',version=11).encode(),old.body()).view,old)
        for view in (self.scene(),View(orbit_color='red'),View(orbit_width=2)):
            with self.assertRaisesRegex(ValueError,'Older formats'):view.definition('/renderer',version=11)
        legacy=View(geometry='800x600')
        self.assertEqual(parse_saved_view(legacy.definition('/renderer',version=10).encode(),legacy.body()).view,legacy)

    def test_invalid_style_and_native_mutation_fail_closed(self):
        for width in (0,4,1.5,'bad',float('nan'),float('inf')):
            bad=self.scene(orbit_width=width);self.assertTrue(any(i.severity=='blocking' and i.field=='orbit_width' for i in bad.issues()))
            self.assertIsInstance(bad.appearance_summary(),str)
            with self.assertRaises(ValueError):bad.body()
        for changes in ({'orbit_color':'$(touch bad)'},{'orbit_paths':'custom'}):
            with self.assertRaises(ValueError):self.scene(**changes).body()
        view=self.scene();definition=view.definition('/renderer').encode()
        for body in (view.body().replace(b'-0.5,0.5,5',b'-100,100,0'),view.body()+b'[earth]\ndraw_orbit=true\n',view.body().replace(b'arc_thickness=1',b'arc_thickness=10',1)):
            self.assertFalse(recognized_body(body))
            with self.assertRaises(ValueError):parse_saved_view(definition,body)

    def test_named_scene_copy_keeps_path_settings_and_source(self):
        view=self.scene(orbit_color='green',orbit_width=2,satellite_scale=3)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();source=save_named(root/'paths.conf',view,sys.executable);before=source.read_bytes()
            doc=open_view(source);self.assertEqual(doc.view,view)
            copy=save_named(root/'copy.conf',doc.view,sys.executable,config_bytes=doc.config)
            self.assertEqual(open_view(copy).view,view);self.assertEqual(source.read_bytes(),before)


    def test_preview_identity_tracks_active_paths_and_style_only(self):
        from configurator.workspace import PreviewSnapshot,renderer_path
        view=self.scene(orbit_color='yellow',orbit_width=2)
        snap=PreviewSnapshot(Path('/unused-image'),view,renderer_path(sys.executable),view.render_digest(),'2000-01-01T00:00:00Z','',binary_identity=identity(Path(sys.executable).resolve()))
        self.assertTrue(snap.matches(view,sys.executable,view.body()))
        self.assertFalse(snap.matches(replace(view,orbit_width=3),sys.executable,view.body()))
        self.assertFalse(snap.matches(replace(view,orbit_paths='off'),sys.executable,view.body()))
        inactive=replace(view,projection='orthographic')
        snap=replace(snap,view=inactive,config_digest=inactive.render_digest())
        self.assertTrue(snap.matches(replace(inactive,orbit_color='green',orbit_width=3),sys.executable,inactive.body()))


class OrbitFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_footprint_conflict_keeps_prior_image_and_never_spawns(self):
        from unittest.mock import AsyncMock,patch
        from configurator.workspace import Workspace,PreviewSnapshot,renderer_path
        w=Workspace();self.addCleanup(w.close)
        valid=View(target='saturn',projection='space',composition='system')
        image=w.root/'previous'/'image.png';image.parent.mkdir();image.write_bytes(b'last successful image fixture')
        previous=PreviewSnapshot(image,valid,renderer_path(sys.executable),valid.render_digest(),'2000-01-01T00:00:00Z','',binary_identity=identity(Path(sys.executable).resolve()));w.latest=previous
        bad=replace(valid,orbit_paths='on',time_mode='fixed',utc='1800-01-01T00:00:00Z')
        with patch('configurator.workspace.asyncio.create_subprocess_exec',new_callable=AsyncMock) as spawn:
            with self.assertRaisesRegex(ValueError,'Orbital path samples'):await w.preview(bad,sys.executable)
            spawn.assert_not_awaited()
        self.assertIs(w.latest,previous);self.assertEqual(image.read_bytes(),b'last successful image fixture');self.assertFalse(w.busy);self.assertIsNone(w.process)
