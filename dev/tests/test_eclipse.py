"""NASA GSFC central path excerpts, transcribed from the linked path tables.

The short excerpts exercise parsing and publication. They are not complete
eclipse predictions and must never be used as live source files.
"""
import hashlib
from contextlib import redirect_stdout
from io import StringIO
import json
from unittest.mock import patch

from totalmarker.errors import ConfigError, FeedError, StorageError
from totalmarker.features.eclipse import _source_key, parse_path, render, run
from totalmarker.http import Fetcher, Response
from totalmarker.state import PairPublisher, json_bytes, recover_pending
from .support import Sandbox, ScriptedTransport


TOTAL_URL = "https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2027Aug02Tpath.html"
ANNULAR_URL = "https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2027Feb06Apath.html"
HYBRID_URL = "https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2023Apr20Hpath.html"
TOTAL = b"""<html><h1>Path of the Total Solar Eclipse of 2027 Aug 02</h1><pre>
Limits  28 48.0N 044 56.6W  27 07.3N 044 01.4W  27 57.7N 044 28.6W  1.060
11:30   01 43.4N 064 02.9E  00 28.7N 061 59.1E  01 06.5N 063 00.3E  1.071
11:32   00 48.8N 065 21.5E  00 24.5S 063 15.6E  00 12.6N 064 17.7E  1.070
11:34   00 08.4S 066 46.7E  01 20.0S 064 38.4E  00 43.7S 065 41.7E  1.070
Limits  11 38.0S 090 50.3E  13 19.9S 090 03.0E  12 29.0S 090 26.5E  1.060
</pre></html>"""
ANNULAR = b"""<h1>Path of the Annular Solar Eclipse of 2027 Feb 06</h1><pre>
Limits  37 38.8S 130 21.0W  40 31.9S 132 23.0W  39 05.1S 131 20.4W  0.914
14:08   40 51.2S 117 50.0W     -         -      41 19.8S 122 50.6W  0.916
14:10   41 49.9S 112 58.3W  43 28.0S 120 42.8W  42 46.6S 116 14.6W  0.917
Limits  07 39.5N 002 58.9E  04 43.1N 004 27.5E  06 11.7N 003 42.7E  0.915
</pre>"""
HYBRID = b"""<h1>Path of the Hybrid Solar Eclipse of 2023 Apr 20</h1><pre>
Limits  48 25.4S 063 37.0E  48 28.8S 063 38.0E  48 27.1S 063 37.5E  0.998
02:38   46 07.9S 073 05.9E  46 06.8S 073 07.4E  46 07.4S 073 06.7E  1.000
02:40   43 57.4S 079 58.9E  43 52.1S 080 01.9E  43 54.8S 080 00.4E  1.002
Limits  02 58.9N 178 48.2W  02 52.6N 178 48.6W  02 55.8N 178 48.4W  0.997
</pre>"""


class EclipseTests(Sandbox):
    def options(self, url=TOTAL_URL):
        return self.config(f"EclipseEnabled=On\nEclipsePathURL={url}\n")

    def previous_notice_state(self, settings):
        marker = self.fs.read(settings.eclipse.marker)
        old_line = (b'-55 1 "Total Solar Eclipse path samples start '
                    b'2027-08-02 11:30 UTC" color=White image=none position=pixel\n')
        marker = b"".join(old_line if line.startswith(b'-55 1 "') else line
                          for line in marker.splitlines(keepends=True))
        self.fs.write(settings.eclipse.marker, marker)
        arc = self.fs.read(settings.eclipse.arc)
        state = self.read_state(settings)
        record = state["products"]["eclipse"]
        record["source_key"] = _source_key(self.fs, settings.eclipse, legacy_notice=True)
        record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
        record["body_sha256"] = hashlib.sha256(marker + b"\0" + arc).hexdigest()
        self.fs.write(settings.state, json_bytes(state))
        return marker

    def test_total_signed_coordinates_timed_arcs_notice_and_cache(self):
        path = parse_path(TOTAL, TOTAL_URL)
        self.assertEqual(path.kind, "Total")
        self.assertAlmostEqual(path.points[2].south[0], -24.5 / 60)
        settings = self.options()
        transport = ScriptedTransport(Response(200, {"content-type": "text/html"}, TOTAL))
        now = path.start_at - 3600
        first = run(self.fs, settings, fetcher=Fetcher(transport), now=now)
        self.assertEqual(first.outcome, "changed")
        marker = self.fs.read(settings.eclipse.marker)
        arc = self.fs.read(settings.eclipse.arc)
        self.assertIn(b"Total Solar Eclipse central-path samples begin in 1h 0m (2027-08-02 11:30 UTC)", marker)
        self.assertIn(b'# center path', arc)
        self.assertIn(b'color=Black spacing=0.2', arc)
        self.assertEqual(len(transport.calls), 1)
        fetched_at = self.read_state(settings)["products"]["eclipse"]["fetched_at"]
        again = run(self.fs, settings, fetcher=Fetcher(transport), now=now + 60)
        self.assertEqual(again.outcome, "changed")
        self.assertIn(b"samples begin in 0h 59m", self.fs.read(settings.eclipse.marker))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(self.read_state(settings)["products"]["eclipse"]["fetched_at"],
                         fetched_at)
        underway = run(self.fs, settings, fetcher=Fetcher(transport),
                       now=path.start_at + 60)
        self.assertEqual(underway.outcome, "changed")
        self.assertIn(b"Total Solar Eclipse central-path sampling underway", self.fs.read(settings.eclipse.marker))
        self.assertEqual(len(transport.calls), 1)

    def test_notice_visibility_does_not_hide_path(self):
        settings = self.config(
            f"EclipseEnabled=On\nEclipsePathURL={TOTAL_URL}\n"
            "EclipseNoticeEnabled=Off\n")
        path = parse_path(TOTAL, TOTAL_URL)
        marker, arc = render(path, settings.eclipse, path.start_at - 3600, True)
        self.assertNotIn(b"central-path samples begin in", marker)
        self.assertNotIn(b"NASA predicted central path", marker)
        self.assertIn(b"11:30 UTC", marker)
        self.assertIn(b"# center path", arc)
        with self.assertRaisesRegex(ConfigError, "EclipseNoticeEnabled"):
            self.config("EclipseNoticeEnabled=maybe\n")

    def test_notice_switch_reuses_saved_path_without_request(self):
        path = parse_path(TOTAL, TOTAL_URL)
        on = self.options()
        initial = run(self.fs, on, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, TOTAL))), now=path.start_at - 3600)
        self.assertEqual(initial.outcome, "changed")
        prior_arc = self.fs.read(on.eclipse.arc)
        fetched_at = self.read_state(on)["products"]["eclipse"]["fetched_at"]
        off = self.config(f"EclipseEnabled=On\nEclipsePathURL={TOTAL_URL}\n"
                          "EclipseNoticeEnabled=Off\n")
        transport = ScriptedTransport()
        hidden = run(self.fs, off, fetcher=Fetcher(transport),
                     now=path.start_at - 3540)
        self.assertEqual(hidden.outcome, "changed")
        self.assertNotIn(b"central-path samples begin in", self.fs.read(off.eclipse.marker))
        self.assertEqual(self.fs.read(off.eclipse.arc), prior_arc)
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.read_state(off)["products"]["eclipse"]["fetched_at"],
                         fetched_at)
        self.assertEqual(hidden.successful_at, initial.successful_at)
        self.config(f"EclipseEnabled=On\nEclipsePathURL={TOTAL_URL}\n"
                    "EclipseNoticeEnabled=On\n")
        visible = run(self.fs, on, fetcher=Fetcher(transport),
                      now=path.start_at - 3480)
        self.assertEqual(visible.outcome, "changed")
        self.assertIn(b"central-path samples begin in", self.fs.read(on.eclipse.marker))
        self.assertEqual(transport.calls, [])

    def test_annular_hybrid_and_missing_limit(self):
        for raw, url, kind in ((ANNULAR, ANNULAR_URL, "Annular"),
                               (HYBRID, HYBRID_URL, "Hybrid")):
            with self.subTest(kind=kind):
                path = parse_path(raw, url)
                self.assertEqual(path.kind, kind)
                marker, arc = render(path, self.options(url).eclipse,
                                     path.start_at, True)
                self.assertIn(kind.encode() + b" Solar Eclipse", marker)
                self.assertIn(b"# north path", arc)
                self.assertIn(b"# south path", arc)
        self.assertIsNone(parse_path(ANNULAR, ANNULAR_URL).points[1].south)

    def test_previous_state_notice_key_can_hide_notice_offline(self):
        path = parse_path(TOTAL, TOTAL_URL)
        original = self.options()
        first = run(self.fs, original, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, TOTAL))), now=path.start_at - 3600)
        self.previous_notice_state(original)
        off = self.config(f"EclipseEnabled=On\nEclipsePathURL={TOTAL_URL}\n"
                          "EclipseNoticeEnabled=Off\n")
        transport = ScriptedTransport()
        hidden = run(self.fs, off, fetcher=Fetcher(transport),
                     now=path.start_at - 3540)
        self.assertEqual(hidden.outcome, "changed")
        self.assertEqual(hidden.successful_at, first.successful_at)
        self.assertNotIn(b'central-path samples begin in', self.fs.read(off.eclipse.marker))
        self.assertEqual(transport.calls, [])

    def test_previous_notice_key_does_not_adopt_changed_path_selection(self):
        path = parse_path(TOTAL, TOTAL_URL)
        original = self.options()
        run(self.fs, original, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, TOTAL))), now=path.start_at - 3600)
        old_marker = self.previous_notice_state(original)
        changed = self.config(f"EclipseEnabled=On\nEclipsePathURL={ANNULAR_URL}\n"
                              "EclipseNoticeEnabled=Off\n")
        failed = run(self.fs, changed, fetcher=Fetcher(ScriptedTransport(
            Response(503, {}, b"Unavailable"))), now=path.start_at - 3540)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(self.fs.read(changed.eclipse.marker), old_marker)

    def test_failed_stale_fetch_refreshes_saved_countdown_without_success(self):
        path = parse_path(TOTAL, TOTAL_URL)
        settings = self.options()
        first = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, TOTAL))), now=path.start_at - 30 * 3600)
        old_arc = self.fs.read(settings.eclipse.arc)
        old_fetch = self.read_state(settings)["products"]["eclipse"]["fetched_at"]
        failing = ScriptedTransport(Response(503, {}, b"Unavailable"))
        failed = run(self.fs, settings, fetcher=Fetcher(failing),
                     now=path.start_at - 3600)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.successful_at, first.successful_at)
        self.assertIn(b'central-path samples begin in 1h 0m',
                      self.fs.read(settings.eclipse.marker))
        self.assertEqual(self.fs.read(settings.eclipse.arc), old_arc)
        self.assertEqual(self.read_state(settings)["products"]["eclipse"]["fetched_at"],
                         old_fetch)
        self.assertEqual(len(failing.calls), 1)

    def test_post_path_grace_notice_does_not_claim_eclipse_underway(self):
        path = parse_path(TOTAL, TOTAL_URL)
        settings = self.options()
        run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, TOTAL))), now=path.end_at - 60)
        grace = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport()),
                    now=path.end_at + 1800)
        self.assertEqual(grace.outcome, "changed")
        self.assertIn(b'central-path sampling ended',
                      self.fs.read(settings.eclipse.marker))

    def test_padded_coordinates_include_final_arc_segment(self):
        padded = TOTAL.replace(b"  00 43.7S 065 41.7E",
                               b" \t 00  43.7S  065 41.7E", 1)
        path = parse_path(padded, TOTAL_URL)
        self.assertEqual(path.points, parse_path(TOTAL, TOTAL_URL).points)
        _, arc = render(path, self.options().eclipse, path.start_at, True)
        center_segments = arc.split(b"# center path\n", 1)[1].splitlines()
        self.assertEqual(len(center_segments), 4)
        self.assertEqual(center_segments[-1],
                         b"-0.7283 65.6950 -12.4833 90.4417 color=Black spacing=0.2")

    def test_window_hides_then_expires_and_bad_source_retains_pair(self):
        path = parse_path(TOTAL, TOTAL_URL)
        settings = self.options()
        transport = ScriptedTransport(Response(200, {}, TOTAL),
                                      Response(200, {}, TOTAL))
        client = Fetcher(transport)
        early = run(self.fs, settings, fetcher=client, now=path.start_at - 50 * 3600)
        self.assertEqual(early.outcome, "changed")
        self.assertNotIn(b"central-path samples begin in", self.fs.read(settings.eclipse.marker))
        active = run(self.fs, settings, fetcher=client, now=path.start_at - 3600)
        self.assertEqual(active.outcome, "changed")
        expired = run(self.fs, settings, fetcher=client, now=path.end_at + 2 * 3600)
        self.assertEqual(expired.outcome, "changed")
        self.assertNotIn(b"# center path", self.fs.read(settings.eclipse.arc))
        # A fixed event is never re-fetched after its verified expiry.
        retained = self.fs.read(settings.eclipse.arc)
        later = run(self.fs, settings, fetcher=client, now=path.end_at + 26 * 3600)
        self.assertEqual(later.outcome, "unchanged")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(self.fs.read(settings.eclipse.arc), retained)

    def test_invalid_degree_minutes_are_rejected(self):
        malformed = TOTAL.replace(b"01 43.4N", b"01 99.9N", 1)
        with self.assertRaisesRegex(FeedError, "coordinate"):
            parse_path(malformed, TOTAL_URL)

    def test_expiry_is_offline_even_after_ninety_days(self):
        path = parse_path(TOTAL, TOTAL_URL)
        settings = self.options()
        transport = ScriptedTransport(Response(200, {}, TOTAL))
        initial = run(self.fs, settings, fetcher=Fetcher(transport),
                      now=path.start_at - 3600)
        self.assertEqual(initial.outcome, "changed")
        expired = run(self.fs, settings, fetcher=Fetcher(transport),
                      now=path.end_at + 2 * 3600)
        self.assertEqual(expired.outcome, "changed")
        self.assertNotIn(b"central-path samples begin in", self.fs.read(settings.eclipse.marker))
        self.assertNotIn(b"# center path", self.fs.read(settings.eclipse.arc))
        self.assertEqual(expired.successful_at, initial.successful_at)
        later = run(self.fs, settings, fetcher=Fetcher(transport),
                    now=path.end_at + 90 * 86400)
        self.assertEqual(later.outcome, "unchanged")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(later.successful_at, initial.successful_at)

    def _assert_expiry_after_config_change(self, replacement):
        path = parse_path(TOTAL, TOTAL_URL)
        old_settings = self.options()
        initial = run(self.fs, old_settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, TOTAL))), now=path.start_at - 3600)
        self.assertEqual(initial.outcome, "changed")
        old_source_key = self.read_state(old_settings)["products"]["eclipse"]["source_key"]
        settings = self.config("EclipseEnabled=On\n" + replacement)
        transport = ScriptedTransport()
        expired = run(self.fs, settings, fetcher=Fetcher(transport),
                      now=path.end_at + 90 * 86400)
        self.assertEqual(expired.outcome, "changed")
        self.assertEqual(transport.calls, [])
        self.assertEqual(expired.successful_at, initial.successful_at)
        self.assertNotIn(b"central-path samples begin in", self.fs.read(settings.eclipse.marker))
        self.assertNotIn(b"# center path", self.fs.read(settings.eclipse.arc))
        self.assertEqual(self.read_state(settings)["products"]["eclipse"]["source_key"],
                         old_source_key)
        # The new settings still need a real fetch; an outage leaves the
        # already-cleared files in place without claiming a fresh success.
        failing = ScriptedTransport(Response(
            503, {"content-type": "text/plain"}, b"Service unavailable"))
        followup = run(self.fs, settings, fetcher=Fetcher(failing),
                       now=path.end_at + 90 * 86400 + 60)
        self.assertEqual(followup.outcome, "failed")
        self.assertEqual(len(failing.calls), 1)
        self.assertEqual(followup.successful_at, initial.successful_at)
        self.assertNotIn(b"# center path", self.fs.read(settings.eclipse.arc))

    def test_prior_version_expiry_after_edge_color_change(self):
        self._assert_expiry_after_config_change(
            f"EclipsePathURL={TOTAL_URL}\nEclipseEdgeColor=Orange\n")

    def test_prior_version_expiry_after_notice_window_change(self):
        self._assert_expiry_after_config_change(
            f"EclipsePathURL={TOTAL_URL}\nEclipseNotifyHours=24\n")

    def test_prior_version_expiry_after_explicit_to_discovery(self):
        self._assert_expiry_after_config_change("EclipsePathURL=\n")

    def test_enabled_cli_success_then_provider_failure(self):
        from totalmarker.cli import main
        path = parse_path(TOTAL, TOTAL_URL)
        self.options()
        transport = ScriptedTransport(Response(200, {}, TOTAL),
                                      Response(503, {"content-type": "text/plain"},
                                               b"Service unavailable"))
        with patch("totalmarker.features.eclipse.Fetcher", return_value=Fetcher(transport)):
            with patch("totalmarker.features.eclipse.time.time",
                       side_effect=[path.start_at - 30 * 3600,
                                    path.start_at - 3600]):
                outputs = []
                for _ in range(2):
                    stream = StringIO()
                    with redirect_stdout(stream):
                        code = main(["--root", str(self.root), "--config", "config.ini",
                                     "eclipse"])
                    outputs.append((code, json.loads(stream.getvalue())))
        self.assertEqual([code for code, _ in outputs], [0, 1])
        self.assertEqual([body["outcome"] for _, body in outputs], ["changed", "failed"])
        self.assertEqual(outputs[1][1]["successful_at"],
                         outputs[0][1]["successful_at"])

    def test_interrupted_pair_recovers_before_shared_state(self):
        settings = self.options()
        publisher = PairPublisher(self.fs, settings, "eclipse",
                                  settings.eclipse.marker, settings.eclipse.arc,
                                  "marker_sha256", "arc_sha256")
        marker, arc = b"# verified marker\n", b"# verified arc\n"
        state = {"schema": 1, "products": {"eclipse": {
            "marker_sha256": hashlib.sha256(marker).hexdigest(),
            "arc_sha256": hashlib.sha256(arc).hexdigest()}}}
        write = self.fs.write
        failed = False

        def interrupt(path, data, **kwargs):
            nonlocal failed
            if path == settings.eclipse.arc and not failed:
                failed = True
                raise StorageError("simulated interruption")
            return write(path, data, **kwargs)

        self.fs.write = interrupt
        try:
            with self.assertRaisesRegex(StorageError, "interruption"):
                publisher.publish(state, None, first=marker, second=arc)
        finally:
            self.fs.write = write
        self.assertIsNotNone(self.fs.read(settings.eclipse.journal))
        self.assertIsNone(self.fs.read(settings.eclipse.arc))
        recover_pending(self.fs, settings)
        self.assertEqual(self.fs.read(settings.eclipse.marker), marker)
        self.assertEqual(self.fs.read(settings.eclipse.arc), arc)
        self.assertIsNone(self.fs.read(settings.eclipse.journal))

    def test_disabled_malformed_and_wrong_identity(self):
        settings = self.config()
        self.assertEqual(run(self.fs, settings).outcome, "disabled")
        self.assertIsNone(self.fs.read(settings.state))
        with self.assertRaisesRegex(ConfigError, "NASA central"):
            self.options("https://example.org/not-a-path.html")
        with self.assertRaisesRegex(FeedError, "identity"):
            parse_path(ANNULAR, TOTAL_URL)
        with self.assertRaisesRegex(FeedError, "incomplete"):
            parse_path(TOTAL.replace(b"Limits  11 38.0S", b"Missing 11 38.0S"),
                       TOTAL_URL)
