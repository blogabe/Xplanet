"""Read old generated map references without changing their native bytes."""
import unittest
from configurator.model import View, parse_saved_view, recognized_body, _PREVIOUS_MAP_FOLDERS

class MapsLayoutTests(unittest.TestCase):
    def test_old_generated_paths_reopen_but_render_model_uses_current_layout(self):
        views=(View(map_family='world',month='09',night='lights2002'),
               View(clouds='snapshot2011',relief='gebco',specular='bundled'),
               View(target='mars',projection='space'),
               View(target='jupiter',projection='space',composition='system'))
        for view in views:
            with self.subTest(target=view.target,clouds=view.clouds):
                original=view.body().replace(b'=maps/',b'=assets/maps/')
                self.assertNotEqual(original,view.body())
                doc=parse_saved_view(view.definition('/usr/bin/true').encode(),original)
                self.assertEqual(doc.view,view)
                self.assertEqual(doc.config,original)
                self.assertTrue(recognized_body(original))
                self.assertNotIn(b'=assets/maps/',doc.view.body())
                self.assertTrue(all(str(p).startswith('maps/') for p in view.resource_paths()))

    def test_old_prefix_does_not_make_unknown_configuration_editable(self):
        view=View(target='mars',projection='space')
        body=view.body().replace(b'=maps/',b'=assets/maps/')+b'unknown=keep\n'
        with self.assertRaises(ValueError):parse_saved_view(view.definition('/usr/bin/true').encode(),body)
        self.assertFalse(recognized_body(body))

    def test_prior_solar_directory_spellings_remain_read_only_recognizable(self):
        for target in ('moon','mars','jupiter','saturn','uranus','neptune','pluto'):
            view=View(target=target,projection='space')
            old=view.body()
            for previous,current in _PREVIOUS_MAP_FOLDERS.items():
                old=old.replace(('/solarsystem/'+current+'/').encode(),('/solarsystem/'+previous+'/').encode())
            old=old.replace(b'=maps/',b'=assets/maps/')
            doc=parse_saved_view(view.definition('/usr/bin/true').encode(),old)
            self.assertEqual(doc.config,old)
            self.assertEqual(doc.view,view)
            self.assertTrue(recognized_body(old))
