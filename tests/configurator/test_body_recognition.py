"""Recognized native bodies retain the section and ordering of captured layers."""
import unittest
from configurator.model import View,recognized_body

class BodyRecognitionTests(unittest.TestCase):
    def test_astronomy_references_are_an_earth_suffix_not_global_defaults(self):
        earth=View().body()
        for refs in (b'satellite_file=frozen-norad.satellites\n',b'marker_file=frozen-eclipse.markers\narc_file=frozen-eclipse.arcs\n'):
            with self.subTest(refs=refs):
                self.assertTrue(recognized_body(earth+refs))
                self.assertFalse(recognized_body(refs+earth))
                self.assertFalse(recognized_body(earth.replace(b'[earth]\n',refs+b'[earth]\n')))
                self.assertFalse(recognized_body(View(target='mars',projection='space').body()+refs))
