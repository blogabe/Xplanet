"""Offline regression for complete NASA responses captured after the live failure."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from totalmarker.errors import FeedError
from totalmarker.features.eclipse import INDEX_URL, parse_index, parse_path, render, run
from totalmarker.http import Fetcher, Response
from .support import Sandbox, ScriptedTransport


FIXTURES = Path(__file__).parent / "fixtures" / "nasa"
ANNULAR_URL = (
    "https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2027Feb06Apath.html")
TOTAL_URL = (
    "https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2027Aug02Tpath.html")
NOW = datetime(2026, 10, 19, 19, 16, tzinfo=timezone.utc).timestamp()


class NasaCaptureTests(Sandbox):
    def captured(self):
        manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
        self.assertIn("original failed response was not saved", manifest["provenance"])
        bodies = {}
        for entry in manifest["captures"]:
            raw = (FIXTURES / entry["file"]).read_bytes()
            self.assertEqual(len(raw), entry["bytes"])
            self.assertEqual(sha256(raw).hexdigest(), entry["sha256"])
            self.assertEqual(entry["http_status"], 200)
            bodies[entry["source_url"]] = raw
        return bodies

    def test_complete_index_and_page_parse_with_url_identity(self):
        bodies = self.captured()
        candidates = parse_index(bodies[INDEX_URL])
        self.assertEqual(next(url for date, url in candidates if date >=
                              datetime(2026, 10, 18, tzinfo=timezone.utc).date()),
                         ANNULAR_URL)
        path = parse_path(bodies[ANNULAR_URL], ANNULAR_URL)
        self.assertEqual((path.kind, path.date, len(path.points)),
                         ("Annular", "2027-02-06", 115))
        self.assertEqual((path.start_at, path.end_at),
                         (1801922880.0, 1801936320.0))
        marker, arc = render(path, self.config("EclipseEnabled=On\n").eclipse,
                             path.start_at, True)
        self.assertIn(b"Annular Solar Eclipse central-path sampling underway", marker)
        self.assertEqual(arc.count(b"color=Black spacing=0.2"), 114)
        with self.assertRaisesRegex(FeedError, "identity"):
            parse_path(bodies[ANNULAR_URL], TOTAL_URL)

    def test_conflicting_page_heading_is_rejected(self):
        raw = self.captured()[ANNULAR_URL]
        old = b'<h1 class="box"> Path of the \nAnnular Solar Eclipse of'
        self.assertIn(old, raw)
        conflicting = raw.replace(
            old, b'<h1 class="box"> Path of the \nTotal Solar Eclipse of', 1)
        with self.assertRaisesRegex(FeedError, "identity"):
            parse_path(conflicting, ANNULAR_URL)

    def test_isolated_discovery_publishes_selected_future_event(self):
        bodies = self.captured()
        settings = self.config("EclipseEnabled=On\nEclipsePathURL=\n")
        transport = ScriptedTransport(Response(200, {}, bodies[INDEX_URL]),
                                      Response(200, {}, bodies[ANNULAR_URL]))
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=NOW)
        self.assertEqual((result.outcome, result.count), ("changed", 115))
        self.assertEqual(result.successful_at, NOW)
        self.assertEqual([url for url, _ in transport.calls], [INDEX_URL, ANNULAR_URL])
        self.assertIn(b"Annular 2027-02-06", self.fs.read(settings.eclipse.marker))
