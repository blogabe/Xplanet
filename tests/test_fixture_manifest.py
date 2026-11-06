"""Unreceipted provider fixtures still have an immutable byte contract."""
import hashlib,json,unittest
from pathlib import Path
from .support import PROJECT

class FixtureManifestTests(unittest.TestCase):
    def test_selected_fixture_receipts_pin_bytes_without_inventing_retrieval(self):
        directory=PROJECT/'tests/fixtures'
        manifest=json.loads((directory/'provenance.json').read_bytes())
        self.assertEqual(manifest['schema'],1)
        records=manifest['records']
        expected={'usgs_quake_selected_20261019.geojson',
                  'storm/jtwc-abpw-20261026-2230.txt',
                  'storm/jtwc-rss-20261027-reissue.xml'}
        self.assertEqual({record['path'] for record in records},expected)
        self.assertEqual(len(records),len(expected))
        for record in records:
            with self.subTest(fixture=record['path']):
                raw=(directory/record['path']).read_bytes()
                self.assertEqual(len(raw),record['bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(),record['sha256'])
                self.assertIs(record['retrieval_verified'],False)
                for field in ('retrieved_at','source_url','http_status','http_headers'):
                    self.assertIsNone(record[field])
