"""Known orbital coordinates are data; no arbitrary import or desktop execution."""
from dataclasses import replace
from pathlib import Path
import json,sys,tempfile,unittest
from configurator.model import View,ORIGIN_FILE,LUNAR_BODY,PLANET_MAPS,parse_saved_view,recognized_body
from configurator.workspace import open_view,save_view
from configurator.library import save_named
from configurator.handoff import create_plan,stage_plan,check_bundle
from configurator.selection import apply_bundle,inspect_selection,read_revision,REVISIONS,ARGS
from tests.configurator import support_handoff as fixtures


def orbital(**changes):
    base=View(target='earth',projection='space',observer='moon',camera_mode='lunar_orbit',time_mode='fixed',utc='2000-01-18T12:00:00Z',framing='fov',fov=120,rotation=-90,frame_x=50,frame_y=100*900/1080)
    return replace(base,**changes)


class OrbitalCameraTests(unittest.TestCase):
    def test_args_use_one_known_coordinate_row_and_explicit_frame_centre(self):
        view=orbital();args=view.arguments();self.assertIn('-dynamic_origin',args);self.assertNotIn('-origin_file',args)
        self.assertEqual(args[args.index('-dynamic_origin')+1],ORIGIN_FILE)
        self.assertEqual(args[args.index('-center')+1],'+960+900')
        self.assertEqual(view.arguments(geometry_override='3840x2160')[args.index('-center')+1],'+1920+1800')
        self.assertEqual(view.origin_data(),b'20000118.120000 2 0 145\n')
        self.assertEqual(view.auxiliary_files()[ORIGIN_FILE],view.origin_data())
        self.assertIn(Path(PLANET_MAPS['moon']),view.resource_paths());self.assertTrue(recognized_body(view.body()))
        self.assertFalse(recognized_body(view.body()+LUNAR_BODY))
        self.assertIn('from centre',view.summary())

    def test_named_and_legacy_save_reopen_preserve_camera_assets_and_unchanged_sources(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as temp:
            root=Path(temp).resolve();view=orbital();path=save_named(root/'rise.conf',view,sys.executable)
            doc=open_view(path);self.assertEqual(doc.view,view)
            self.assertEqual((root/'rise.camera.origin').read_bytes(),view.origin_data())
            original={p.name:p.read_bytes() for p in root.iterdir()}
            clone=save_named(root/'copy.conf',doc.view,sys.executable,config_bytes=doc.config)
            self.assertEqual(open_view(clone).view,view)
            legacy=save_view(root/'directory',view,sys.executable);self.assertEqual(open_view(legacy).view,view)
            for name,raw in original.items():self.assertEqual((root/name).read_bytes(),raw)

    def test_missing_mutated_linked_or_multiple_coordinate_rows_are_refused(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as temp:
            root=Path(temp).resolve();path=save_named(root/'rise.conf',orbital(),sys.executable);origin=root/'rise.camera.origin';raw=origin.read_bytes()
            for bad in (b'',raw+raw,raw.replace(b' 2 ',b' 3 '),b'touch forbidden\n',b'x'*257):
                origin.write_bytes(bad)
                with self.subTest(bad=bad),self.assertRaises(ValueError):open_view(path)
                self.assertEqual(origin.read_bytes(),bad)
            origin.unlink()
            with self.assertRaises(OSError):open_view(path)
            other=root/'other';other.write_bytes(raw);origin.symlink_to(other)
            with self.assertRaises(OSError):open_view(path)
            self.assertFalse((root/'forbidden').exists())

    def test_mode_time_and_retained_choice_boundaries(self):
        view=orbital()
        with self.assertRaisesRegex(ValueError,'fixed UTC'):replace(view,time_mode='now').validate()
        with self.assertRaises(ValueError):replace(view,target='moon').validate()
        for fields in ({'orbit_range':1},{'orbit_range':101},{'orbit_latitude':91},{'orbit_longitude':float('nan')},{'frame_x':101},{'frame_y':float('inf')}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):replace(view,**fields).validate()
        inactive=replace(view,projection='rectangular',time_mode='now');inactive.validate()
        self.assertNotIn('-dynamic_origin',inactive.arguments());self.assertNotIn('-center',inactive.arguments())
        self.assertIsNone(inactive.origin_data());self.assertEqual(inactive.auxiliary_files(),{})
        self.assertEqual(inactive.render_digest(),replace(inactive,camera_mode='centre',frame_x=50,frame_y=50).render_digest())
        self.assertEqual(parse_saved_view(inactive.definition('/renderer').encode(),inactive.body()).view,inactive)
        self.assertNotEqual(view.render_digest(),replace(view,orbit_range=3).render_digest())

    def test_prior_versions_retain_defaults_and_cannot_silently_drop_new_choices(self):
        old=View(geometry='2160x1080');raw=old.definition('/renderer',version=14).encode()
        self.assertEqual(parse_saved_view(raw,old.body()).view,old)
        for view in (orbital(),View(frame_x=20),View(camera_mode='lunar_orbit')):
            with self.assertRaisesRegex(ValueError,'Older formats'):view.definition('/renderer',version=14)
        with self.assertRaises(ValueError):parse_saved_view(old.definition('/renderer').encode(),old.body(),origin=b'unexpected')


class OrbitalHandoffTests(unittest.TestCase):
    setUp=fixtures.HandoffFixture.setUp

    def test_review_freezes_coordinates_and_recomputes_centre_for_desktop_dimensions(self):
        view=orbital();scene=save_named(self.root/'config/scenes/rise.conf',view,sys.executable)
        plan=create_plan(self.root,scene,sys.executable,'3840x2160');stage_plan(plan,self.target)
        record=check_bundle(self.root,self.target);args=json.loads((self.target/'handoff.json').read_bytes())['compiled_argv']
        self.assertEqual(args[args.index('-dynamic_origin')+1],str(self.target/'rise.camera.origin'))
        self.assertEqual(args[args.index('-center')+1],'+1920+1800');self.assertEqual(args[-2:],['-timewarp','0'])
        receipt=apply_bundle(self.root,self.target,inspect_selection(self.root));revision=self.root/REVISIONS/receipt.after.revision
        self.assertEqual((revision/'rise.camera.origin').read_bytes(),view.origin_data())
        self.assertIn(b'@revision@/rise.camera.origin',(revision/ARGS).read_bytes())
        read_revision(self.root,receipt.after.revision)
        (revision/'rise.camera.origin').write_bytes(b'changed')
        with self.assertRaises(ValueError):read_revision(self.root,receipt.after.revision)
        self.assertFalse((self.root/'forbidden').exists())
