"""Offline volcano contract checks; no live CAP requests or working-root outputs."""
from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from totalmarker.cli import main
from totalmarker.config import VolcanoOptions, load
from totalmarker.errors import ConfigError, FeedError
from totalmarker.features.volcano import run
from totalmarker.http import Fetcher, Response
from totalmarker.labels import legacy_time
from totalmarker.state import MarkerPublisher, json_bytes, load_state, recover_pending
from totalmarker.volcano_cap import parse_cap, render_body
from .support import PROJECT, Sandbox, ScriptedTransport

NOW = 1_700_000_000
SAMPLE = (PROJECT / "dev/tests/fixtures/legacy_gvp_cap.xml").read_bytes()


def cap_response(body=SAMPLE, status=200, **headers):
    return Response(status, {"Content-Type": "application/xml", **headers}, body)


def synthetic_info(name="Kīlauea &amp; Pele's", circle="19.421,-155.287 0",
                   location="Hawaiʻi"):
    return (f'<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><info>'
            f'<eventCode><valueName>Volcano Name</valueName><value>{name}</value></eventCode>'
            f'<area><areaDesc>{location}</areaDesc><circle>{circle}</circle></area>'
            f'</info></alert>').encode()


CAP11 = (b'<?xml version="1.0" encoding="ISO-8859-1"?>\n'
         b'<alert xmlns="urn:oasis:names:tc:emergency:cap:1.1">'
         b'<sent>2023-10-01T07:50:51-04:00</sent><info>'
         b'<headline>Volcanic activity report, 24-30 September 2023</headline>'
         b'<eventCode><valueName>Volcano Name</valueName><value>Ambrym</value></eventCode>'
         b'<area><areaDesc>Vanuatu</areaDesc><circle>-16.25,168.12 0</circle></area>'
         b'</info></alert>')


class VolcanoParserTests(Sandbox):
    def test_cap_11_report_sent_and_position(self):
        events = parse_cap(CAP11)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].name, events[0].lat, events[0].lon),
                         ("Ambrym", -16.25, 168.12))
        self.assertEqual(events[0].source_sent_at,
                         datetime.fromisoformat("2023-10-01T07:50:51-04:00").timestamp())

    def test_genuine_embedded_examples_keep_full_weekly_scope(self):
        events = parse_cap(SAMPLE)
        self.assertEqual([(e.name, e.location) for e in events],
                         [("Yasur", "Vanuatu"), ("Shiveluch", "Russia")])
        self.assertEqual([(e.lat, e.lon) for e in events],
                         [(-19.53, 169.442), (56.653, 161.36)])
        body = render_body(events, VolcanoOptions()).decode()
        self.assertEqual(len(body.splitlines()), 6)
        self.assertIn('"" color=Yellow symbolsize=4', body)
        self.assertIn('"" color=Red symbolsize=8', body)
        self.assertIn('"Yasur" color=Brown symbolsize=12 align=Below', body)
        self.assertIn('"Shiveluch" color=Brown symbolsize=12 align=Below', body)

    def test_namespaced_unicode_and_optional_legacy_styles(self):
        event = parse_cap(synthetic_info())[0]
        self.assertEqual((event.name, event.location), ("Kīlauea & Pele's", "Hawaiʻi"))
        options = replace(VolcanoOptions(), image="volcano.png",
                          image_transparent="42",
                          name_color="Gold", name_align="Above",
                          detail="<name> in <location>; <elev> at <lat>,<long>",
                          detail_color="Blue", detail_align="Below")
        lines = render_body([event], options).decode().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn('"Kīlauea & Pele\'s" align=Above color=Gold image=volcano.png transparent=42',
                      lines[2])
        self.assertIn('"Kīlauea & Pele\'s in Hawaiʻi; UNKNOWN at', lines[3])
        self.assertIn("color=Blue align=Below image=none", lines[3])
        hidden = render_body([event], replace(options, name_enabled=False, detail="")).decode()
        self.assertIn('"" color=Brown symbolsize=12', hidden)
        self.assertNotIn('"Kīlauea', hidden)

    def test_malformed_or_incomplete_feed_never_becomes_empty_success(self):
        cases = [
            b"", b"<alerts/>", b"<alerts><alert/></alerts>",
            b"<alert><info/></alert>", b"<alert><info>",
            synthetic_info(circle="91,0 0"),
            synthetic_info(circle="19,-155"),
            synthetic_info(circle="19,-155 -1"),
            synthetic_info(name=""),
            synthetic_info().replace(b"</area>", b"<circle>20,-155 0</circle></area>"),
            synthetic_info().replace(b"<areaDesc>", b"<wrongAreaDesc>"),
            b"<!DOCTYPE alert [<!ENTITY x 'bad'>]>" + synthetic_info(),
        ]
        for raw in cases:
            with self.subTest(raw=raw[:70]), self.assertRaises(FeedError):
                parse_cap(raw)

    def test_foreign_namespace_cannot_masquerade_as_cap_info(self):
        raw = (b'<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2" '
               b'xmlns:x="urn:wrong"><x:info><x:eventCode><x:valueName>Volcano Name'
               b'</x:valueName><x:value>False</x:value></x:eventCode></x:info></alert>')
        with self.assertRaises(FeedError):
            parse_cap(raw)


class VolcanoProviderTests(Sandbox):
    def test_old_cap_report_keeps_source_date_but_new_marker_label_is_green(self):
        settings = self.config("VolcanoCheckIntervalSeconds=0\n")
        result, _ = self.run_with(settings, cap_response(CAP11))
        self.assertEqual(result.outcome, "changed")
        self.assertEqual(result.source_report_at,
                         datetime.fromisoformat("2023-10-01T07:50:51-04:00").timestamp())
        label = self.fs.read(settings.labels).decode()
        self.assertIn(legacy_time(NOW), label)
        self.assertIn("color=Green", label)
        self.assertLess(result.source_report_at, result.installed_at)

    def run_with(self, settings, *responses, now=NOW):
        transport = ScriptedTransport(*responses)
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=now)
        return result, transport

    def test_first_publish_preserves_other_label_rows_and_originals(self):
        settings = self.config("VolcanoCheckIntervalSeconds=0\n")
        old = ('# preserve this header\n'
               '-53 -12 "Cloud Map Last Updated UNKNOWN" color=Red image=none position=pixel\n'
               '-68 -13 "Earthquake Information Last Updated UNKNOWN" color=Red image=none position=pixel\n')
        self.fs.write(settings.labels, old.encode())
        result, _ = self.run_with(settings, cap_response(
            ETag='"edition-1"', **{"Last-Modified": "Tue, 14 Nov 2023 20:00:00 GMT"}))
        self.assertEqual((result.outcome, result.count, result.source_report_at),
                         ("changed", 2, None))
        marker = self.fs.read(settings.volcano.marker)
        self.assertIn(b'"Yasur" color=Brown symbolsize=12 align=Below', marker)
        self.assertIn(b'"Shiveluch" color=Brown symbolsize=12 align=Below', marker)
        label = self.fs.read(settings.labels).decode()
        self.assertTrue(label.startswith(old))
        self.assertIn(f'-83 -13 "Volcano Information Last Updated {legacy_time(NOW)}"',
                      label)
        record = self.read_state(settings)["products"]["volcano"]
        self.assertEqual(record["installed_at"], NOW)
        self.assertEqual(record["checked_at"], NOW)
        self.assertEqual(record["fetched_at"], NOW)
        self.assertIsNone(record["source_report_at"])
        self.assertIsNotNone(record["source_modified_at"])
        self.assertNotEqual(record["source_modified_at"], record["installed_at"])
        self.assertFalse(self.fs.read(settings.volcano.journal))

    def test_cache_304_identical_and_failure_keep_last_good(self):
        settings = self.config("VolcanoCheckIntervalSeconds=3600\n")
        self.run_with(settings, cap_response(ETag='"edition-1"'))
        original_marker = self.fs.read(settings.volcano.marker)
        original_mtime = self.fs.file_stat(settings.volcano.marker).st_mtime_ns
        original_label = self.fs.read(settings.labels)
        result, transport = self.run_with(settings, now=NOW + 60)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(transport.calls, [])
        self.assertEqual((result.installed_at, result.successful_at), (NOW, NOW + 60))
        self.assertIn(legacy_time(NOW + 60).encode(), self.fs.read(settings.labels))
        result, transport = self.run_with(settings, cap_response(status=304),
                                          now=NOW + 3600)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(transport.calls[0][1]["If-None-Match"], '"edition-1"')
        result, _ = self.run_with(settings, cap_response(), now=NOW + 7200)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(self.fs.read(settings.volcano.marker), original_marker)
        self.assertEqual(self.fs.file_stat(settings.volcano.marker).st_mtime_ns,
                         original_mtime)
        self.assertNotEqual(self.fs.read(settings.labels), original_label)
        self.assertIn(legacy_time(NOW + 7200).encode(), self.fs.read(settings.labels))
        self.assertEqual(self.read_state(settings)["products"]["volcano"]["installed_at"], NOW)
        self.assertEqual(self.read_state(settings)["products"]["volcano"]["successful_at"],
                         NOW + 7200)
        for bad in [cap_response(b"<alerts/>"), cap_response(status=403),
                    TimeoutError("PRIVATE_RESPONSE")]:
            result, _ = self.run_with(settings, bad, now=NOW + 30_000)
            self.assertEqual(result.outcome, "failed")
            self.assertEqual(self.fs.read(settings.volcano.marker), original_marker)
            self.assertEqual(self.read_state(settings)["products"]["volcano"]["installed_at"],
                             NOW)
        self.assertNotIn(b"PRIVATE_RESPONSE", self.fs.read(settings.log))

    def test_successful_poll_refreshes_label_but_failure_does_not(self):
        settings = self.config("VolcanoCheckIntervalSeconds=0\n"
                               "LabelWarningVolcano=100\n")
        self.run_with(settings, cap_response())
        result, _ = self.run_with(settings, cap_response(), now=NOW + 101)
        self.assertEqual((result.installed_at, result.successful_at), (NOW, NOW + 101))
        self.assertIn(legacy_time(NOW + 101).encode(), self.fs.read(settings.labels))
        self.assertIn(b"color=Green", self.fs.read(settings.labels))
        record = self.read_state(settings)["products"]["volcano"]
        self.assertEqual((record["checked_at"], record["fetched_at"],
                          record["installed_at"]), (NOW + 101, NOW + 101, NOW))
        result, _ = self.run_with(settings, cap_response(b"<bad>"),
                                  now=NOW + 302)
        self.assertEqual(result.outcome, "failed")
        self.assertIn(b"color=Red", self.fs.read(settings.labels))
        record = self.read_state(settings)["products"]["volcano"]
        self.assertEqual(record["checked_at"], NOW + 302)
        self.assertEqual(record["fetched_at"], NOW + 101)
        self.assertEqual(record["installed_at"], NOW)
        self.assertEqual(record["successful_at"], NOW + 101)

    def test_changed_feed_advances_marker_and_label_once(self):
        settings = self.config("VolcanoCheckIntervalSeconds=0\n")
        self.run_with(settings, cap_response())
        prior = self.fs.read(settings.volcano.marker)
        result, _ = self.run_with(settings, cap_response(synthetic_info()),
                                  now=NOW + 1)
        self.assertEqual((result.outcome, result.count, result.installed_at),
                         ("changed", 1, NOW + 1))
        self.assertNotEqual(self.fs.read(settings.volcano.marker), prior)
        self.assertIn("Kīlauea".encode(), self.fs.read(settings.volcano.marker))
        self.assertIn(legacy_time(NOW + 1).encode(), self.fs.read(settings.labels))

    def test_existing_volcano_row_keeps_coordinates_order_and_options(self):
        settings = self.config("VolcanoCheckIntervalSeconds=0\n")
        old = ('-68 -12 "Cloud Map Last Updated UNKNOWN" color=Red\n'
               '-108 -13 "Volcano Information Last Updated Mon 1 Jan 2020,00:00:00" '
               'image=none color=Red position=pixel\n'
               '-53 -13 "Earthquake Information Last Updated UNKNOWN" color=Red\n')
        self.fs.write(settings.labels, old.encode())
        self.run_with(settings, cap_response())
        lines = self.fs.read(settings.labels).decode().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], old.splitlines()[0])
        self.assertTrue(lines[1].startswith('-108 -13 "Volcano Information Last Updated '))
        self.assertIn('image=none color=Green position=pixel', lines[1])
        self.assertEqual(lines[2], old.splitlines()[2])

    def test_initial_failure_creates_no_empty_marker_or_success_label(self):
        settings = self.config()
        result, _ = self.run_with(settings, cap_response(b"<alerts/>"))
        self.assertEqual(result.outcome, "failed")
        self.assertIsNone(self.fs.read(settings.volcano.marker))
        self.assertIsNone(self.fs.read(settings.labels))
        record = self.read_state(settings)["products"]["volcano"]
        self.assertEqual(record["checked_at"], NOW)
        self.assertNotIn("fetched_at", record)

    def test_corrupt_marker_and_state_fail_closed_without_erasing_last_good(self):
        settings = self.config("VolcanoCheckIntervalSeconds=0\n")
        self.run_with(settings, cap_response())
        marker = self.fs.read(settings.volcano.marker)
        self.fs.write(settings.volcano.marker, b"damaged")
        result, _ = self.run_with(settings, cap_response(status=304), now=NOW + 1)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(self.fs.read(settings.volcano.marker), b"damaged")
        result, _ = self.run_with(settings, cap_response(), now=NOW + 2)
        self.assertEqual(result.outcome, "changed")
        self.assertNotEqual(self.fs.read(settings.volcano.marker), b"damaged")
        self.assertNotEqual(marker, b"damaged")

    def test_pending_marker_recovery_finishes_state_and_label(self):
        settings = self.config()
        self.run_with(settings, cap_response())
        state = load_state(self.fs, settings.state)
        state["products"]["volcano"]["installed_at"] = NOW + 1
        marker = self.fs.read(settings.volcano.marker) + b"# recovered\n"
        state["products"]["volcano"]["marker_sha256"] = hashlib.sha256(marker).hexdigest()
        self.fs.write(settings.volcano.marker, marker)
        publisher = MarkerPublisher(self.fs, settings)
        intent = {"schema": 1, "paths": publisher.paths(), "state": state,
                  "label": '-53 -13 "Volcano recovered" color=Green\n',
                  "digest": hashlib.sha256(marker).hexdigest()}
        self.fs.write(settings.volcano.journal, json_bytes(intent))
        recover_pending(self.fs, settings)
        self.assertEqual(load_state(self.fs, settings.state)["products"]["volcano"]["installed_at"],
                         NOW + 1)
        self.assertIn(b"Volcano recovered", self.fs.read(settings.labels))
        self.assertIsNone(self.fs.read(settings.volcano.journal))

    def test_toml_options_and_cli_route_remain_offline_in_fixture(self):
        text = ('[cloud]\nprovider = "custom"\nurl = "https://cloud.example.invalid/c.jpg"\n'
                '[volcano]\nurl = "https://volcano.example.invalid/cap.xml"\n'
                'output = "markers/volcano-custom"\nname_enabled = false\n'
                'circle_size_outer = 15\n'
                '[labels]\nwarning_volcano_seconds = 123\n')
        (self.root / "config.toml").write_text(text)
        settings = load(self.fs, "config.toml")
        self.assertEqual(settings.volcano.circle_sizes, (4, 8, 15))
        self.assertFalse(settings.volcano.name_enabled)
        transport = ScriptedTransport(cap_response())
        output = io.StringIO()
        with (patch("totalmarker.features.volcano.Fetcher",
                    return_value=Fetcher(transport)), redirect_stdout(output)):
            status = main(["--root", str(self.root), "--config", "config.toml",
                           "volcano"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "changed")
        self.assertEqual(transport.calls[0][0], settings.volcano.url)
        self.assertIn(b"symbolsize=15", self.fs.read(settings.volcano.marker))
        self.assertNotIn(b'"Yasur"', self.fs.read(settings.volcano.marker))
        self.assertEqual((self.root / "config.toml").read_text(), text)

    def test_image_subpaths_are_supported_but_traversal_is_rejected(self):
        settings = self.config("VolcanoImageList=icons/volcano.png\n")
        self.assertEqual(settings.volcano.image, "icons/volcano.png")
        for image in ["../escape.png", "/tmp/escape.png", "a/../escape.png",
                      "bad image.png"]:
            with self.subTest(image=image):
                with self.assertRaises(ConfigError):
                    self.config(f"VolcanoImageList={image}\n")
