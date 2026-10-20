"""Validate portable public launchd examples without constraining local plists."""
from pathlib import Path
import plistlib
import unittest

from .support import PROJECT


DIRECTORY = PROJECT / "scripts/launchd"
JOBS = {"clouds", "earth-map", "quake", "start", "storm", "volcano"}


class LaunchdExampleTests(unittest.TestCase):
    def test_examples_are_parseable_literal_templates(self):
        examples = {path.name.removeprefix("local.xplanet.").removesuffix(".plist.example")
                    for path in DIRECTORY.glob("*.plist.example")}
        self.assertEqual(examples, JOBS)
        for job in sorted(JOBS):
            with self.subTest(job=job):
                path = DIRECTORY / f"local.xplanet.{job}.plist.example"
                data = path.read_bytes()
                self.assertEqual(data.count(b"__HOME__"), 1)
                self.assertNotIn(b"$HOME", data)
                self.assertNotIn(b"<USERNAME>", data)
                parsed = plistlib.loads(data)
                self.assertTrue(parsed["WorkingDirectory"].startswith(
                    "__HOME__/.xplanet"))
                rendered = plistlib.loads(
                    data.replace(b"__HOME__", b"/Users/example"))
                self.assertTrue(rendered["WorkingDirectory"].startswith(
                    "/Users/example/.xplanet"))

    def test_example_calendars_keep_the_original_cadences(self):
        schedules = {}
        for job in JOBS:
            path = DIRECTORY / f"local.xplanet.{job}.plist.example"
            schedules[job] = plistlib.loads(path.read_bytes()).get(
                "StartCalendarInterval")
        self.assertIsNone(schedules["start"])
        for job in ("clouds", "storm"):
            self.assertEqual(len(schedules[job]), 1)
            self.assertEqual(set(schedules[job][0]), {"Minute"})
        quake = schedules["quake"]
        self.assertEqual(len(quake), 3)
        self.assertTrue(all(set(entry) == {"Minute"} for entry in quake))
        minutes = sorted(entry["Minute"] for entry in quake)
        self.assertEqual([(minutes[(index + 1) % 3] - minutes[index]) % 60
                          for index in range(3)], [20, 20, 20])
        self.assertEqual(len(schedules["volcano"]), 1)
        self.assertEqual(set(schedules["volcano"][0]), {"Hour", "Minute"})
        self.assertEqual(len(schedules["earth-map"]), 1)
        self.assertEqual(set(schedules["earth-map"][0]), {"Day", "Hour", "Minute"})
        self.assertEqual(schedules["earth-map"][0]["Day"], 1)
        self.assertNotIn(schedules["clouds"][0]["Minute"], minutes)
        self.assertNotIn(schedules["storm"][0]["Minute"], minutes)
        self.assertNotEqual(schedules["clouds"][0], schedules["storm"][0])

    def test_examples_delegate_to_the_named_launcher_command(self):
        for job in sorted(JOBS):
            with self.subTest(job=job):
                example = DIRECTORY / f"local.xplanet.{job}.plist.example"
                fields = plistlib.loads(example.read_bytes())
                command = fields["ProgramArguments"]
                self.assertEqual(len(command), 2)
                expected = "../scripts/xplanet.sh" if job == "earth-map" else "./scripts/xplanet.sh"
                self.assertEqual(command[0], expected)
                self.assertEqual(command[1], "earth" if job == "earth-map" else job)
