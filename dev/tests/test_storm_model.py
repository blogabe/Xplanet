"""Offline provider-neutral worldwide storm marker, track and label contracts."""
from dataclasses import replace

from totalmarker.errors import FeedError
from totalmarker.labels import legacy_time, render_storm
from totalmarker.storm_model import (ForecastPoint, Storm, StormSnapshot,
                                     StormStyle, TrackPoint, render_bodies,
                                     validate_snapshot)
from .support import Sandbox

BASE = 1_728_921_600  # October 2024 UTC; season label is independent of date year.
REQUIRED = frozenset({"nhc", "jtwc_west", "jtwc_south", "jtwc_indian"})


def sample_storm():
    current = TrackPoint(BASE, -16.5, 179.0)
    return Storm(
        id="SH012025", name="Ana", kind="STO", current=current, wind_kt=55,
        history=(TrackPoint(BASE - 12 * 3600, -15.0, 170.0),
                 TrackPoint(BASE - 6 * 3600, -16.0, 178.0)),
        forecast_base=current,
        forecast=(ForecastPoint(12, BASE + 12 * 3600, -17.5, -179.0),
                  ForecastPoint(24, BASE + 24 * 3600, -19.0, -175.0)),
        forecast_status="issued")


def snapshot(*storms, complete=True, groups=REQUIRED):
    return StormSnapshot(tuple(storms), tuple((group, BASE) for group in sorted(groups)),
                         complete)


class StormModelTests(Sandbox):
    def test_southern_season_identity_and_dateline_tracks(self):
        storm = sample_storm()
        self.assertEqual(storm.id[-4:], "2025")
        self.assertEqual(storm.current.at, BASE)  # October 2024 observation.
        markers, arcs = render_bodies(snapshot(storm), StormStyle(),
                                      required_groups=REQUIRED)
        marker = markers.decode()
        arc = arcs.decode()
        self.assertIn('"Ana" align=Above color=SkyBlue', marker)
        self.assertIn('"STO" align=Below color=SkyBlue', marker)
        self.assertIn('color=Blue', arc)
        self.assertIn('color=SkyBlue', arc)
        self.assertIn(' -16.50  179.00  -17.50 -179.00 color=SkyBlue', arc)
        self.assertEqual(len(marker.splitlines()), 2)
        self.assertEqual(len(arc.splitlines()), 4)

    def test_empty_is_valid_only_after_complete_global_source_checks(self):
        valid = snapshot()
        self.assertEqual(validate_snapshot(valid, required_groups=REQUIRED), valid)
        marker, arc = render_bodies(valid, StormStyle(), required_groups=REQUIRED)
        self.assertEqual((marker, arc), (b"\n", b"\n"))
        for invalid in [snapshot(complete=False),
                        snapshot(groups={"nhc", "jtwc_west"}),
                        StormSnapshot((), (), True)]:
            with self.subTest(invalid=invalid), self.assertRaises(FeedError):
                validate_snapshot(invalid, required_groups=REQUIRED)

    def test_duplicate_ids_and_invalid_coordinates_fail_closed(self):
        storm = sample_storm()
        with self.assertRaisesRegex(FeedError, "duplicated"):
            validate_snapshot(snapshot(storm, replace(storm, id="sh012025")),
                              required_groups=REQUIRED)
        with self.assertRaisesRegex(FeedError, "latitude"):
            validate_snapshot(snapshot(replace(storm, current=TrackPoint(BASE, -91, 179))),
                              required_groups=REQUIRED)

    def test_forecast_leads_and_valid_times_are_checked(self):
        storm = sample_storm()
        for invalid in [
            replace(storm, forecast=(ForecastPoint(0, BASE, -17, 179),)),
            replace(storm, forecast=(ForecastPoint(12, BASE + 24 * 3600, -17, 179),)),
            replace(storm, forecast_status="not_issued"),
            replace(storm, forecast_base=None),
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(FeedError):
                validate_snapshot(snapshot(invalid), required_groups=REQUIRED)

    def test_not_issued_forecast_and_legacy_style_options(self):
        storm = replace(sample_storm(), id="WP292024", name="Invest 29W",
                        kind="DEP", forecast_base=None, forecast=(),
                        forecast_status="not_issued", wind_kt=None)
        style = replace(StormStyle(), name_enabled=False, detail="<type> <speed>",
                        image="icons/storm.png", image_transparent="50",
                        track_forecast_color="Cyan")
        marker, arc = render_bodies(snapshot(storm), style, required_groups=REQUIRED)
        self.assertIn(b'"DEP UNKNOWN"', marker)
        self.assertIn(b'image=icons/storm.png transparent=50', marker)
        self.assertNotIn(b'color=Cyan', arc)
        self.assertNotIn(b'Invest 29W', marker)
        self.assertEqual(len(arc.splitlines()), 2)

    def test_older_source_time_does_not_age_new_marker_label(self):
        old = '-53 -12 "Cloud Map Last Updated UNKNOWN" color=Red image=none position=pixel\n'
        earlier = BASE - 7 * 86400
        data = StormSnapshot((sample_storm(),),
                             (("nhc", BASE), ("jtwc_west", BASE),
                              ("jtwc_south", earlier), ("jtwc_indian", BASE)), True)
        self.assertEqual(data.oldest_source_at, earlier)
        label = render_storm(old, BASE, BASE, 3 * 86400,
                             ("Green", "Yellow", "Red"))
        self.assertTrue(label.startswith(old))
        self.assertIn(f'-68 -13 "Storm Infomation Last Updated {legacy_time(BASE)}"',
                      label)
        self.assertIn('color=Green', label.splitlines()[1])

    def test_storm_label_exact_warning_and_red_boundaries(self):
        warning = 3 * 3600
        for age, color in ((0, "Green"), (warning, "Green"),
                           (warning + 1, "Yellow"), (2 * warning, "Yellow"),
                           (2 * warning + 1, "Red")):
            with self.subTest(age=age):
                label = render_storm("", BASE, BASE + age, warning,
                                     ("Green", "Yellow", "Red"))
                self.assertIn(f'Storm Infomation Last Updated {legacy_time(BASE)}', label)
                self.assertIn(f'color={color} image=none position=pixel', label)
