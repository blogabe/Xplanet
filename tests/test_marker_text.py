"""Provider labels cannot escape Xplanet's literal quote parser."""
import unittest
from totalmarker.marker_text import quoted_label
from totalmarker.quake_geojson import _quoted as quake_quote
from totalmarker.volcano_cap import _quoted as volcano_quote
from totalmarker.storm_model import _quote as storm_quote

class MarkerTextTests(unittest.TestCase):
    def test_every_producer_uses_literal_engine_safe_labels(self):
        raw='Place " color=Red image=/private/file \\ line\nnext\x1b'
        expected='"Place \' color=Red image=/private/file / line next "'
        for quote in (quoted_label,quake_quote,volcano_quote,storm_quote):
            with self.subTest(producer=quote):
                self.assertEqual(quote(raw),expected)
                self.assertEqual(quote(raw).count('"'),2)
                self.assertNotIn('\\',quote(raw))
