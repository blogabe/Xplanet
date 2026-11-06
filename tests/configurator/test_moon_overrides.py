"""Individual scales replace inheritance without changing inactive visual state."""
from configurator.resources import identity
from dataclasses import replace
from pathlib import Path
import sys,tempfile,unittest
from configurator.model import View,SYSTEMS,parse_moon_scales,encode_moon_scales,parse_saved_view,recognized_body
from configurator.library import save_named
from configurator.workspace import open_view,PreviewSnapshot,renderer_path

class OverrideTests(unittest.TestCase):
    def scene(self,**changes):return replace(View(target='jupiter',projection='space',composition='system',satellite_scale=3),**changes)

    def test_literal_table_bounds_duplicates_unknowns_and_injection_decline(self):
        self.assertEqual(parse_moon_scales('europa=10,io=1.25'),{'europa':10,'io':1.25})
        self.assertEqual(encode_moon_scales({'io':'','titan':'2','europa':'+03'}),'europa=3,titan=2')
        for text in ('io=0','io=10.1','io=nan','io=1e309','io=-1','IO=2','earth=2','moon=2','io=1,io=2','io=1\ntitan=3','io=$(touch bad)','io=1;europa=2','x'*1025,'io=','io=1,'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_moon_scales(text)
        with self.assertRaises(ValueError):encode_moon_scales({'io':'1,europa=10'})

    def test_overrides_replace_shared_scale_and_do_not_scale_target(self):
        view=self.scene(moon_scales='io=1,europa=10,titan=2')
        self.assertEqual(view.system_scales(),{'io':1,'europa':10,'ganymede':3,'callisto':3})
        body=view.body();self.assertTrue(body.startswith(b'# Xplanet configurator system appearance v13;'))
        self.assertIn(b'[io]\nmap=',body);self.assertIn(b'grid=false\nmagnify=10\n',body)
        parent=body.split(b'[jupiter]\n')[1].split(b'\n\n',1)[0];self.assertNotIn(b'magnify=',parent)
        self.assertEqual(view.arguments(),replace(view,moon_scales='').arguments())
        self.assertTrue(any('Only Miranda' in i.message for i in self.scene(target='uranus',moon_scales='miranda=10').issues()))
        self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),body).view,view)
        warnings=' '.join(i.message for i in view.issues() if i.severity=='warning')
        self.assertIn('Europa 10×',warnings);self.assertNotIn('Titan 2×',warnings)

    def test_effectively_uniform_and_redundant_tables_keep_original_body_and_fingerprint(self):
        baseline=self.scene(satellite_scale=1)
        uniform=self.scene(moon_scales='io=1,europa=1,ganymede=1,callisto=1')
        self.assertEqual(uniform.body(),baseline.body());self.assertEqual(uniform.render_digest(),baseline.render_digest())
        self.assertEqual(replace(uniform,satellite_scale=9).render_digest(),baseline.render_digest())
        self.assertFalse(any('Effective moon enlargement' in i.message for i in uniform.issues()))
        redundant=self.scene(moon_scales='io=3,titan=10')
        self.assertEqual(redundant.body(),self.scene().body())
        self.assertEqual(redundant.render_digest(),self.scene().render_digest())
        self.assertEqual(parse_saved_view(uniform.definition('/renderer').encode(),uniform.body()).view,uniform)

    def test_other_family_and_inactive_overrides_roundtrip_without_affecting_body(self):
        for view in (self.scene(moon_scales='titan=10'),self.scene(target='earth',moon_scales='io=10'),self.scene(projection='orthographic',moon_scales='io=10')):
            self.assertEqual(view.body(),replace(view,moon_scales='').body())
            self.assertEqual(view.render_digest(),replace(view,moon_scales='').render_digest())
            self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),view.body()).view,view)
        invalid=self.scene(target='earth',moon_scales='io=0')
        self.assertTrue(any(i.field=='moon_scales' and i.severity=='blocking' for i in invalid.issues()))
        self.assertIsInstance(invalid.appearance_summary(),str)
        with self.assertRaises(ValueError):invalid.body()

    def test_old_formats_default_to_inheritance_and_cannot_drop_new_metadata(self):
        old=self.scene(orbit_paths='on',geometry='800x600')
        for version in (11,12):
            view=replace(old,orbit_paths='off') if version==11 else old
            self.assertEqual(parse_saved_view(view.definition('/renderer',version=version).encode(),view.body()).view,view)
        with self.assertRaisesRegex(ValueError,'Older formats'):self.scene(moon_scales='titan=2').definition('/renderer',version=12)

    def test_nonuniform_known_body_and_definition_mutations_are_rejected(self):
        view=self.scene(moon_scales='io=1,europa=10',orbit_paths='on');body=view.body();definition=view.definition('/renderer').encode()
        self.assertTrue(recognized_body(body))
        for changed in (body.replace(b'magnify=10',b'magnify=0'),body+b'[europa]\nmagnify=10\n',body.replace(b'Io.png',b'private.png'),body.replace(b'[io]',b'[unknown]')):
            self.assertFalse(recognized_body(changed))
            with self.assertRaises(ValueError):parse_saved_view(definition,changed)
        with self.assertRaises(ValueError):parse_saved_view(definition.replace(b'io=1,europa=10',b'io=2,europa=10'),body)

    def test_metadata_cannot_make_native_header_exceed_renderer_line_bounds(self):
        value='1.2345678901234567'
        table=encode_moon_scales({body:value if i%2 else '10' for i,body in enumerate(SYSTEMS['saturn'])})
        view=self.scene(target='saturn',moon_scales=table,orbit_paths='on')
        self.assertLessEqual(max(map(len,view.body().splitlines())),240)
        self.assertTrue(recognized_body(view.body()))
        self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),view.body()).view,view)

    def test_saved_copy_keeps_source_and_all_family_values(self):
        view=self.scene(moon_scales='io=1,europa=10,titan=2,miranda=3')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();source=save_named(root/'source.conf',view,sys.executable);before={p:p.read_bytes() for p in (source,source.with_suffix('.def'))}
            doc=open_view(source);copy=save_named(root/'copy.conf',doc.view,sys.executable,config_bytes=doc.config)
            self.assertEqual(open_view(copy).view,view)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    def test_preview_tracks_effective_scales_and_keeps_orbits_and_dates_unchanged(self):
        view=self.scene(moon_scales='io=1,europa=10')
        snap=PreviewSnapshot(Path('/unused'),view,renderer_path(sys.executable),view.render_digest(),'2000-01-01T00:00:00Z','',binary_identity=identity(Path(sys.executable).resolve()))
        self.assertTrue(snap.matches(replace(view,moon_scales='io=1,europa=10,titan=2'),sys.executable,view.body()))
        self.assertFalse(snap.matches(replace(view,moon_scales='io=2,europa=10'),sys.executable,view.body()))
        bad=replace(view,target='pluto',moon_scales='charon=1',time_mode='fixed',utc='2100-01-01T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'before 2100'):bad.body()
        bad=replace(view,target='saturn',orbit_paths='on',time_mode='fixed',utc='1800-01-01T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'Orbital path samples'):bad.body()
