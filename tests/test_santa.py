"""Existing settings, records and publication journals survive stub retirement."""
from contextlib import redirect_stderr
from io import StringIO
import hashlib
from unittest.mock import patch

from totalmarker.cli import main
from totalmarker.errors import StorageError
from totalmarker.state import MarkerPublisher, load_state, recover_pending
from .support import Sandbox


class RetiredSantaTests(Sandbox):
    def test_legacy_settings_load_but_cli_no_longer_exposes_stub(self):
        settings = self.config("SantaEnabled=On\nSantaFreshnessSeconds=3600\n")
        self.assertTrue(settings.santa.enabled)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as exc:
            main(["--root", str(self.root), "santa"])
        self.assertEqual(exc.exception.code, 2)
        self.assertIsNone(self.fs.read(settings.santa.marker))

    def test_old_pending_marker_recovers_with_original_paths(self):
        settings = self.config("SantaOutput=markers/old-santa\n")
        mark = b'12.3456 -45.6789 "Santa" color=Red\n'
        state = {"schema": 1, "products": {"santa": {
            "marker_sha256": hashlib.sha256(mark).hexdigest(), "count": 1,
            "last_good": {"provider_id": "older-test", "season_year": 2026,
                          "lifecycle": "tracking", "latitude": 12.3456, "longitude": -45.6789,
                          "source_at": 1798110000, "retrieved_at": 1798110000}}}}
        publish = MarkerPublisher(self.fs, settings, "santa")
        writer = self.fs.write
        def interrupted(path, raw, **kwargs):
            if path == settings.state:
                raise StorageError("test interrupted after marker write")
            return writer(path, raw, **kwargs)

        with patch.object(self.fs, "write", side_effect=interrupted):
            with self.assertRaisesRegex(StorageError, "test interrupted"):
                publish.publish(state, None, marker=mark)
        self.assertIsNotNone(self.fs.read(settings.santa.journal))
        recover_pending(self.fs, settings)
        self.assertIsNone(self.fs.read(settings.santa.journal))
        self.assertEqual(self.fs.read(settings.santa.marker), mark)
        self.assertEqual(load_state(self.fs, settings.state)["products"]["santa"],
                         state["products"]["santa"])
