"""Cross-product label aging uses verified saved product times."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch

from totalmarker.features.clouds import run as run_clouds
from totalmarker.features.quake import run as run_quake
from totalmarker.features.storm import run as run_storm
from totalmarker.http import Fetcher, Response
from totalmarker.labels import legacy_time
from totalmarker.state import json_bytes
from totalmarker.storm_model import Storm, StormSnapshot, TrackPoint
from totalmarker.storm_sources import REQUIRED_GROUPS
from .support import Sandbox, ScriptedTransport, jpeg

NOW = 1_700_000_000


class SharedLabelRefreshTests(Sandbox):
    def row(self, settings, product):
        return next(line for line in self.fs.read(settings.labels).decode().splitlines()
                    if product in line)

    def test_legacy_spelling_is_corrected_without_moving_shared_rows(self):
        settings = self.config()
        old = ('# retain header\n'
               '-53 -13 "Earthquake Infomation Last Updated UNKNOWN" '
               'image=none color=Red position=pixel\n'
               '-91 -19 "Storm Infomation Last Updated UNKNOWN" '
               'color=Red image=none position=pixel\n'
               '-108 -13 "Volcano Infomation Last Updated UNKNOWN" '
               'color=Red image=none position=pixel\n')
        self.fs.write(settings.labels, old.encode())
        self.fs.write(settings.state, json_bytes({"schema": 1, "products": {
            product: {"successful_at": NOW}
            for product in ("quake", "storm", "volcano")}}))
        self.assertEqual(run_clouds(self.fs, settings, label_only=True, now=NOW).outcome,
                         "unchanged")
        expected = old.replace("Infomation", "Information").replace("color=Red", "color=Green")
        expected = expected.replace("UNKNOWN", legacy_time(NOW))
        expected += ('-98 -12 "Cloud Map Last Updated UNKNOWN" '
                     'color=Red image=none position=pixel\n')
        self.assertEqual(self.fs.read(settings.labels).decode(), expected)
        run_clouds(self.fs, settings, label_only=True, now=NOW)
        self.assertEqual(self.fs.read(settings.labels).decode(), expected)

    def test_cloud_label_only_ages_every_existing_marker_row_at_exact_boundaries(self):
        settings = self.config("LabelWarningQuake=100\nLabelWarningVolcano=200\n"
                               "LabelWarningStorm=300\nLabelWarningCloud=400\n")
        self.fs.write(settings.image, jpeg())
        old = ('# retain header\n'
               f'-108 -13 "Volcano Information Last Updated {legacy_time(NOW)}" '
               'image=none color=Green position=pixel\n'
               f'-53 -13 "Earthquake Information Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               f'-83 -13 "Storm Information Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               f'-68 -12 "Cloud Map Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               '-123 -13 "NORAD Information Last Updated UNKNOWN" color=Yellow\n')
        self.fs.write(settings.labels, old.encode())
        record = {"installed_at": NOW - 1000, "successful_at": NOW}
        self.fs.write(settings.state, json.dumps({"schema": 1, "products": {
            "quake": record.copy(),
            "volcano": {**record, "source_report_at": NOW - 86400},
            "storm": record.copy(),
            "clouds": {"installed_at": NOW - 1000},
        }}).encode())
        for age, quake, volcano, cloud in (
                (100, "Green", "Green", "Green"),
                (101, "Yellow", "Green", "Green"),
                (200, "Yellow", "Green", "Green"),
                (201, "Red", "Yellow", "Green"),
                (400, "Red", "Yellow", "Green"),
                (401, "Red", "Red", "Yellow")):
            with self.subTest(age=age):
                result = run_clouds(self.fs, settings, label_only=True, now=NOW + age)
                self.assertEqual(result.outcome, "unchanged")
                for product, color in (("Earthquake", quake), ("Volcano", volcano),
                                       ("Cloud Map", cloud)):
                    row = self.row(settings, product)
                    self.assertIn(legacy_time(NOW), row)
                    self.assertIn("color=" + color, row)
                label = self.fs.read(settings.labels).decode()
                self.assertEqual([line.split(' "')[0] for line in label.splitlines()[1:]],
                                 ['-108 -13', '-53 -13', '-83 -13', '-68 -12', '-123 -13'])
                self.assertIn('image=none color=' + volcano, self.row(settings, "Volcano"))
                self.assertIn(old.splitlines()[-1], label)
        products = self.read_state(settings)["products"]
        for product in ("quake", "volcano", "storm"):
            self.assertEqual(products[product]["installed_at"], NOW - 1000)
            self.assertEqual(products[product]["successful_at"], NOW)
        self.assertEqual(products["volcano"]["source_report_at"], NOW - 86400)
        self.assertEqual(products["clouds"]["source_created_at"], NOW)
        self.assertEqual(products["clouds"]["installed_at"], NOW - 1000)

        failed = run_clouds(self.fs, settings, now=NOW + 402,
                            fetcher=Fetcher(ScriptedTransport(Response(503, {}))),
                            environment={})
        self.assertEqual(failed.outcome, "failed")
        products = self.read_state(settings)["products"]
        self.assertEqual(products["quake"]["installed_at"], NOW - 1000)
        self.assertEqual(products["quake"]["successful_at"], NOW)
        self.assertEqual(products["volcano"]["installed_at"], NOW - 1000)
        self.assertEqual(products["volcano"]["successful_at"], NOW)
        self.assertEqual(products["volcano"]["source_report_at"], NOW - 86400)
        self.assertEqual(products["storm"]["installed_at"], NOW - 1000)
        self.assertEqual(products["storm"]["successful_at"], NOW)
        self.assertIn("color=Red", self.row(settings, "Earthquake"))
        self.assertIn("color=Red", self.row(settings, "Volcano"))

    def test_missing_marker_times_become_unknown_without_moving_rows(self):
        settings = self.config()
        self.fs.write(settings.image, jpeg())
        old = (f'-53 -13 "Earthquake Information Last Updated {legacy_time(NOW)}" '
               'image=none color=Green position=pixel\n'
               f'-83 -13 "Storm Information Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               f'-98 -13 "Volcano Information Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n')
        self.fs.write(settings.labels, old.encode())
        run_clouds(self.fs, settings, label_only=True, now=NOW)
        for product, coordinate in (("Earthquake", "-53 -13"),
                                    ("Storm", "-83 -13"),
                                    ("Volcano", "-98 -13")):
            row = self.row(settings, product)
            self.assertTrue(row.startswith(coordinate + ' "'))
            self.assertIn("Last Updated UNKNOWN", row)
            self.assertIn("color=Red", row)
        self.assertIn("image=none color=Red position=pixel",
                      self.row(settings, "Earthquake"))
        self.assertNotIn("quake", self.read_state(settings)["products"])
        self.assertNotIn("volcano", self.read_state(settings)["products"])
        self.assertNotIn("storm", self.read_state(settings)["products"])

    def test_old_state_uses_confirmed_publication_not_recent_poll_or_legacy_row(self):
        settings = self.config()
        self.fs.write(settings.image, jpeg())
        old = ''.join(
            f'-{53 + 15 * i} -13 "{product} Information Last Updated '
            f'{legacy_time(NOW - 10)}" color=Green image=none position=pixel\n'
            for i, product in enumerate(("Earthquake", "Storm", "Volcano")))
        self.fs.write(settings.labels, old.encode())
        self.fs.write(settings.state, json.dumps({"schema": 1, "products": {
            product: {"installed_at": NOW - 500, "checked_at": NOW - 10,
                      "fetched_at": NOW - 10, "legacy_label_at": NOW - 10}
            for product in ("quake", "storm", "volcano")}}).encode())
        run_clouds(self.fs, settings, label_only=True, now=NOW)
        for product in ("Earthquake", "Storm", "Volcano"):
            row = self.row(settings, product)
            self.assertIn(legacy_time(NOW - 500), row)
            self.assertNotIn(legacy_time(NOW - 10), row)
        products = self.read_state(settings)["products"]
        for product in ("quake", "storm", "volcano"):
            self.assertNotIn("successful_at", products[product])
            self.assertEqual(products[product]["installed_at"], NOW - 500)

    def test_waiting_quake_keeps_newer_storm_label_and_future_guard(self):
        settings = self.config("QuakeCheckIntervalSeconds=3600\n")
        fixture = Path(__file__).parent / "fixtures/usgs_quake_selected_20261019.geojson"
        initial = run_quake(self.fs, settings, now=NOW,
                            fetcher=Fetcher(ScriptedTransport(Response(
                                200, {"content-type": "application/geo+json"},
                                fixture.read_bytes()))))
        self.assertEqual(initial.outcome, "changed")

        before = NOW + 60.0
        storm_at = before + 0.000001
        after = storm_at + 0.001
        snapshot = StormSnapshot(
            (Storm("WP292023", "Test Storm", "STO",
                   TrackPoint(NOW + 30, 10, 100), 40, (), None, (), "not_issued"),),
            tuple((group, NOW + 30) for group in sorted(REQUIRED_GROUPS)),
            True, storm_at + 3600)
        storm_holding = threading.Event()
        release_storm = threading.Event()
        quake_waiting = threading.Event()
        quake_has_lock = threading.Event()
        original_lock = self.fs.lock
        original_time = time.time
        results = {}

        @contextmanager
        def watched_lock(path, *args, **kwargs):
            name = threading.current_thread().name
            if name == "waiting-quake":
                quake_waiting.set()
            with original_lock(path, *args, **kwargs):
                if name == "waiting-quake":
                    quake_has_lock.set()
                yield
                if name == "publishing-storm":
                    results["storm_row_before_quake"] = self.row(settings, "Storm Information")
                    results["marker_before_quake"] = self.fs.read(settings.storm.marker)
                    results["arc_before_quake"] = self.fs.read(settings.storm.arc)

        def paused_snapshot(*_args, **_kwargs):
            storm_holding.set()  # storm.run holds the real RootFS lock here.
            if not release_storm.wait(5):
                raise AssertionError("Storm was not released")
            return snapshot

        def clock():
            if threading.current_thread().name == "waiting-quake":
                return after if quake_has_lock.is_set() else before
            return original_time()

        class NoFetch:
            def fetch(self, *_args, **_kwargs):
                raise AssertionError("Cached quake or stubbed storm used a feed")

        def publishing_storm():
            try:
                results["storm"] = run_storm(self.fs, settings, fetcher=NoFetch(),
                                               now=storm_at)
            except Exception as error:
                results["storm_error"] = error

        def waiting_quake():
            try:
                results["quake"] = run_quake(self.fs, settings, fetcher=NoFetch())
            except Exception as error:
                results["quake_error"] = error

        storm_thread = threading.Thread(target=publishing_storm,
                                        name="publishing-storm", daemon=True)
        quake_thread = threading.Thread(target=waiting_quake,
                                        name="waiting-quake", daemon=True)
        self.fs.lock = watched_lock
        with (patch("totalmarker.features.quake.time.time", side_effect=clock),
              patch("totalmarker.features.storm.collect_snapshot",
                    side_effect=paused_snapshot)):
            try:
                storm_thread.start()
                self.assertTrue(storm_holding.wait(5), "Storm did not acquire the lock")
                quake_thread.start()
                self.assertTrue(quake_waiting.wait(5), "Quake did not reach the lock")
                self.assertFalse(quake_has_lock.is_set())
            finally:
                release_storm.set()
                if storm_thread.ident is not None:
                    storm_thread.join(5)
                if quake_thread.ident is not None:
                    quake_thread.join(5)
                self.fs.lock = original_lock
        self.assertFalse(storm_thread.is_alive())
        self.assertFalse(quake_thread.is_alive())
        for name in ("storm_error", "quake_error"):
            if name in results:
                raise results[name]
        self.assertEqual(results["storm"].outcome, "changed")
        self.assertEqual(results["quake"].outcome, "unchanged")
        self.assertIn(legacy_time(storm_at), results["storm_row_before_quake"])
        self.assertIn("color=Green", results["storm_row_before_quake"])
        products = self.read_state(settings)["products"]
        self.assertEqual(products["storm"]["successful_at"], storm_at)
        self.assertEqual(products["quake"]["successful_at"], after)
        self.assertEqual(self.fs.read(settings.storm.marker), results["marker_before_quake"])
        self.assertEqual(self.fs.read(settings.storm.arc), results["arc_before_quake"])
        self.assertIn(legacy_time(storm_at), self.row(settings, "Storm Information"))
        self.assertIn("color=Green", self.row(settings, "Storm Information"))
        self.assertIn(legacy_time(after), self.row(settings, "Earthquake Information"))

        # A genuinely future-dated saved time must still fail closed.
        products["storm"]["successful_at"] = after + 3600
        self.fs.write(settings.state, json_bytes({"schema": 1, "products": products}))
        run_clouds(self.fs, settings, label_only=True, now=after + 1)
        self.assertIn("Last Updated UNKNOWN", self.row(settings, "Storm Information"))
        self.assertIn("color=Red", self.row(settings, "Storm Information"))
        self.assertEqual(self.fs.read(settings.storm.marker), results["marker_before_quake"])
        self.assertEqual(self.fs.read(settings.storm.arc), results["arc_before_quake"])
