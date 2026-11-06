"""Bundled satellite targets and conservative ephemeris input policy."""
from dataclasses import replace
from pathlib import Path
import sys,tempfile,unittest
from configurator.model import View,ROOT,PLANET_MAPS,MOON_PARENTS,EAST_POSITIVE,parse_saved_view,recognized_body
from configurator.library import save_named
from configurator.workspace import open_view

NEW=('phobos','deimos','io','europa','ganymede','callisto','mimas','enceladus','tethys','dione','rhea','titan','hyperion','iapetus','phoebe','miranda','pluto','charon')

class MoonTests(unittest.TestCase):
    def test_bundled_targets_roundtrip_as_maps_and_from_their_primary(self):
        for target in NEW:
            self.assertTrue((ROOT/PLANET_MAPS[target]).is_file(),target)
            for mode in ('space','orthographic'):
                view=View(target=target,projection=mode,observer=MOON_PARENTS.get(target,'charon'),grid='30',planet_shade=12,time_mode='fixed',utc='2000-01-01T12:00:00Z')
                with self.subTest(target=target,mode=mode):
                    self.assertTrue(recognized_body(view.body()))
                    self.assertEqual(parse_saved_view(view.definition('/renderer').encode(),view.body()).view,view)
                    self.assertIn(str(PLANET_MAPS[target]).encode(),view.body())
                    self.assertNotIn(b'magnify=',view.body())
                    if mode=='space':self.assertIn('-origin',view.arguments())
                    else:self.assertNotIn('-origin',view.arguments())

    def test_named_moon_copy_keeps_inactive_earth_choices_without_using_them(self):
        view=View(target='europa',projection='space',observer='jupiter',places='on',places_text='0 0 "Keep me"',clouds='snapshot2011',map_family='world',month='09')
        with tempfile.TemporaryDirectory() as temp:
            path=save_named(Path(temp).resolve()/'europa.conf',view,sys.executable)
            doc=open_view(path);self.assertEqual(doc.view,view)
            self.assertNotIn(b'marker_file=',doc.config);self.assertNotIn(b'cloud_map=',doc.config)
            earth=replace(doc.view,target='earth',observer='geographic')
            self.assertIn(b'cloud_map=',earth.body());self.assertIn(b'marker_file=',earth.body())

    def test_pluto_charon_fixed_date_policy_checks_active_target_or_origin(self):
        for target,origin in (('pluto','geographic'),('charon','pluto'),('earth','charon'),('io','pluto')):
            for date in ('1800-01-01T00:00:00Z','2099-12-31T23:59:59Z'):
                View(target=target,observer=origin,projection='space',time_mode='fixed',utc=date).validate()
            for date in ('2100-01-01T00:00:00Z','2200-12-31T23:59:59Z'):
                view=View(target=target,observer=origin,projection='space',time_mode='fixed',utc=date)
                with self.subTest(target=target,origin=origin,date=date),self.assertRaisesRegex(ValueError,'before 2100'):view.validate()

    def test_inactive_origin_and_inactive_time_do_not_impose_pluto_limit(self):
        View(target='earth',observer='pluto',projection='orthographic',time_mode='fixed',utc='2200-01-01T00:00:00Z').validate()
        View(target='pluto',time_mode='now',utc='2200-01-01T00:00:00Z').validate()
        self.assertNotIn('-date',View(target='pluto',time_mode='now',utc='2200-01-01T00:00:00Z').arguments())
        View(target='europa',time_mode='fixed',utc='2200-01-01T00:00:00Z').validate()

    def test_geometry_context_is_not_an_accuracy_or_imagery_promise(self):
        for target in NEW:
            text=' '.join(i.message for i in View(target=target).issues())
            self.assertIn('not certified',text)
            if target in MOON_PARENTS:self.assertIn(MOON_PARENTS[target].title(),text)
        self.assertTrue(any('legacy bundled textures' in i.message for i in View(target='pluto').issues()))
        self.assertTrue(any(i.field=='observer' and 'satellite approximation' in i.message for i in View(target='mars',projection='space',observer='phobos').issues()))
        self.assertFalse(any(i.field=='observer' and 'satellite approximation' in i.message for i in View(target='mars',projection='orthographic',observer='phobos').issues()))
        for target in ('miranda','pluto','charon'):self.assertIn(target,EAST_POSITIVE)
        for target in ('phobos','europa','titan'):self.assertNotIn(target,EAST_POSITIVE)

    def test_missing_texture_bodies_are_not_fabricated(self):
        for body in ('triton','nereid','ariel','umbriel','titania','oberon'):
            with self.subTest(body=body),self.assertRaises(ValueError):View(target=body).validate()
