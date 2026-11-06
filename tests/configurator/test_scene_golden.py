"""Frozen historical pairs detect parser/serializer drift across releases."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import unittest

from configurator.model import View, parse_saved_view
from configurator.workspace import open_view

FIXTURES = Path(__file__).resolve().parents[1]/'fixtures/configurator/scenes'


class NativeSceneGoldenTests(unittest.TestCase):
    def test_every_supported_historical_pair_preserves_bytes_and_meaning(self):
        manifest = json.loads((FIXTURES/'manifest.json').read_bytes())
        self.assertEqual(set(manifest['versions']), {str(v) for v in range(2, 17)})
        for version, record in manifest['versions'].items():
            with self.subTest(version=version):
                folder = FIXTURES/('v'+version)
                files = {name:(folder/name).read_bytes() for name in record['files']}
                for name, raw in files.items():
                    self.assertEqual(len(raw), record['files'][name]['bytes'])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), record['files'][name]['sha256'])
                document = parse_saved_view(files['xp.def'], files['xp.conf'])
                self.assertEqual(asdict(document.view), record['expected_fields'])
                self.assertEqual(document.config, files['xp.conf'])
                self.assertEqual(document.saved_renderer, '/path/to/xplanet')
                reopened = open_view(folder/'xp.conf')
                self.assertEqual(reopened.view, document.view)
                self.assertEqual(files, {name:(folder/name).read_bytes() for name in files})

    def test_current_serializer_matches_its_frozen_native_contract(self):
        manifest = json.loads((FIXTURES/'manifest.json').read_bytes())
        folder = FIXTURES/('v'+str(manifest['current_version']))
        view = View(**manifest['current_defaults'])
        self.assertEqual(view.definition('/path/to/xplanet', asset_root=Path('/xplanet')).encode(), (folder/'xp.def').read_bytes())
        self.assertEqual(view.body(), (folder/'xp.conf').read_bytes())
