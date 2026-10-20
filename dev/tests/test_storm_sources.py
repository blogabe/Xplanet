"""Offline official NHC/JTWC storm-source and coherent publication checks."""
from dataclasses import replace
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from totalmarker.errors import FeedError, StorageError
from totalmarker.features.clouds import run as run_clouds
from totalmarker.features.storm import run
from totalmarker.http import Response
from totalmarker.labels import legacy_time
from totalmarker.state import StormPublisher, load_state, recover_pending
from totalmarker.storm_sources import (collect_snapshot, NHC_ATCF, NHC_INDEX,
                                       JTWC_RSS, _fresh_advisory, parse_jtwc_rss,
                                       parse_jtwc_warning, parse_nhc_best,
                                       parse_nhc_forecast)
from totalmarker.storm_advisory import parse_advisory
from totalmarker.storm_model import render_bodies, StormStyle
from .support import Sandbox

FIXTURES = Path(__file__).parent / "fixtures" / "storm"
NOW = datetime(2026, 10, 19, 9, tzinfo=timezone.utc).timestamp()
LIVE_NOW = datetime(2026, 10, 19, 15, tzinfo=timezone.utc).timestamp()
JTWC = "https://www.metoc.navy.mil/jtwc/products/"
LIVE_ABIO = FIXTURES / "jtwc-abio-20261019-1230.txt"


class MappedFetcher:
    def __init__(self):
        files = {
            NHC_INDEX: "nhc-current.json",
            JTWC_RSS: "jtwc-rss.xml",
            NHC_ATCF + "btk/bep212026.dat": "nhc-best.txt",
            NHC_ATCF + "aid_public/aep212026.dat.gz": "nhc-aid-selected.gz",
            JTWC + "wp2926web.txt": "jtwc-wp-warning.txt",
            JTWC + "wp2926.kmz": "jtwc-wp-track.kmz",
            JTWC + "sh0127web.txt": "jtwc-sh-warning.txt",
            JTWC + "sh0127.kmz": "jtwc-sh-track.kmz",
            JTWC + "abioweb.txt": "jtwc-abio-20261019.txt",
            JTWC + "abpwweb.txt": "jtwc-abpw-20261019.txt",
        }
        self.payloads = {url: (FIXTURES / name).read_bytes() for url, name in files.items()}
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.payloads:
            raise FeedError("Storm test source missing")
        return Response(200, {"date": "Mon, 19 Oct 2026 09:00:00 GMT"},
                        self.payloads[url])


def empty_rss():
    return ("<rss><channel>" + "".join(
        f"<item><title>{title}</title><pubDate>Mon, 19 Oct 26 09:00:00 +0000</pubDate>"
        "<description>No active tropical systems</description></item>"
        for title in ("Current Northwest Pacific/North Indian Ocean* Tropical Systems",
                      "Current Southern Hemisphere Tropical Systems")) +
            '<item><title>Current Significant Tropical Weather Advisories</title>'
            '<description><![CDATA[<a href="' + JTWC + 'abpwweb.txt">ABPW10</a>'
            '<a href="' + JTWC + 'abioweb.txt">ABIO10</a>]]></description></item>' +
            "</channel></rss>").encode()


def empty_advisory(kind):
    areas = (("NORTH INDIAN OCEAN AREA", "SOUTH INDIAN OCEAN AREA") if kind == "abio"
             else ("WESTERN NORTH PACIFIC AREA", "SOUTH PACIFIC AREA"))
    return (f"{kind.upper()}10 PGTW 190900\nISSUED/190900Z-200600ZOCT2026//\n" +
            "".join(f"{i}. {area}:\n   A. TROPICAL CYCLONE SUMMARY: NONE.\n"
                    "   B. TROPICAL DISTURBANCE SUMMARY: NONE.\n"
                    "   C. SUBTROPICAL SYSTEM SUMMARY: NONE.\n"
                    for i, area in enumerate(areas, 1))).encode()


class StormSourcesTests(Sandbox):
    def test_cache_revalidates_when_saved_source_coverage_expires(self):
        settings = self.config("StormCheckIntervalSeconds=86400\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        record = self.read_state(settings)["products"]["storm"]
        deadline = record["source_valid_until_at"]
        self.assertLess(deadline, NOW + settings.storm.interval)
        marker = self.fs.read(settings.storm.marker)
        arc = self.fs.read(settings.storm.arc)
        cached_fetcher = MappedFetcher()
        cached = run(self.fs, settings, fetcher=cached_fetcher, now=NOW + 60)
        self.assertEqual(cached.outcome, "unchanged")
        self.assertEqual(cached_fetcher.calls, [])
        expired_fetcher = MappedFetcher()
        expired = run(self.fs, settings, fetcher=expired_fetcher, now=deadline + 1)
        self.assertEqual(expired.outcome, "failed")
        self.assertTrue(expired_fetcher.calls)
        self.assertEqual(expired.successful_at, NOW + 60)
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), (marker, arc))

    def test_official_global_fixture_observations_history_and_forecasts(self):
        fetcher = MappedFetcher()
        snapshot = collect_snapshot(fetcher, now=NOW)
        self.assertEqual([storm.id for storm in snapshot.storms],
                         ["EP212026", "WP292026", "SH012027", "IO962026", "SH932027"])
        self.assertEqual(len(fetcher.calls), 10)
        nhc, west, south, io_invest, sh_invest = snapshot.storms
        self.assertEqual((nhc.current.lat, nhc.current.lon), (19.7, -107.6))
        self.assertEqual((west.current.lat, west.current.lon), (14.3, 138.4))
        self.assertEqual((south.current.lat, south.current.lon), (-18.6, -160.2))
        self.assertGreater(len(nhc.history), 20)
        self.assertGreater(len(west.history), 20)
        self.assertGreater(len(south.history), 10)
        self.assertEqual((nhc.forecast[0].lead_hours, west.forecast[0].lead_hours,
                          south.forecast[0].lead_hours), (3, 12, 12))
        self.assertEqual(south.current.at, datetime(2026, 10, 18, 18,
                                                     tzinfo=timezone.utc).timestamp())
        self.assertEqual((io_invest.current.lat, io_invest.current.lon), (4.0, 57.0))
        self.assertEqual((sh_invest.current.lat, sh_invest.current.lon), (3.2, 57.1))
        self.assertEqual([item.name for item in (io_invest, sh_invest)],
                         ["Invest 96A", "Invest 93S"])
        self.assertTrue(all(not item.history and not item.forecast and
                            item.forecast_status == "not_issued"
                            for item in (io_invest, sh_invest)))
        marker, arc = render_bodies(snapshot, StormStyle(), required_groups={
            "nhc", "jtwc_west", "jtwc_indian", "jtwc_south"})
        self.assertIn(b'"Invest 96A"', marker)
        self.assertNotIn(b'   4.00   57.00', arc)

    def test_nhc_stale_or_past_forecast_fails_and_keeps_last_good_files(self):
        path = NHC_ATCF + "aid_public/aep212026.dat.gz"
        original = gzip.decompress((FIXTURES / "nhc-aid-selected.gz").read_bytes())
        stale = gzip.compress(original.replace(b"2026101900", b"2026100100"))
        index_at = datetime(2026, 10, 19, 3, tzinfo=timezone.utc).timestamp()
        with self.assertRaisesRegex(FeedError, "cycle is stale"):
            parse_nhc_forecast(stale, "EP212026", index_at)
        short = gzip.compress(b"\n".join(
            line for line in original.splitlines()
            if line.split(b",")[5].strip() in {b"0", b"3"}) + b"\n")
        with self.assertRaisesRegex(FeedError, "no future positions"):
            parse_nhc_forecast(short, "EP212026", index_at + 3 * 3600)
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        marker, arc = self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)
        fetcher = MappedFetcher()
        fetcher.payloads[path] = stale
        failed = run(self.fs, settings, fetcher=fetcher, now=NOW + 60)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.successful_at, NOW)
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), (marker, arc))

    def test_jtwc_warning_adjacent_month_year_and_leap_day(self):
        for year, observed_day, rss_month, forecast_day in (
                (2023, "282100Z", 3, "010900Z"),
                (2024, "292100Z", 3, "010900Z"),
                (2023, "312100Z", 1, "010900Z")):
            with self.subTest(year=year, observed_day=observed_day):
                rss_year = year + (rss_month == 1)
                rss_at = datetime(rss_year, rss_month, 1, 0,
                                  tzinfo=timezone.utc).timestamp()
                bulletin = ("SUBJ/TROPICAL CYCLONE 07B (SEVEN) WARNING NR 002//\n"
                            "WARNING POSITION:\n"
                            f"{observed_day} --- NEAR 20.3N 88.9E\n"
                            "MAX SUSTAINED WINDS - 035 KT\n"
                            "FORECASTS:\n12 HRS, VALID AT:\n"
                            f"{forecast_day} --- 21.9N 90.2E\n").encode()
                current, _, _, forecast, _ = parse_jtwc_warning(
                    bulletin, f"IO07{year}", rss_at)
                expected = datetime(year, 2 if rss_month == 3 else 12,
                                    int(observed_day[:2]), 21,
                                    tzinfo=timezone.utc).timestamp()
                self.assertEqual(current.at, expected)
                self.assertEqual(forecast[0].at, expected + 12 * 3600)

    def test_advisory_sections_current_positions_and_historical_io_format(self):
        abio = parse_advisory((FIXTURES / "jtwc-abio-20261019.txt").read_bytes(), "abio")
        abpw = parse_advisory((FIXTURES / "jtwc-abpw-20261019.txt").read_bytes(), "abpw")
        self.assertEqual([area.cyclone_none for area in abio.areas], [True, True])
        self.assertEqual([area.warned_codes for area in abpw.areas], [("29W",), ("01P",)])
        self.assertEqual(len(abio.invests), 2)
        for filename, identity, start in (("bio012023.dat", "IO012023", (7.7, 91.4)),
                                          ("bio082023.dat", "IO082023", (7.5, 88.0))):
            with self.subTest(identity=identity):
                points = parse_nhc_best((FIXTURES / filename).read_bytes(), identity,
                                        datetime(2023, 12, 31, tzinfo=timezone.utc).timestamp())
                self.assertGreater(len(points), 1)
                self.assertEqual((points[0].lat, points[0].lon), start)

    def test_authentic_advisory_validity_boundaries(self):
        captured = FIXTURES / "live-20261020-promotion"
        examples = (
            ("abpw", "jtwc-abpw-advisory.txt", (2026, 10, 20, 6, 0),
             (2026, 10, 21, 6, 0), (2026, 10, 20, 18, 28)),
            ("abio", "jtwc-abio-advisory.txt", (2026, 10, 20, 8, 30),
             (2026, 10, 20, 18, 0), (2026, 10, 20, 12, 0)),
        )
        for kind, filename, start, end, inside in examples:
            advisory = parse_advisory((captured / filename).read_bytes(), kind)
            issue = datetime(*start, tzinfo=timezone.utc).timestamp()
            until = datetime(*end, tzinfo=timezone.utc).timestamp()
            self.assertEqual((advisory.issue_at, advisory.valid_until_at), (issue, until))
            for label, now in (("before", issue - 3601), ("start", issue),
                               ("inside", datetime(*inside, tzinfo=timezone.utc).timestamp()),
                               ("end", until), ("after", until + 1)):
                with self.subTest(kind=kind, boundary=label):
                    if label in {"before", "after"}:
                        with self.assertRaisesRegex(FeedError, kind.upper() + " advisory is stale"):
                            _fresh_advisory(advisory, now, kind)
                    else:
                        _fresh_advisory(advisory, now, kind)
            _fresh_advisory(advisory, issue - 3600, kind)  # Existing clock skew.

    def test_authentic_wrapped_abio_interval_and_boundary_controls(self):
        captured = FIXTURES / "live-20261020-interval-wrap"
        record = json.loads((captured / "manifest.json").read_text())["records"][0]
        raw = (captured / record["path"]).read_bytes()
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()),
                         (record["bytes"], record["sha256"]))
        boundary = b"201800Z-\r\n211800Z"
        self.assertIn(boundary, raw)
        advisory = parse_advisory(raw, "abio")
        issue = datetime(2026, 10, 20, 18, tzinfo=timezone.utc).timestamp()
        until = datetime(2026, 10, 21, 18, tzinfo=timezone.utc).timestamp()
        self.assertEqual((advisory.issue_at, advisory.valid_until_at), (issue, until))
        self.assertEqual(advisory.areas[1].warned_codes, ("02S",))
        _fresh_advisory(advisory, datetime(2026, 10, 20, 19, 25,
                                            tzinfo=timezone.utc).timestamp(), "abio")
        for replacement in (b"201800Z-211800Z", b"201800Z- 211800Z",
                            b"201800Z-\t211800Z", b"201800Z-\n211800Z",
                            b"201800Z- \r\n\t211800Z"):
            with self.subTest(replacement=replacement):
                changed = parse_advisory(raw.replace(boundary, replacement), "abio")
                self.assertEqual((changed.issue_at, changed.valid_until_at), (issue, until))
        for replacement in (b"201800Z-\r\n\r\n211800Z",
                            b"201800Z-X\r\n211800Z",
                            b"201800Z-\r211800Z",
                            b"201800Z-\r\n211801Z",
                            b"201800Z-\r\n211800ZOCT2026///"):
            with self.subTest(replacement=replacement):
                with self.assertRaises(FeedError):
                    parse_advisory(raw.replace(boundary, replacement), "abio")
        duplicate = raw.replace(b"RMKS/", b"ISSUED/201800Z-211800ZOCT2026//\r\nRMKS/", 1)
        with self.assertRaisesRegex(FeedError, "lacks a dated issue interval"):
            parse_advisory(duplicate, "abio")
        wrong_header = raw.replace(b"ABIO10 PGTW 201800", b"ABIO10 PGTW 201801", 1)
        with self.assertRaisesRegex(FeedError, "header disagrees with issue time"):
            parse_advisory(wrong_header, "abio")

    def test_advisory_month_year_rollover_and_invalid_intervals(self):
        rollover = empty_advisory("abpw")
        for header, interval, issue, until in (
                (b"311800", b"311800Z-010600ZNOV2026", (2026, 10, 31, 18),
                 (2026, 11, 1, 6)),
                (b"311800", b"311800Z-010600ZJAN2027", (2026, 12, 31, 18),
                 (2027, 1, 1, 6))):
            with self.subTest(interval=interval):
                body = rollover.replace(b"ABPW10 PGTW 190900", b"ABPW10 PGTW " + header)
                body = body.replace(b"190900Z-200600ZOCT2026", interval)
                advisory = parse_advisory(body, "abpw")
                self.assertEqual(advisory.issue_at,
                                 datetime(*issue, tzinfo=timezone.utc).timestamp())
                self.assertEqual(advisory.valid_until_at,
                                 datetime(*until, tzinfo=timezone.utc).timestamp())
        original = (FIXTURES / "live-20261020-promotion/jtwc-abpw-advisory.txt").read_bytes()
        for bad in (b"200600Z-200500ZOCT2026",  # Reversed.
                    b"200600Z-210700ZOCT2026",  # More than 24 hours.
                    b"200600Z-320600ZOCT2026",  # Invalid calendar day.
                    b"200600Z-210600ZOCT2026/",  # Extra terminator.
                    b"200600Z-UNSET"):
            with self.subTest(interval=bad):
                body = original.replace(b"200600Z-210600ZOCT2026", bad)
                with self.assertRaises(FeedError):
                    parse_advisory(body, "abpw")
        missing_end = original.replace(b"200600Z-210600ZOCT2026//",
                                       b"200600Z-210600ZOCT2026/")
        with self.assertRaisesRegex(FeedError, "lacks a dated issue interval"):
            parse_advisory(missing_end, "abpw")
        duplicated = original.replace(b"RMKS/", b"ISSUED/200600Z-210600ZOCT2026//\r\nRMKS/", 1)
        with self.assertRaisesRegex(FeedError, "lacks a dated issue interval"):
            parse_advisory(duplicated, "abpw")
        wrong_header = original.replace(b"ABPW10 PGTW 200600", b"ABPW10 PGTW 200601", 1)
        with self.assertRaisesRegex(FeedError, "header disagrees with issue time"):
            parse_advisory(wrong_header, "abpw")
        for extra in (b"ISSUED/200600Z-201700ZOCT2026/",
                      b"ISSUED/200600Z-201700ZOCT2026///",
                      b"ISSUED/200600Z-201700ZOCT2026//JUNK",
                      b"ISSUED 200600Z-201700ZOCT2026//"):
            with self.subTest(extra=extra):
                body = original.replace(b"RMKS/", extra + b"\r\nRMKS/", 1)
                with self.assertRaisesRegex(FeedError, "lacks a dated issue interval"):
                    parse_advisory(body, "abpw")
        extra_subject = original.replace(
            b"RMKS/",
            b"SUBJ/SIGNIFICANT TROPICAL WEATHER ADVISORY FOR THE "
            b"WESTERN AND SOUTH PACIFIC OCEANS/BROKEN\r\nRMKS/", 1)
        with self.assertRaisesRegex(FeedError, "lacks a dated issue interval"):
            parse_advisory(extra_subject, "abpw")

    def test_advisory_validity_controls_cache_and_last_good_pair(self):
        settings = self.config("StormCheckIntervalSeconds=86400\n")
        short = MappedFetcher()
        url = JTWC + "abpwweb.txt"
        short.payloads[url] = short.payloads[url].replace(
            b"190900Z-200600ZOCT2026", b"190900Z-191200ZOCT2026")
        first = run(self.fs, settings, fetcher=short, now=NOW)
        self.assertEqual(first.outcome, "changed", first.message)
        deadline = datetime(2026, 10, 19, 12, tzinfo=timezone.utc).timestamp()
        self.assertEqual(self.read_state(settings)["products"]["storm"]["source_valid_until_at"],
                         deadline)
        saved = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        cached_fetcher = MappedFetcher()
        cached = run(self.fs, settings, fetcher=cached_fetcher, now=deadline)
        self.assertEqual((cached.outcome, cached.successful_at), ("unchanged", deadline))
        self.assertEqual(cached_fetcher.calls, [])
        expired = MappedFetcher()
        expired.payloads[url] = short.payloads[url]
        failed = run(self.fs, settings, fetcher=expired, now=deadline + 1)
        self.assertEqual((failed.outcome, failed.successful_at), ("failed", deadline))
        self.assertIn("ABPW advisory is stale", failed.message)
        self.assertIn(url, expired.calls)
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), saved)
        refreshed = MappedFetcher()
        recovered = run(self.fs, settings, fetcher=refreshed, now=deadline + 2)
        self.assertEqual((recovered.outcome, recovered.successful_at),
                         ("unchanged", deadline + 2))
        self.assertIn(url, refreshed.calls)
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), saved)
        self.assertEqual(recovered.source_at, first.source_at)
        self.assertIn(legacy_time(deadline + 2), self.fs.read(settings.labels).decode())

    def test_official_dissipated_invest_is_excluded_without_reusing_previous_fix(self):
        bulletin = LIVE_ABIO.read_bytes()
        advisory = parse_advisory(bulletin, "abio")
        self.assertEqual([area.cyclone_none for area in advisory.areas], [True, True])
        self.assertEqual([storm.id for storm in advisory.invests], ["SH932027"])
        self.assertEqual((advisory.invests[0].current.lat,
                          advisory.invests[0].current.lon), (3.2, 57.1))
        for broken in (
                bulletin.replace(b"HAS DISSIPATED", b"HAS WEAKENED"),
                bulletin.replace(b"IN THE NEXT 24 HOURS.",
                                 b"IN THE NEXT 24 HOURS. IS NOW LOCATED NEAR 4.0N 57.0E.", 1),
                bulletin.replace(b"4.0N 57.0E HAS DISSIPATED",
                                 b"94.0N 57.0E HAS DISSIPATED")):
            with self.subTest(broken=broken[:120]), self.assertRaises(FeedError):
                parse_advisory(broken, "abio")

    def test_dissipated_bulletin_publishes_coherent_fixture_marker_and_arcs(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        fetcher = MappedFetcher()
        fetcher.payloads[JTWC + "abioweb.txt"] = LIVE_ABIO.read_bytes()
        result = run(self.fs, settings, fetcher=fetcher, now=LIVE_NOW)
        self.assertEqual((result.outcome, result.count), ("changed", 4), result.message)
        marker = self.fs.read(settings.storm.marker).decode()
        arc = self.fs.read(settings.storm.arc).decode()
        self.assertIn('"Invest 93S"', marker)
        self.assertIn('"Champi"', marker)
        self.assertIn('"Wati"', marker)
        self.assertIn('"Trudy"', marker)
        self.assertIn('   3.20   57.10 "Invest 93S"', marker)
        self.assertNotIn('"Invest 96A"', marker)
        self.assertNotIn(' 4.00   57.00 ', marker)
        self.assertGreater(len(marker.splitlines()), 5)
        self.assertGreater(len(arc.splitlines()), 10)
        self.assertIn("color=Blue", arc)
        self.assertIn("color=SkyBlue", arc)
        self.assertIn("   7.60  -88.00    7.40  -89.20 color=Blue", arc)
        self.assertIn("  19.60 -107.40   19.70 -107.60 color=SkyBlue", arc)
        self.assertNotIn(" 4.00   57.00 ", arc)
        self.assertIn("Storm Infomation Last Updated", self.fs.read(settings.labels).decode())

    def test_ambiguous_advisory_fails_instead_of_promoting_previous_position(self):
        original = (FIXTURES / "jtwc-abio-20261019.txt").read_bytes()
        for corrupt in (original.replace(b"IS NOW LOCATED NEAR 4.0N 57.0E", b"IS NOW AT 4.0N 57.0E"),
                        original.replace(b"INVEST 96A", b"INVEST 96W"),
                        original.replace(b"TROPICAL DISTURBANCE SUMMARY:", b"DISTURBANCE SUMMARY:", 1)):
            with self.subTest(corrupt=corrupt[:60]), self.assertRaises(FeedError):
                parse_advisory(corrupt, "abio")

    def test_nonempty_subtropical_section_fails_closed_and_retains_outputs(self):
        empty = empty_advisory("abio")
        changed = empty.replace(b"C. SUBTROPICAL SYSTEM SUMMARY: NONE.",
                                b"C. SUBTROPICAL SYSTEM SUMMARY: "
                                b"(1) SUBTROPICAL SYSTEM INVEST 96A IS CURRENT.", 1)
        with self.assertRaisesRegex(FeedError, "subtropical summary"):
            parse_advisory(changed, "abio")
        hidden = empty.replace(b"C. SUBTROPICAL SYSTEM SUMMARY: NONE.",
                               b"C. SUBTROPICAL SYSTEM SUMMARY: NONE.\n"
                               b"(1) SUBTROPICAL SYSTEM INVEST 96A IS CURRENT.", 1)
        with self.assertRaisesRegex(FeedError, "subtropical summary"):
            parse_advisory(hidden, "abio")
        terminated = empty + b"//\nNNNN\n"
        self.assertEqual(len(parse_advisory(terminated, "abio").invests), 0)
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        marker, arc = self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)
        fetcher = MappedFetcher()
        fetcher.payloads[JTWC + "abioweb.txt"] = changed
        failed = run(self.fs, settings, fetcher=fetcher, now=NOW + 60)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.successful_at, NOW)
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), (marker, arc))

    def test_missing_or_corrupt_global_source_cannot_become_empty_success(self):
        for url, raw in [(JTWC_RSS, b"<rss/>"),
                         (JTWC + "sh0127.kmz", b"not a zip"),
                         (NHC_INDEX, b'{}'),
                         (JTWC + "abioweb.txt", b"missing")]:
            fetcher = MappedFetcher()
            fetcher.payloads[url] = raw
            with self.subTest(url=url), self.assertRaises(FeedError):
                collect_snapshot(fetcher, now=NOW)
        with self.assertRaisesRegex(FeedError, "confirm an empty"):
            parse_jtwc_rss(empty_rss().replace(b"No active", b"Unknown"))
        with self.assertRaisesRegex(FeedError, "both significant advisories"):
            parse_jtwc_rss(empty_rss().replace(b"abioweb.txt", b"missing.txt"))

    def test_explicit_empty_at_both_official_indexes_is_valid(self):
        fetcher = MappedFetcher()
        fetcher.payloads[NHC_INDEX] = b'{"activeStorms":[]}'
        fetcher.payloads[JTWC_RSS] = empty_rss()
        fetcher.payloads[JTWC + "abioweb.txt"] = empty_advisory("abio")
        fetcher.payloads[JTWC + "abpwweb.txt"] = empty_advisory("abpw")
        result = collect_snapshot(fetcher, now=NOW)
        self.assertEqual(result.storms, ())
        self.assertEqual(len(fetcher.calls), 4)

    def test_wrong_season_and_stale_categories_fail_closed(self):
        fetcher = MappedFetcher()
        fetcher.payloads[JTWC_RSS] = fetcher.payloads[JTWC_RSS].replace(
            b"sh0127web.txt", b"sh0126web.txt")
        with self.assertRaises(FeedError):
            collect_snapshot(fetcher, now=NOW)
        fetcher = MappedFetcher()
        with self.assertRaisesRegex(FeedError, "stale"):
            collect_snapshot(fetcher, now=NOW + 48 * 3600)

    def test_cache_hit_refreshes_successful_time_without_fetching(self):
        settings = self.config("StormCheckIntervalSeconds=3600\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        before_marker = self.fs.read(settings.storm.marker)
        before_arc = self.fs.read(settings.storm.arc)
        fetcher = MappedFetcher()
        result = run(self.fs, settings, fetcher=fetcher, now=NOW + 60)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(fetcher.calls, [])
        self.assertEqual((result.installed_at, result.successful_at), (NOW, NOW + 60))
        self.assertEqual(self.fs.read(settings.storm.marker), before_marker)
        self.assertEqual(self.fs.read(settings.storm.arc), before_arc)
        self.assertIn(legacy_time(NOW + 60), self.fs.read(settings.labels).decode())

    def test_runtime_change_unchanged_failure_and_valid_empty(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        fetcher = MappedFetcher()
        old = '-53 -12 "Cloud Map Last Updated UNKNOWN" color=Red image=none position=pixel\n'
        self.fs.write(settings.labels, old.encode())
        first = run(self.fs, settings, fetcher=fetcher, now=NOW)
        self.assertEqual((first.outcome, first.count), ("changed", 5))
        marker1 = self.fs.read(settings.storm.marker)
        arc1 = self.fs.read(settings.storm.arc)
        label1 = self.fs.read(settings.labels).decode()
        self.assertIn('"Champi"', marker1.decode())
        self.assertIn('"Invest 96A"', marker1.decode())
        self.assertIn('"Invest 93S"', marker1.decode())
        self.assertIn('color=SkyBlue', arc1.decode())
        self.assertIn(f'-68 -13 "Storm Infomation Last Updated {legacy_time(NOW)}"',
                      label1)
        again = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW + 60)
        self.assertEqual(again.outcome, "unchanged")
        self.assertEqual((again.installed_at, again.successful_at), (NOW, NOW + 60))
        label_after_again = self.fs.read(settings.labels).decode()
        self.assertIn(legacy_time(NOW + 60), label_after_again)
        broken = MappedFetcher()
        broken.payloads[JTWC + "sh0127.kmz"] = b"broken"
        failed = run(self.fs, settings, fetcher=broken, now=NOW + 120)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(self.fs.read(settings.storm.marker), marker1)
        self.assertEqual(self.fs.read(settings.storm.arc), arc1)
        self.assertEqual(failed.successful_at, NOW + 60)
        self.assertEqual(self.fs.read(settings.labels).decode(), label_after_again)
        bad_advisory = MappedFetcher()
        bad_advisory.payloads[JTWC + "abioweb.txt"] = b"broken"
        failed = run(self.fs, settings, fetcher=bad_advisory, now=NOW + 150)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(self.fs.read(settings.storm.marker), marker1)
        self.assertEqual(self.fs.read(settings.storm.arc), arc1)
        self.assertEqual(failed.successful_at, NOW + 60)
        self.assertEqual(self.fs.read(settings.labels).decode(), label_after_again)
        empty = MappedFetcher()
        empty.payloads[NHC_INDEX] = b'{"activeStorms":[]}'
        empty.payloads[JTWC_RSS] = empty_rss()
        empty.payloads[JTWC + "abioweb.txt"] = empty_advisory("abio")
        empty.payloads[JTWC + "abpwweb.txt"] = empty_advisory("abpw")
        cleared = run(self.fs, settings, fetcher=empty, now=NOW + 180)
        self.assertEqual((cleared.outcome, cleared.count), ("changed", 0))
        self.assertNotIn('"Champi"', self.fs.read(settings.storm.marker).decode())
        self.assertNotIn('color=SkyBlue', self.fs.read(settings.storm.arc).decode())
        self.assertIn(legacy_time(NOW + 180), self.fs.read(settings.labels).decode())

    def test_successful_execution_age_survives_failure_and_other_product_refresh(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        fetcher = MappedFetcher()
        fetcher.payloads[JTWC + "abioweb.txt"] = LIVE_ABIO.read_bytes()
        snapshot = collect_snapshot(fetcher, now=LIVE_NOW)
        warning = settings.storm.warning
        self.assertLess(snapshot.oldest_source_at, LIVE_NOW - 2 * warning)

        with patch("totalmarker.features.storm.collect_snapshot", return_value=snapshot):
            changed = run(self.fs, settings, now=LIVE_NOW)
        self.assertEqual(changed.outcome, "changed")
        marker = self.fs.read(settings.storm.marker)
        arc = self.fs.read(settings.storm.arc)
        first_record = self.read_state(settings)["products"]["storm"]
        self.assertEqual(first_record["installed_at"], LIVE_NOW)
        self.assertEqual(first_record["source_at"], snapshot.oldest_source_at)
        label = self.fs.read(settings.labels).decode()
        row = next(line for line in label.splitlines() if "Storm Infomation" in line)
        self.assertIn(legacy_time(LIVE_NOW), row)
        self.assertIn("color=Green", row)

        with patch("totalmarker.features.storm.collect_snapshot", return_value=snapshot):
            unchanged = run(self.fs, settings, now=LIVE_NOW + 60)
        self.assertEqual(unchanged.outcome, "unchanged")
        unchanged_record = self.read_state(settings)["products"]["storm"]
        self.assertEqual(unchanged_record["installed_at"], LIVE_NOW)
        self.assertEqual(unchanged_record["source_at"], snapshot.oldest_source_at)
        self.assertEqual(unchanged_record["fetched_at"], LIVE_NOW + 60)
        self.assertEqual(unchanged_record["successful_at"], LIVE_NOW + 60)
        self.assertIn(legacy_time(LIVE_NOW + 60), self.fs.read(settings.labels).decode())

        run_clouds(self.fs, settings, label_only=True,
                   now=LIVE_NOW + 60 + warning + 1)
        refreshed = self.fs.read(settings.labels).decode()
        row = next(line for line in refreshed.splitlines() if "Storm Infomation" in line)
        self.assertIn(legacy_time(LIVE_NOW + 60), row)
        self.assertIn("color=Yellow", row)
        self.assertEqual(self.read_state(settings)["products"]["storm"]["installed_at"],
                         LIVE_NOW)

        with patch("totalmarker.features.storm.collect_snapshot",
                   side_effect=FeedError("synthetic source failure")):
            failed = run(self.fs, settings, now=LIVE_NOW + 60 + 2 * warning + 1)
        self.assertEqual(failed.outcome, "failed")
        final_record = self.read_state(settings)["products"]["storm"]
        self.assertEqual(final_record["installed_at"], LIVE_NOW)
        self.assertEqual(final_record["source_at"], snapshot.oldest_source_at)
        self.assertEqual(final_record["fetched_at"], LIVE_NOW + 60)
        self.assertEqual(final_record["successful_at"], LIVE_NOW + 60)
        self.assertEqual(self.fs.read(settings.storm.marker), marker)
        self.assertEqual(self.fs.read(settings.storm.arc), arc)
        row = next(line for line in self.fs.read(settings.labels).decode().splitlines()
                   if "Storm Infomation" in line)
        self.assertIn(legacy_time(LIVE_NOW + 60), row)
        self.assertIn("color=Red", row)

    def test_partial_two_file_publication_recovers_both_outputs(self):
        settings = self.config()
        publisher = StormPublisher(self.fs, settings)
        state = load_state(self.fs, settings.state)
        marker = b"# storm marker\n1 2 \"Test\"\n"
        arc = b"# storm arc\n1 2 3 4 color=Blue\n"
        state["products"]["storm"] = {
            "marker_sha256": hashlib.sha256(marker).hexdigest(),
            "arc_sha256": hashlib.sha256(arc).hexdigest()}
        original_write = self.fs.write
        failed_once = False

        def fail_arc(path, data, **kwargs):
            nonlocal failed_once
            if path == settings.storm.arc and not failed_once:
                failed_once = True
                raise StorageError("simulated interruption")
            return original_write(path, data, **kwargs)

        self.fs.write = fail_arc
        with self.assertRaises(StorageError):
            publisher.publish(state, "label\n", marker=marker, arc=arc)
        self.fs.write = original_write
        self.assertIsNotNone(self.fs.read(settings.storm.journal))
        recover_pending(self.fs, settings)
        self.assertEqual(self.fs.read(settings.storm.marker), marker)
        self.assertEqual(self.fs.read(settings.storm.arc), arc)
        self.assertEqual(self.fs.read(settings.labels), b"label\n")
        self.assertIsNone(self.fs.read(settings.storm.journal))
