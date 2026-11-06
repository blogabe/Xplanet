"""Offline official NHC/JTWC storm-source and coherent publication checks."""
from dataclasses import replace
from datetime import datetime, timezone
import gzip
import hashlib
from io import BytesIO
import json
import zlib
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from totalmarker.errors import FeedError, StorageError
from totalmarker.features.clouds import run as run_clouds
from totalmarker.features.storm import (run, _SourceCapture, REJECT_CAPTURE,
                                        CAPTURE_BODY_LIMIT, CAPTURE_TOTAL_LIMIT)
from totalmarker.http import Response
from totalmarker.labels import legacy_time
from totalmarker.state import StormPublisher, load_state, recover_pending
from totalmarker.storm_sources import (collect_snapshot, NHC_ATCF, NHC_INDEX,
                                       JTWC_RSS, _fresh_advisory, parse_jtwc_rss,
                                       parse_jtwc_warning, parse_jtwc_formation_alert, parse_jtwc_kmz, parse_nhc_best,
                                       _jtwc_url,
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

    def test_nhc_forecast_exact_age_boundary_and_latest_eligible_cycle(self):
        def row(cycle, lead, lat):
            return f"EP, 21, {cycle}, 00, OFCL, {lead}, {lat}N, 1076W\n".encode()
        # Distinct positions identify the selected cycle. A future cycle must
        # not supersede the latest cycle at or before the current advisory.
        raw = b"".join(row(cycle, lead, lat) for cycle, lat in
                       (("2026101800", 180), ("2026101900", 190), ("2026102006", 200))
                       for lead in (0, 48))
        current = datetime(2026, 10, 20, tzinfo=timezone.utc).timestamp()
        body = gzip.compress(raw)
        base, forecast = parse_nhc_forecast(body, "EP212026", current)
        self.assertEqual((base.lat, base.at), (19.0, current - 86400))
        self.assertEqual(forecast[0].at, current + 86400)
        with self.assertRaisesRegex(FeedError, "cycle is stale"):
            parse_nhc_forecast(body, "EP212026", current + 1)

    def test_malformed_external_containers_and_url_are_feed_errors(self):
        # Valid gzip header followed by a deflate block with reserved BTYPE=3.
        corrupt_gzip = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07" + b"\x00" * 8
        with self.assertRaisesRegex(FeedError, "gzip is invalid"):
            parse_nhc_forecast(corrupt_gzip, "EP212026", NOW)
        with self.assertRaisesRegex(FeedError, "invalid JTWC product URL"):
            _jtwc_url(JTWC.replace(".mil/", ".mil:invalid/") + "wp2926web.txt")
        packed = BytesIO()
        with ZipFile(packed, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("doc.kml", "<kml>external payload</kml>")
        damaged = bytearray(packed.getvalue())
        data_offset = 30 + int.from_bytes(damaged[26:28], "little") + int.from_bytes(damaged[28:30], "little")
        damaged[data_offset] = 7  # Reserved deflate BTYPE, inside a valid ZIP container.
        with self.assertRaisesRegex(FeedError, "KMZ is invalid"):
            parse_jtwc_kmz(bytes(damaged), None, "WP292026", "Champi")
        # The bounded ZIP reader can reject deflate, unsupported compression or
        # encryption before XML parsing. Normalize only that external boundary.
        for error in (zlib.error("invalid block"), NotImplementedError("compression"),
                      RuntimeError("encrypted member")):
            with self.subTest(error=type(error).__name__):
                with patch("totalmarker.storm_sources.ZipFile.open", side_effect=error):
                    with self.assertRaisesRegex(FeedError, "KMZ is invalid"):
                        parse_jtwc_kmz(packed.getvalue(), None, "WP292026", "Champi")

    def test_corrupt_forecast_records_failure_and_retains_last_good_pair(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        before = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        broken = MappedFetcher()
        broken.payloads[NHC_ATCF + "aid_public/aep212026.dat.gz"] = (
            b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07" + b"\x00" * 8)
        failed = run(self.fs, settings, fetcher=broken, now=NOW + 60)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.successful_at, NOW)
        record = self.read_state(settings)["products"]["storm"]
        self.assertEqual(record["checked_at"], NOW + 60)
        self.assertIn("gzip is invalid", record["last_error"]["message"])
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)), before)

    def test_rejected_capture_is_bounded_public_only_and_latest_only(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        class Bodies:
            def fetch(self, url, **kwargs):
                return Response(200, {"authorization": "private-header"}, b"x" * 100000)
        capture = _SourceCapture(Bodies())
        for i in range(30):
            capture.fetch(NHC_INDEX)
        capture.fetch(JTWC + "abpwweb.txt")
        capture.fetch(JTWC + "abioweb.txt")
        for i in range(8):
            capture.fetch(NHC_INDEX)
        capture.fetch("https://user:secret@example.invalid/private?token=secret")
        capture.save(self.fs, settings, NOW)
        raw = self.fs.read(REJECT_CAPTURE)
        data = json.loads(raw)
        self.assertLessEqual(len(raw), 384 * 1024)
        self.assertEqual(len(data["responses"]), 32)
        self.assertEqual(data["omitted_responses"], 9)
        self.assertEqual(sum(r["captured_bytes"] for r in data["responses"]), CAPTURE_TOTAL_LIMIT)
        self.assertTrue(all(r["captured_bytes"] <= CAPTURE_BODY_LIMIT for r in data["responses"]))
        self.assertTrue(all(r["truncated"] for r in data["responses"]))
        self.assertEqual([r["captured_bytes"] for r in data["responses"][30:32]],
                         [CAPTURE_BODY_LIMIT, CAPTURE_BODY_LIMIT])
        self.assertEqual(data["responses"][0]["sha256"], hashlib.sha256(b"x" * 100000).hexdigest())
        self.assertNotIn(b"private-header", raw)
        self.assertNotIn(b"secret", raw)
        # Normal success and subsequent cache hits must retain failure evidence.
        self.assertEqual(run(self.fs, settings, fetcher=MappedFetcher(), now=NOW).outcome, "changed")
        cached = replace(settings, storm=replace(settings.storm, interval=3600))
        self.assertEqual(run(self.fs, cached, fetcher=MappedFetcher(), now=NOW + 1).outcome, "unchanged")
        self.assertEqual(self.fs.read(REJECT_CAPTURE), raw)
        # A later rejection atomically replaces, rather than accumulates, data.
        later = _SourceCapture(Bodies())
        later.fetch(JTWC_RSS)
        later.save(self.fs, settings, NOW + 2)
        replacement = json.loads(self.fs.read(REJECT_CAPTURE))
        self.assertEqual(replacement["at"], NOW + 2)
        self.assertEqual(len(replacement["responses"]), 1)

    def test_rejected_capture_refuses_output_collisions_and_contained_aliases(self):
        settings = self.config()
        capture = _SourceCapture(MappedFetcher())
        capture.fetch(NHC_INDEX)
        # Every configured output and journal is protected, including disabled
        # products and case aliases on case-insensitive installation volumes.
        examples = [replace(settings, state=REJECT_CAPTURE),
                    replace(settings, log=REJECT_CAPTURE.upper()),
                    replace(settings, norad=replace(settings.norad, satellite=REJECT_CAPTURE)),
                    replace(settings, eclipse=replace(settings.eclipse, journal=REJECT_CAPTURE)),
                    replace(settings, labels=".state/totalmarker")]
        for configured in examples:
            with self.subTest(configured=configured.state):
                capture.save(self.fs, configured, NOW)
                self.assertIsNone(self.fs.read(REJECT_CAPTURE))
        self.fs.write("markers/keep", b"last-good")
        target = self.root / REJECT_CAPTURE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(self.root / "markers/keep")
        capture.save(self.fs, settings, NOW)
        self.assertEqual(self.fs.read("markers/keep"), b"last-good")
        self.assertTrue(target.is_symlink())

    def test_capture_storage_failure_preserves_primary_failure(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        original = self.fs.write
        def guarded(path, body, **kwargs):
            if str(path) == REJECT_CAPTURE:
                raise StorageError("capture cannot be written")
            return original(path, body, **kwargs)
        broken = MappedFetcher()
        broken.payloads[NHC_INDEX] = b"not-json"
        with patch.object(self.fs, "write", side_effect=guarded):
            failed = run(self.fs, settings, fetcher=broken, now=NOW)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.message, "Storm NHC active index is invalid JSON")
        self.assertEqual(self.read_state(settings)["products"]["storm"]["last_error"]["message"],
                         failed.message)

    def test_capture_optional_path_oserror_preserves_primary_failure(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        # A disabled product's unusable configured path is irrelevant to this
        # failed storm refresh. Collision inspection must remain best effort.
        self.fs.write("satellites/block", b"regular file")
        settings = replace(settings, norad=replace(settings.norad,
                                                   satellite="satellites/block/item"))
        broken = MappedFetcher()
        broken.payloads[NHC_INDEX] = b"not-json"
        failed = run(self.fs, settings, fetcher=broken, now=NOW)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.message, "Storm NHC active index is invalid JSON")
        self.assertEqual(self.read_state(settings)["products"]["storm"]["last_error"]["message"],
                         failed.message)
        self.assertEqual(self.fs.read("satellites/block"), b"regular file")

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

    def test_jtwc_observations_after_season_boundary_reject_previous_season(self):
        # Synthetic contract checks only: no claim about provider continuity
        # conventions or permission to accept old-season identities.
        for basin, code, year, month in (("WP", "02W", 2027, 1),
                                         ("IO", "02B", 2027, 1),
                                         ("SH", "02S", 2027, 7)):
            season = year + (basin == "SH")
            rss_at = datetime(year, month, 1, 3, tzinfo=timezone.utc).timestamp()
            warning = (f"SUBJ/TROPICAL CYCLONE {code} (TWO) WARNING NR 002//\n"
                       "WARNING POSITION:\n010000Z --- NEAR 10.0N 80.0E\n"
                       "FORECASTS:\n12 HRS, VALID AT:\n011200Z --- NEAR 11.0N 81.0E\n").encode()
            invest = "93" + code[-1]
            alert = ("WTIO21 PGTW 010000\n"
                     f"SUBJ/TROPICAL CYCLONE FORMATION ALERT (INVEST {invest})//\n"
                     "IS NOW LOCATED NEAR 10.0N 80.0E\n").encode()
            with self.subTest(basin=basin, boundary=(year, month)):
                for parser, body, number, message in (
                        (parse_jtwc_warning, warning, "02", "warning season"),
                        (parse_jtwc_formation_alert, alert, "93", "formation alert season")):
                    current = parser(body, basin + number + str(season), rss_at)[0]
                    self.assertEqual(current.at, rss_at - 3 * 3600)
                    with self.assertRaisesRegex(FeedError, message + " disagrees with RSS"):
                        parser(body, basin + number + str(season - 1), rss_at)

    def test_synthetic_final_warning_without_forecast_keeps_entire_last_good_layer(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        saved = (self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc))
        broken = MappedFetcher()
        path = JTWC + "wp2926web.txt"
        original = broken.payloads[path]
        self.assertIn(b"FORECASTS:", original)
        # Deliberately synthetic: preserve a real observed position but omit
        # all future points, as a possible final product might do.
        broken.payloads[path] = original.split(b"FORECASTS:", 1)[0] + b"FINAL WARNING\n"
        failed = run(self.fs, settings, fetcher=broken, now=NOW + 60)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.message, "Storm JTWC warning lacks issued forecast points")
        self.assertEqual(failed.successful_at, NOW)
        self.assertEqual((self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)), saved)

    def test_explicit_null_nhc_forecast_is_accepted_without_fetching_a_deck(self):
        fetcher = MappedFetcher()
        index = json.loads(fetcher.payloads[NHC_INDEX])
        index["activeStorms"][0]["forecastTrack"] = None
        fetcher.payloads[NHC_INDEX] = json.dumps(index).encode()
        forecast_url = NHC_ATCF + "aid_public/aep212026.dat.gz"
        del fetcher.payloads[forecast_url]  # An accidental request must fail.
        snapshot = collect_snapshot(fetcher, now=NOW)
        storm = next(storm for storm in snapshot.storms if storm.id == "EP212026")
        self.assertEqual((storm.forecast_status, storm.forecast_base, storm.forecast),
                         ("not_issued", None, ()))
        self.assertNotIn(forecast_url, fetcher.calls)
        marker, arc = render_bodies(snapshot, StormStyle(), required_groups={
            "nhc", "jtwc_west", "jtwc_indian", "jtwc_south"})
        self.assertIn(b'Trudy', marker)
        self.assertTrue(arc)  # Other storms and observed history remain valid.

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
                        with self.assertRaisesRegex(FeedError, kind.upper() + " advisory is " +
                                                    ("future-dated" if label == "before" else "stale")):
                            _fresh_advisory(advisory, now, kind)
                    else:
                        _fresh_advisory(advisory, now, kind)
            _fresh_advisory(advisory, issue - 3600, kind)  # Existing clock skew.

    def test_authentic_abpw_reissue_has_distinct_header_and_validity_start(self):
        # Official JTWC ABPW and RSS captured October 27, 2026.
        raw = (FIXTURES / "jtwc-abpw-20261026-2230.txt").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "510e0b6e8b3c4b765c852725a3efafd3936f5a49ad79da4f61e9ef472d6f7395")
        advisory = parse_advisory(raw, "abpw")
        start = datetime(2026, 10, 26, 22, tzinfo=timezone.utc).timestamp()
        issued = datetime(2026, 10, 26, 22, 30, tzinfo=timezone.utc).timestamp()
        until = datetime(2026, 10, 27, 6, tzinfo=timezone.utc).timestamp()
        self.assertEqual((advisory.issue_at, advisory.issued_at,
                          advisory.valid_until_at, advisory.reissued),
                         (start, issued, until, True))
        self.assertEqual(advisory.areas[0].warned_codes, ("30W",))
        rss = (FIXTURES / "jtwc-rss-20261027-reissue.xml").read_bytes()
        self.assertEqual(hashlib.sha256(rss).hexdigest(),
                         "c3a695d2f549b04e33f2552a673d1fdd3eafd637970a1dd3dad34d9b2838cb20")
        _, _, advisory_links = parse_jtwc_rss(rss)
        self.assertEqual(advisory_links["abpw"],
                         (JTWC + "abpwweb.txt", ("Reissued", "26/2230Z")))
        for now in (issued - 3600, issued, until):
            _fresh_advisory(advisory, now, "abpw")
        for now, reason in ((issued - 3601, "future-dated"), (until + 1, "stale")):
            with self.assertRaisesRegex(FeedError, "ABPW advisory is " + reason):
                _fresh_advisory(advisory, now, "abpw")

        invalid = (
            raw.replace(b"REISSUED/", b"ISSUED/", 1),
            raw.replace(b"ABPW10 PGTW 262230", b"ABPW10 PGTW 262159", 1),
            raw.replace(b"ABPW10 PGTW 262230", b"ABPW10 PGTW 270600", 1),
            raw.replace(b"ABPW10 PGTW 262230", b"ABPW10 PGTW 322230", 1),
            raw.replace(b"MSGID/", b"ABPW10 PGTW 262230\r\nMSGID/", 1),
        )
        for body in invalid:
            with self.subTest(body=hashlib.sha256(body).hexdigest()):
                with self.assertRaisesRegex(FeedError, "header disagrees with issue time"):
                    parse_advisory(body, "abpw")
        duplicate = raw.replace(b"RMKS/", b"REISSUED/262200Z-270600ZOCT2026//\r\nRMKS/", 1)
        with self.assertRaisesRegex(FeedError, "lacks a dated issue interval"):
            parse_advisory(duplicate, "abpw")
        invalid_end = raw.replace(b"270600ZOCT2026", b"320600ZOCT2026", 1)
        with self.assertRaisesRegex(FeedError, "validity interval is invalid"):
            parse_advisory(invalid_end, "abpw")

        indian = (FIXTURES / "jtwc-abio-20261019.txt").read_bytes()
        indian = indian.replace(b"ABIO10 PGTW 190300", b"ABIO10 PGTW 190330", 1)
        changed = parse_advisory(indian, "abio")
        self.assertEqual(changed.issued_at - changed.issue_at, 30 * 60)
        self.assertTrue(changed.invests)
        self.assertTrue(all(storm.current.at == changed.issue_at for storm in changed.invests))

    def test_reissue_requires_matching_rss_issue_and_keeps_last_good_on_mismatch(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        marker, arc = self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)
        reissue = MappedFetcher()
        reissue.payloads[JTWC + "abpwweb.txt"] = reissue.payloads[JTWC + "abpwweb.txt"].replace(
            b"ABPW10 PGTW 190900", b"ABPW10 PGTW 190930", 1)
        original_rss = reissue.payloads[JTWC_RSS]
        self.assertIn(b"Issued at 19/0600Z", original_rss)
        reissue.payloads[JTWC_RSS] = original_rss.replace(
            b"Issued at 19/0600Z", b"Reissued at 19/0930Z", 1)
        accepted = run(self.fs, settings, fetcher=reissue, now=NOW + 600)
        self.assertEqual(accepted.outcome, "unchanged", accepted.message)
        self.assertEqual(accepted.successful_at, NOW + 600)
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), (marker, arc))
        for rss_status in (b"Reissued at 19/0931Z", b"Issued at 19/0930Z", b"Unknown"):
            with self.subTest(rss_status=rss_status):
                bad = MappedFetcher()
                bad.payloads[JTWC + "abpwweb.txt"] = reissue.payloads[JTWC + "abpwweb.txt"]
                bad.payloads[JTWC_RSS] = original_rss.replace(
                    b"Issued at 19/0600Z", rss_status, 1)
                failed = run(self.fs, settings, fetcher=bad, now=NOW + 1200)
                self.assertEqual(failed.outcome, "failed")
                self.assertIn("ABPW reissue disagrees with RSS", failed.message)
                self.assertEqual(failed.successful_at, NOW + 600)
                self.assertEqual((self.fs.read(settings.storm.marker),
                                  self.fs.read(settings.storm.arc)), (marker, arc))

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

    def test_authentic_abio_region_wrap_keeps_strict_interval_and_basin_checks(self):
        captured = FIXTURES / "live-20261021-indian-wrap"
        record = json.loads((captured / "manifest.json").read_text())["records"][0]
        raw = (captured / record["path"]).read_bytes()
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()),
                         (record["bytes"], record["sha256"]))
        self.assertIn(b"INDIAN \r\nOCEAN/211800Z-221800ZOCT2026//", raw)
        advisory = parse_advisory(raw, "abio")
        self.assertEqual((advisory.issue_at, advisory.valid_until_at), (
            datetime(2026, 10, 21, 18, tzinfo=timezone.utc).timestamp(),
            datetime(2026, 10, 22, 18, tzinfo=timezone.utc).timestamp()))
        self.assertEqual(advisory.areas[1].warned_codes, ("02S",))

        # Older reissues place the date on its own line after the subject.
        reissued = (FIXTURES / "live-20261020-promotion/jtwc-abio-advisory.txt").read_bytes()
        self.assertIn(b"INDIAN OCEAN \r\nREISSUED/", reissued)
        reissued = reissued.replace(b"INDIAN OCEAN ", b"INDIAN \r\nOCEAN ", 1)
        self.assertEqual(parse_advisory(reissued, "abio").issue_at,
                         datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc).timestamp())

        malformed = (
            (raw.replace(b"221800ZOCT2026", b"321800ZOCT2026", 1),
             "validity interval is invalid"),
            (raw.replace(b"RMKS/", b"ISSUED/211800Z-221800ZOCT2026//\r\nRMKS/", 1),
             "JTWC ABIO advisory lacks a dated issue interval"),
            (raw.replace(b"INDIAN \r\nOCEAN/", b"INDIAN \r\n\r\nOCEAN/", 1),
             "JTWC ABIO advisory lacks a dated issue interval"),
        )
        for body, message in malformed:
            with self.subTest(body=hashlib.sha256(body).hexdigest()):
                with self.assertRaisesRegex(FeedError, message):
                    parse_advisory(body, "abio")
        with self.assertRaisesRegex(FeedError, "subject disagrees with region"):
            parse_advisory(raw, "abpw")

    def test_authentic_slash_reissue_keeps_date_region_and_freshness_guards(self):
        captured = FIXTURES / "live-20261105-slash-reissue"
        record = json.loads((captured / "manifest.json").read_text())["records"][0]
        raw = (captured / record["path"]).read_bytes()
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()),
                         (record["bytes"], record["sha256"]))
        self.assertIn(b"INDIAN \r\nOCEAN/REISSUED/051800Z-061800ZNOV2026//", raw)
        issued = datetime(2026, 11, 5, 18, tzinfo=timezone.utc).timestamp()
        until = datetime(2026, 11, 6, 18, tzinfo=timezone.utc).timestamp()
        for separator in (b"/", b" ", b" \r\n"):
            with self.subTest(separator=separator):
                body = raw.replace(b"OCEAN/REISSUED/", b"OCEAN" + separator + b"REISSUED/")
                advisory = parse_advisory(body, "abio")
                self.assertEqual((advisory.issue_at, advisory.issued_at,
                                  advisory.valid_until_at, advisory.reissued),
                                 (issued, issued, until, True))
                self.assertEqual([storm.id for storm in advisory.invests], ["SH942027"])
                _fresh_advisory(advisory, until, "abio")
                with self.assertRaisesRegex(FeedError, "advisory is stale"):
                    _fresh_advisory(advisory, until + 1, "abio")
                with self.assertRaisesRegex(FeedError, "future-dated"):
                    _fresh_advisory(advisory, issued - 3601, "abio")
        malformed = (
            raw.replace(b"OCEAN/REISSUED/", b"OCEAN//REISSUED/"),
            raw.replace(b"051800Z-061800ZNOV2026//", b"051800Z-061800ZNOV2026/"),
            raw.replace(b"061800ZNOV2026", b"061800Z"),
            raw.replace(b"ABIO10 PGTW 051800", b"ABIO10 PGTW 071800"),
            raw.replace(b"RMKS/", b"ISSUED/051800Z-061800ZNOV2026//\r\nRMKS/", 1),
            raw.replace(b"RMKS/", b"SUBJ/BROKEN\r\nRMKS/", 1),
        )
        for body in malformed:
            with self.subTest(body=hashlib.sha256(body).hexdigest()):
                with self.assertRaises(FeedError):
                    parse_advisory(body, "abio")
        with self.assertRaisesRegex(FeedError, "subject disagrees with region"):
            parse_advisory(raw, "abpw")

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
        reissue = (empty_advisory("abpw")
                   .replace(b"ABPW10 PGTW 190900", b"ABPW10 PGTW 010030", 1)
                   .replace(b"ISSUED/190900Z-200600ZOCT2026//",
                            b"REISSUED/312300Z-010600ZNOV2026//", 1))
        parsed = parse_advisory(reissue, "abpw")
        self.assertEqual((parsed.issue_at, parsed.issued_at, parsed.valid_until_at), (
            datetime(2026, 10, 31, 23, tzinfo=timezone.utc).timestamp(),
            datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc).timestamp(),
            datetime(2026, 11, 1, 6, tzinfo=timezone.utc).timestamp()))
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
        self.assertIn("Storm Information Last Updated", self.fs.read(settings.labels).decode())

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

    def test_kmz_identity_mismatch_or_ambiguity_keeps_last_good_pair(self):
        settings = self.config("StormCheckIntervalSeconds=0\n")
        first = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW)
        self.assertEqual(first.outcome, "changed")
        marker, arc = self.fs.read(settings.storm.marker), self.fs.read(settings.storm.arc)
        label = self.fs.read(settings.labels)
        original = MappedFetcher().payloads[JTWC + "sh0127.kmz"]

        def altered_kmz(change):
            with ZipFile(BytesIO(original)) as archive:
                root = ET.fromstring(archive.read("doc.kml"))
            ns = "{http://www.opengis.net/kml/2.2}"
            document = root.find(ns + "Document")
            folder = document.find(ns + "Folder")
            change(document, folder, ns)
            output = BytesIO()
            with ZipFile(output, "w") as archive:
                archive.writestr("doc.kml", ET.tostring(root))
            return output.getvalue()

        def missing_description(document, folder, ns):
            folder.find(ns + "description").text = ""

        def other_name(document, folder, ns):
            folder.find(ns + "name").text = "OTHER"
            folder.find(ns + "description").text = (
                folder.find(ns + "description").text.replace("WATI", "OTHER"))

        def wrong_code(document, folder, ns):
            description = folder.find(ns + "description")
            description.text = description.text.replace("01P", "02P")

        def ambiguous_header(document, folder, ns):
            description = folder.find(ns + "description")
            description.text += " " + description.text

        def ambiguous_folder(document, folder, ns):
            document.append(ET.fromstring(ET.tostring(folder)))

        for source, payload in (
                ("sh0127.kmz", MappedFetcher().payloads[JTWC + "wp2926.kmz"]),
                ("wp2926.kmz", original),
                ("sh0127.kmz", altered_kmz(missing_description)),
                ("sh0127.kmz", altered_kmz(other_name)),
                ("sh0127.kmz", altered_kmz(wrong_code)),
                ("sh0127.kmz", altered_kmz(ambiguous_header)),
                ("sh0127.kmz", altered_kmz(ambiguous_folder))):
            with self.subTest(source=source, digest=hashlib.sha256(payload).hexdigest()):
                fetcher = MappedFetcher()
                fetcher.payloads[JTWC + source] = payload
                failed = run(self.fs, settings, fetcher=fetcher, now=NOW + 60)
                self.assertEqual(failed.outcome, "failed")
                self.assertEqual(failed.successful_at, NOW)
                self.assertEqual((self.fs.read(settings.storm.marker),
                                  self.fs.read(settings.storm.arc),
                                  self.fs.read(settings.labels)), (marker, arc, label))
        valid = run(self.fs, settings, fetcher=MappedFetcher(), now=NOW + 120)
        self.assertEqual(valid.outcome, "unchanged")
        self.assertEqual(valid.successful_at, NOW + 120)

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
        self.assertIn(f'-68 -13 "Storm Information Last Updated {legacy_time(NOW)}"',
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
        row = next(line for line in label.splitlines() if "Storm Information" in line)
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
        row = next(line for line in refreshed.splitlines() if "Storm Information" in line)
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
                   if "Storm Information" in line)
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
