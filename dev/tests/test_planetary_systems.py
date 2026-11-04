"""Known system appearance, scale semantics and v11 preservation boundaries."""
from configurator.resources import identity
from dataclasses import replace
from pathlib import Path
import sys,tempfile,unittest
from configurator.model import View,HEADER,V10_HEADER,SYSTEMS,PLANET_MAPS,parse_saved_view,recognized_body
from configurator.library import save_named
from configurator.workspace import open_view,configuration_issues

class SystemTests(unittest.TestCase):
    def test_system_members_have_exact_bundled_textures_and_positive_non_target_scales(self):
        for target,members in SYSTEMS.items():
            view=View(target=target,projection='space',composition='system',satellite_scale=3,grid='30',planet_shade=15)
            with self.subTest(target=target):
                body=view.body();self.assertTrue(recognized_body(body));self.assertFalse(body.endswith(b'\n\n'))
                self.assertEqual(body.count(b'magnify=3\n'),len(members))
                self.assertNotIn(b'magnify=0',body)
                self.assertEqual(view.resource_paths(),[Path(PLANET_MAPS[b]) for b in (target,*members)])
                self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),body).view,view)
                self.assertEqual(view.arguments(),replace(view,composition='target',satellite_scale=1).arguments())
                for member in members:self.assertIn(f'[{member}]\nmap={PLANET_MAPS[member]}\ngrid=false\nmagnify=3\n'.encode(),body)
                self.assertEqual(body.count(b'grid=true'),1)
                self.assertIn(b'[default]\nshade=30\n',body)
                self.assertIn(f'[{target}]\nmap={PLANET_MAPS[target]}\nshade=15\n'.encode(),body)

    def test_defaults_and_v10_native_files_stay_compatible(self):
        for view in (View(geometry='800x600'),View(target='jupiter',projection='space',geometry='800x600'),View(target='europa',projection='space',observer='jupiter',geometry='800x600')):
            body=view.body();old=view.definition('/renderer',version=10).encode()
            self.assertTrue(old.startswith(V10_HEADER.encode()))
            self.assertEqual(parse_saved_view(old,body).view,view)
            self.assertNotIn(b'system appearance',body)
            self.assertTrue(view.definition('/renderer').startswith(HEADER))
        for view in (View(composition='system'),View(satellite_scale=2)):
            with self.assertRaisesRegex(ValueError,'Older formats'):view.definition('/renderer',version=10)

    def test_inactive_system_choices_survive_save_reopen_and_render_digest(self):
        active=View(target='jupiter',projection='space',composition='system',satellite_scale=4,places='on',places_text='0 0 "Retained"',clouds='snapshot2011')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            for target,mode in (('earth','space'),('jupiter','orthographic'),('europa','space')):
                view=replace(active,target=target,projection=mode)
                path=save_named(root/(target+'-'+mode+'.conf'),view,sys.executable)
                doc=open_view(path);self.assertEqual(doc.view,view)
                self.assertFalse(doc.view.uses_system());self.assertNotIn(b'magnify=',doc.config)
                baseline=replace(view,composition='target',satellite_scale=1)
                self.assertEqual(view.render_digest(),baseline.render_digest())
            path=save_named(root/'system.conf',active,sys.executable)
            doc=open_view(path);self.assertEqual(doc.view,active);self.assertTrue(doc.view.uses_system())
            self.assertNotIn(b'cloud_map=',doc.config);self.assertNotIn(b'marker_file=',doc.config)

    def test_scale_bounds_invalid_draft_and_no_fictional_visibility(self):
        for scale in (0,.5,10.1,float('nan'),float('inf'),'bad',''):
            view=View(target='jupiter',projection='space',composition='system',satellite_scale=scale)
            self.assertTrue(any(i.severity=='blocking' and i.field=='satellite_scale' for i in view.issues()))
            self.assertIsInstance(view.appearance_summary(),str)
            with self.assertRaises(ValueError):view.body()
        for scale in (1,1.25,10):View(target='jupiter',projection='space',composition='system',satellite_scale=scale).validate()
        text=' '.join(i.message for i in View(target='jupiter',projection='space',composition='system',satellite_scale=3).issues())
        self.assertIn('still plots a point',text);self.assertIn('not a physical event prediction',text)
        self.assertFalse(any(i.severity=='warning' and i.field=='satellite_scale' for i in View(target='jupiter',projection='space',composition='system').issues()))

    def test_unknown_modes_extra_body_content_and_changed_scale_are_refused(self):
        with self.assertRaises(ValueError):View(composition='hide-others').validate()
        view=View(target='jupiter',projection='space',composition='system',satellite_scale=3)
        for body in (b'',view.body()+b'[sun]\nmagnify=0\n',view.body().replace(b'magnify=3',b'magnify=0',1),view.body().replace(b'Io.png',b'other.png'),view.body().replace(b'scale=3',b'scale=4')):
            self.assertFalse(recognized_body(body))
            with self.assertRaises(ValueError):parse_saved_view(view.definition('/renderer').encode(),body)
        for definition in (view.definition('/renderer').replace('XPLANET_SATELLITE_SCALE=3','XPLANET_SATELLITE_SCALE=4'),view.definition('/renderer')+'UNKNOWN=1\n'):
            with self.assertRaises(ValueError):parse_saved_view(definition.encode(),view.body())

    def test_pluto_system_date_policy_and_active_fields_are_shared(self):
        bad=View(target='pluto',projection='space',composition='system',time_mode='fixed',utc='2100-01-01T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'before 2100'):bad.body()
        self.assertIn('composition',replace(bad,time_mode='now').active_fields())
        self.assertIn('satellite_scale',replace(bad,time_mode='now').active_fields())
        self.assertNotIn('satellite_scale',replace(bad,composition='target').active_fields())
        self.assertNotIn('composition',replace(bad,target='earth').active_fields())
        self.assertTrue(any(i.field=='utc' and i.severity=='blocking' for i in configuration_issues(bad,sys.executable)))

    def test_system_stock_scenes_are_readonly_known_inputs_with_honest_scales(self):
        from configurator.model import ROOT
        for name,target,scale in (('jupiter-inner-enlarged','jupiter',10),('saturn-inner-enlarged','saturn',10),('pluto-charon-system','pluto',1)):
            source=ROOT/'scripts/configurator/samples/scenes'/(name+'.conf');before=source.read_bytes()
            doc=open_view(source);self.assertEqual((doc.view.target,doc.view.satellite_scale),(target,scale));self.assertTrue(doc.view.uses_system())
            self.assertNotIn('/Users/',source.with_suffix('.def').read_text())
            with tempfile.TemporaryDirectory() as temp:
                saved=save_named(Path(temp).resolve()/'copy.conf',doc.view,sys.executable,config_bytes=doc.config)
                self.assertEqual(open_view(saved).view,doc.view)
            self.assertEqual(source.read_bytes(),before)

    def test_preview_identity_tracks_effective_system_settings_only(self):
        from configurator.workspace import PreviewSnapshot,renderer_path
        view=View(target='jupiter',projection='space',composition='system',satellite_scale=3)
        snap=PreviewSnapshot(Path('/unused-image'),view,renderer_path(sys.executable),view.render_digest(),'2000-01-01T00:00:00Z','',binary_identity=identity(Path(sys.executable).resolve()))
        self.assertTrue(snap.matches(view,sys.executable,view.body()))
        self.assertFalse(snap.matches(replace(view,satellite_scale=4),sys.executable,view.body()))
        inactive=replace(view,projection='orthographic')
        snap=replace(snap,view=inactive,config_digest=inactive.render_digest())
        self.assertTrue(snap.matches(replace(inactive,satellite_scale=10),sys.executable,inactive.body()))


class SystemFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_system_does_not_spawn_or_discard_successful_preview(self):
        from configurator.workspace import Workspace
        from unittest.mock import AsyncMock,patch
        workspace=Workspace();self.addCleanup(workspace.close)
        from configurator.workspace import PreviewSnapshot,renderer_path
        good=View(target='jupiter',projection='space',composition='system')
        image=workspace.root/'previous'/'image.png';image.parent.mkdir();image.write_bytes(b'previous successful bytes')
        previous=PreviewSnapshot(image,good,renderer_path(sys.executable),good.render_digest(),'2000-01-01T00:00:00Z','',binary_identity=identity(Path(sys.executable).resolve()))
        workspace.latest=previous
        view=View(target='jupiter',projection='space',composition='system',satellite_scale=0)
        with patch('configurator.workspace.asyncio.create_subprocess_exec',new_callable=AsyncMock) as spawn:
            with self.assertRaises(ValueError):await workspace.preview(view,sys.executable)
            spawn.assert_not_awaited()
        self.assertIs(workspace.latest,previous);self.assertEqual(image.read_bytes(),b'previous successful bytes');self.assertFalse(workspace.busy);self.assertIsNone(workspace.process)
