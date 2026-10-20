"""Cross-product label aging uses verified saved product times."""
import json

from totalmarker.features.clouds import run as run_clouds
from totalmarker.http import Fetcher, Response
from totalmarker.labels import legacy_time
from .support import Sandbox, ScriptedTransport, jpeg

NOW = 1_700_000_000


class SharedLabelRefreshTests(Sandbox):
    def row(self, settings, product):
        return next(line for line in self.fs.read(settings.labels).decode().splitlines()
                    if product in line)

    def test_cloud_label_only_ages_every_existing_marker_row_at_exact_boundaries(self):
        settings = self.config("LabelWarningQuake=100\nLabelWarningVolcano=200\n"
                               "LabelWarningStorm=300\nLabelWarningCloud=400\n")
        self.fs.write(settings.image, jpeg())
        old = ('# retain header\n'
               f'-108 -13 "Volcano Infomation Last Updated {legacy_time(NOW)}" '
               'image=none color=Green position=pixel\n'
               f'-53 -13 "Earthquake Infomation Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               f'-83 -13 "Storm Infomation Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               f'-68 -12 "Cloud Map Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               '-123 -13 "NORAD Infomation Last Updated UNKNOWN" color=Yellow\n')
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
        old = (f'-53 -13 "Earthquake Infomation Last Updated {legacy_time(NOW)}" '
               'image=none color=Green position=pixel\n'
               f'-83 -13 "Storm Infomation Last Updated {legacy_time(NOW)}" '
               'color=Green image=none position=pixel\n'
               f'-98 -13 "Volcano Infomation Last Updated {legacy_time(NOW)}" '
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
            f'-{53 + 15 * i} -13 "{product} Infomation Last Updated '
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
