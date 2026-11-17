"""The gallery catalogue is immutable guidance, not a command importer."""
import unittest
from configurator.recipes import RECIPES, matching_recipes
from configurator.model import ROOT
from configurator.workspace import open_view

class RecipeTests(unittest.TestCase):
    def test_all_visible_upstream_entries_have_unique_sources_and_explicit_scopes(self):
        self.assertEqual(len(RECIPES),24)
        self.assertEqual(len({r.url for r in RECIPES}),24)
        for recipe in RECIPES:
            with self.subTest(recipe=recipe.page):
                self.assertTrue(recipe.url.startswith('https://xplanet.sourceforge.net/Gallery/'))
                for value in (recipe.intent,recipe.camera,recipe.appearance,recipe.prerequisites,recipe.support):
                    self.assertTrue(value)
                self.assertIn('not a runnable preset',recipe.describe())
                if recipe.stock:
                    view=open_view(ROOT/'scripts/configurator/samples/scenes'/f'{recipe.stock}.conf')
                    self.assertIsNotNone(view.view)
                    self.assertIn('not a reproduction',recipe.describe())

    def test_filter_is_case_insensitive_multiword_and_includes_prerequisites(self):
        self.assertEqual(matching_recipes(''),RECIPES)
        self.assertEqual([r.page for r in matching_recipes('south america')],['20050418_earth'])
        self.assertIn('20050802_earth',[r.page for r in matching_recipes('SPICE kernels')])
        self.assertEqual(matching_recipes('no-such-recipe'),())

    def test_unsupported_features_are_not_advertised_as_available(self):
        by_id={r.page:r for r in RECIPES}
        self.assertIn('not all gallery projections',by_id['projections'].support)
        self.assertIn('not a supported studio origin',by_id['20031120_neptune'].support)
        self.assertIsNone(by_id['20031120_neptune'].stock)
        self.assertIn('not supplied',by_id['20050802_earth'].support)
        self.assertIn('historical Hubble',by_id['earth'].support)
