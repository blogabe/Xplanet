"""Offline USGS GeoJSON and quake publication contracts."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from totalmarker.config import QuakeOptions
from totalmarker.errors import FeedError
from totalmarker.features.quake import run
from totalmarker.http import Fetcher, Response
from totalmarker.labels import legacy_time
from totalmarker.quake_geojson import parse_geojson, render_body
from totalmarker.state import MarkerPublisher, json_bytes, load_state, recover_pending
from .support import Sandbox, ScriptedTransport

NOW = 1_700_000_000
SAMPLE = (Path(__file__).parent / "fixtures/usgs_quake_selected_20261019.geojson").read_bytes()


def feature(ident="us1", mag=6.0, lon=-155.3, lat=19.4, depth=12.5,
            origin=1_699_990_000_000, updated=1_699_995_000_000, place="Hawaiʻi"):
    return {"type": "Feature", "id": ident,
            "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
            "properties": {"mag": mag, "time": origin, "updated": updated,
                           "place": place, "type": "earthquake"}}


def feed(*features, generated=1_699_999_000_000):
    return json.dumps({"type": "FeatureCollection",
                       "metadata": {"generated": generated, "count": len(features)},
                       "features": list(features)}).encode()


def response(body, **headers):
    return Response(200, {"content-type": "application/geo+json", **headers}, body)


class QuakeTests(Sandbox):
    def run_with(self, settings, *responses, now=NOW):
        transport = ScriptedTransport(*responses)
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=now)
        return result, transport

    def test_config_selects_all_duration_and_size_feeds(self):
        settings = self.config()
        self.assertEqual(settings.quake.url,
                         "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson")
        self.assertEqual(settings.quake.minimum, 6)
        self.assertEqual(settings.quake.warning, 10800)
        for duration in ("Day", "Week", "Month"):
            for size in ("All", "1.0", "2.5", "4.5", "Significant"):
                selected = self.config(f"QuakeReportingDuration={duration}\n"
                                       f"QuakeReportingSize={size}\n")
                self.assertTrue(selected.quake.url.endswith(
                    f"{size.lower()}_{duration.lower()}.geojson"))

    def test_official_selected_snapshot_fixture(self):
        events, generated = parse_geojson(SAMPLE, 6)
        self.assertEqual(generated, 1_792_381_805)
        self.assertEqual([event.id for event in events],
                         ["us6000u2mq", "us6000u24c", "us6000u214",
                          "us6000u1z5", "us6000u1wn"])
        self.assertEqual(len(render_body(events, QuakeOptions()).splitlines()), 10)

    def test_parser_accepts_nullable_optional_fields_and_correct_coordinate_order(self):
        f = feature(depth=None, updated=None, place=None)
        f["properties"]["magType"] = None
        events, generated = parse_geojson(feed(f, feature("small", 5.9)), 6)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].lat, events[0].lon, events[0].depth),
                         (19.4, -155.3, None))
        self.assertIsNone(events[0].revised_at)
        self.assertEqual(generated, 1_699_999_000)
        self.assertIn('"6.0" color=Yellow align=Above',
                      render_body(events, QuakeOptions()).decode())

    def test_visible_marker_styling_and_origin_detail(self):
        options = replace(QuakeOptions(), detail="<date> <time> <location> <depth>",
                          pixel_min=4, pixel_max=20, detail_color="Blue",
                          image="icons/quake.png", image_transparent="30")
        event = parse_geojson(feed(feature()), 6)[0][0]
        text = render_body([event], options).decode()
        self.assertIn('image=icons/quake.png color=Salmon transparent=30', text)
        self.assertIn('2023-11-14 19:26:40 Hawaiʻi   12.5', text)
        self.assertIn('color=Blue align=Above', text)
        self.assertIn('symbolsize=13.6',
                      render_body([event], replace(options, image="")).decode())

    def test_bad_feed_does_not_become_empty_success(self):
        for raw in [b"", b"{}", b'{"type":"FeatureCollection","features":[]}',
                    feed(feature()).replace(b'"count": 1', b'"count": 2'),
                    feed(feature(lat=91)), feed(feature(origin=None)),
                    feed(feature()).replace(b'"mag": 6.0', b'"mag": NaN')]:
            with self.subTest(raw=raw[:50]), self.assertRaises(FeedError):
                parse_geojson(raw, 6)
        self.assertEqual(parse_geojson(feed(feature(mag=None)), 6)[0], [])

    def test_huge_numeric_field_is_a_feed_failure(self):
        with self.assertRaisesRegex(FeedError, "magnitude"):
            parse_geojson(feed(feature(mag=10 ** 400)), 6)

    def test_huge_number_retains_last_good_and_ages_label(self):
        settings = self.config("QuakeCheckIntervalSeconds=0\n")
        first, _ = self.run_with(settings, response(feed(feature())))
        self.assertEqual(first.outcome, "changed")
        marker = self.fs.read(settings.quake.marker)
        later = NOW + 2 * settings.quake.warning + 1
        failed, _ = self.run_with(settings,
                                  response(feed(feature(mag=10 ** 400))), now=later)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.successful_at, NOW)
        self.assertEqual(self.fs.read(settings.quake.marker), marker)
        row = next(line for line in self.fs.read(settings.labels).decode().splitlines()
                   if "Earthquake Infomation" in line)
        self.assertIn(legacy_time(NOW), row)
        self.assertIn("color=Red", row)
        self.assertEqual(self.read_state(settings)["products"]["quake"]["last_outcome"],
                         "failed")
        self.assertIn(b'"outcome": "failed"', self.fs.read(settings.log))

    def test_publish_revision_age_out_failure_and_valid_empty(self):
        settings = self.config("QuakeCheckIntervalSeconds=0\n")
        old = '-53 -12 "Cloud Map Last Updated UNKNOWN" color=Red image=none position=pixel\n'
        self.fs.write(settings.labels, old.encode())
        first, _ = self.run_with(settings, response(feed(feature()), etag='"a"'))
        self.assertEqual((first.outcome, first.count), ("changed", 1))
        marker1 = self.fs.read(settings.quake.marker)
        label1 = self.fs.read(settings.labels).decode()
        self.assertTrue(label1.startswith(old))
        self.assertIn(f'-68 -13 "Earthquake Infomation Last Updated {legacy_time(NOW)}"',
                      label1)
        record = self.read_state(settings)["products"]["quake"]
        self.assertEqual((record["latest_origin_at"], record["latest_revision_at"],
                          record["feed_generated_at"], record["fetched_at"],
                          record["installed_at"], record["successful_at"]),
                         (1_699_990_000, 1_699_995_000, 1_699_999_000, NOW, NOW, NOW))
        revised = feature(updated=1_699_998_000_000)
        same, _ = self.run_with(settings, response(feed(
            revised, generated=1_699_999_600_000)), now=NOW + 600)
        self.assertEqual(same.outcome, "unchanged")
        self.assertEqual(self.fs.read(settings.quake.marker), marker1)
        self.assertEqual(same.installed_at, NOW)
        self.assertEqual(same.successful_at, NOW + 600)
        self.assertIn(legacy_time(NOW + 600), self.fs.read(settings.labels).decode())
        changed, _ = self.run_with(settings, response(feed(
            feature(mag=6.4, updated=1_699_999_500_000))), now=NOW + 1200)
        self.assertEqual(changed.outcome, "changed")
        self.assertIn('"6.4"', self.fs.read(settings.quake.marker).decode())
        marker2 = self.fs.read(settings.quake.marker)
        failed, _ = self.run_with(settings, response(b"bad"), now=NOW + 1300)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.successful_at, NOW + 1200)
        self.assertEqual(self.fs.read(settings.quake.marker), marker2)
        self.assertIn(legacy_time(NOW + 1200), self.fs.read(settings.labels).decode())
        empty, _ = self.run_with(settings, response(feed()), now=NOW + 1400)
        self.assertEqual((empty.outcome, empty.count), ("changed", 0))
        self.assertNotIn('symbolsize=', self.fs.read(settings.quake.marker).decode())
        self.assertIn(legacy_time(NOW + 1400), self.fs.read(settings.labels).decode())

    def test_failed_initial_fetch_creates_no_success_label(self):
        settings = self.config("QuakeCheckIntervalSeconds=0\n")
        result, _ = self.run_with(settings, response(b"broken"))
        self.assertEqual(result.outcome, "failed")
        self.assertIsNone(self.fs.read(settings.quake.marker))
        self.assertIsNone(self.fs.read(settings.labels))

    def test_feed_304_uses_last_good(self):
        settings = self.config("QuakeCheckIntervalSeconds=0\n")
        self.run_with(settings, response(feed(feature()), etag='"v1"'))
        before = self.fs.read(settings.quake.marker)
        result, transport = self.run_with(settings, Response(304, {}), now=NOW + 60)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(transport.calls[0][1]["If-None-Match"], '"v1"')
        self.assertEqual(self.fs.read(settings.quake.marker), before)
        self.assertEqual((result.installed_at, result.successful_at), (NOW, NOW + 60))
        self.assertIn(legacy_time(NOW + 60), self.fs.read(settings.labels).decode())

    def test_cache_hit_refreshes_successful_time_without_fetching(self):
        settings = self.config("QuakeCheckIntervalSeconds=3600\n")
        self.run_with(settings, response(feed(feature())))
        before = self.fs.read(settings.quake.marker)
        result, transport = self.run_with(settings, now=NOW + 60)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(transport.calls, [])
        self.assertEqual((result.installed_at, result.successful_at), (NOW, NOW + 60))
        self.assertEqual(self.fs.read(settings.quake.marker), before)
        self.assertIn(legacy_time(NOW + 60), self.fs.read(settings.labels).decode())

    def test_source_selection_change_with_same_rendered_set_refreshes_execution_time(self):
        first = self.config("QuakeCheckIntervalSeconds=0\n")
        self.run_with(first, response(feed(feature())))
        before = self.fs.read(first.quake.marker)
        second = self.config("QuakeCheckIntervalSeconds=0\nQuakeReportingSize=2.5\n")
        result, transport = self.run_with(second, response(feed(feature())), now=NOW + 60)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(self.fs.read(second.quake.marker), before)
        self.assertEqual(self.read_state(second)["products"]["quake"]["installed_at"], NOW)
        self.assertEqual(result.successful_at, NOW + 60)
        self.assertTrue(transport.calls[0][0].endswith("2.5_week.geojson"))

    def test_pending_quake_marker_recovery_finishes_state_and_label(self):
        settings = self.config()
        self.run_with(settings, response(feed(feature())))
        state = load_state(self.fs, settings.state)
        state["products"]["quake"]["installed_at"] = NOW + 1
        marker = self.fs.read(settings.quake.marker) + b"# recovered\n"
        digest = hashlib.sha256(marker).hexdigest()
        state["products"]["quake"]["marker_sha256"] = digest
        self.fs.write(settings.quake.marker, marker)
        publisher = MarkerPublisher(self.fs, settings, "quake")
        self.fs.write(settings.quake.journal, json_bytes({
            "schema": 1, "paths": publisher.paths(), "state": state,
            "label": '-53 -13 "Earthquake recovered" color=Green\n',
            "digest": digest}))
        recover_pending(self.fs, settings)
        self.assertEqual(load_state(self.fs, settings.state)["products"]["quake"]["installed_at"],
                         NOW + 1)
        self.assertIn(b"Earthquake recovered", self.fs.read(settings.labels))
        self.assertIsNone(self.fs.read(settings.quake.journal))
