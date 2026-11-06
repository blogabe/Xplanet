"""Literal decimal arguments work independently of the user's numeric locale."""
import os
from pathlib import Path
import subprocess
import unittest
from configurator.resources import renderer_environment

class RendererLocaleTests(unittest.TestCase):
    def test_child_locale_preserves_text_categories_and_parent_environment(self):
        original={'LC_ALL':'fr_FR.UTF-8','LC_MESSAGES':'de_DE.UTF-8','LANG':'en_US.UTF-8'}
        result=renderer_environment(original)
        self.assertEqual(original['LC_ALL'],'fr_FR.UTF-8')
        self.assertNotIn('LC_ALL',result)
        self.assertEqual(result['LC_NUMERIC'],'C')
        self.assertEqual(result['LC_MESSAGES'],'fr_FR.UTF-8')
        self.assertEqual(result['LC_CTYPE'],'fr_FR.UTF-8')
        self.assertEqual(renderer_environment({'LANG':'C','LC_MESSAGES':'C'})['LC_MESSAGES'],'C')
