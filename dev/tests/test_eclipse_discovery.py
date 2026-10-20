"""Synthetic index HTML using published NASA path names; no live response."""
from totalmarker.features.eclipse import parse_index, parse_path, run
from totalmarker.http import Fetcher, Response
from .support import Sandbox, ScriptedTransport
from .test_eclipse import ANNULAR, ANNULAR_URL, TOTAL, TOTAL_URL


INDEX = b"""<html><h1>Central Solar Eclipses: 1991 - 2050</h1><table>
<tr><td>2027 Feb 06</td><td>Annular</td><td><a href="SEpath2001/SE2027Feb06Apath.html">path</a></td></tr>
<tr><td>2027 Aug 02</td><td>Total</td><td><a href="SEpath2001/SE2027Aug02Tpath.html">path</a></td></tr>
</table></html>"""


class EclipseDiscoveryTests(Sandbox):
    def options(self):
        return self.config("EclipseEnabled=On\n")

    def test_index_selects_upcoming_central_event_with_bounded_fetches(self):
        settings = self.options()
        path = parse_path(ANNULAR, ANNULAR_URL)
        transport = ScriptedTransport(Response(200, {}, INDEX),
                                      Response(200, {}, ANNULAR))
        result = run(self.fs, settings, fetcher=Fetcher(transport),
                     now=path.start_at - 24 * 3600)
        self.assertEqual(result.outcome, "changed")
        self.assertEqual(len(transport.calls), 2)
        self.assertIn("SEpath.html", transport.calls[0][0])
        self.assertEqual(transport.calls[1][0], ANNULAR_URL)
        self.assertIn(b"Annular Solar Eclipse", self.fs.read(settings.eclipse.marker))

    def test_index_skips_expired_current_event_and_uses_next(self):
        settings = self.options()
        path = parse_path(ANNULAR, ANNULAR_URL)
        transport = ScriptedTransport(Response(200, {}, INDEX),
                                      Response(200, {}, ANNULAR),
                                      Response(200, {}, TOTAL))
        result = run(self.fs, settings, fetcher=Fetcher(transport),
                     now=path.end_at + 2 * 3600)
        self.assertEqual(result.outcome, "changed")
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(transport.calls[-1][0], TOTAL_URL)
        self.assertIn(b"Total 2027-08-02", self.fs.read(settings.eclipse.marker))

    def test_index_ignores_offhost_invalid_and_duplicate_links(self):
        raw = INDEX.replace(
            b"</table>",
            b'<tr><a href="https://example.org/SEpath/SEpath2001/SE2027Aug02Tpath.html">path</a></tr>'
            b'<tr><a href="SEpath2001/SE2027Feb06Apath.html">path</a></tr>'
            b'<tr><a href="SEpath2001/SE2027Feb99Apath.html">path</a></tr>'
            b'</table>')
        entries = parse_index(raw)
        self.assertEqual([url for _, url in entries], [ANNULAR_URL, TOTAL_URL])

    def test_index_provider_failure_retains_last_good(self):
        settings = self.options()
        path = parse_path(ANNULAR, ANNULAR_URL)
        transport = ScriptedTransport(Response(200, {}, INDEX),
                                      Response(200, {}, ANNULAR),
                                      Response(503, {"content-type": "text/plain"},
                                               b"Service unavailable"))
        first = run(self.fs, settings, fetcher=Fetcher(transport),
                    now=path.start_at - 24 * 3600)
        marker = self.fs.read(settings.eclipse.marker)
        arc = self.fs.read(settings.eclipse.arc)
        second = run(self.fs, settings, fetcher=Fetcher(transport),
                     now=path.start_at - 24 * 3600 + 86400)
        self.assertEqual(first.outcome, "changed")
        self.assertEqual(second.outcome, "failed")
        self.assertEqual(second.successful_at, first.successful_at)
        refreshed = self.fs.read(settings.eclipse.marker)
        self.assertEqual([line for line in refreshed.splitlines()
                          if not line.startswith(b'-55 1 "')],
                         [line for line in marker.splitlines()
                          if not line.startswith(b'-55 1 "')])
        self.assertIn(b'central-path sampling underway', refreshed)
        self.assertEqual(self.fs.read(settings.eclipse.arc), arc)
