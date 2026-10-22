"""Offline NORAD format fixture: installed Xplanet satellites/README ISS 3LE."""
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
from io import StringIO
import json
import hashlib
from pathlib import Path
from unittest.mock import patch

from totalmarker.errors import ConfigError, FeedError, StorageError
from totalmarker.features.norad import parse_group, parse_tle, run
from totalmarker.config import load
from totalmarker.http import Fetcher, Response
from totalmarker.state import json_bytes
from .support import Sandbox, ScriptedTransport


# The published example is copied here so the test remains portable.
SAMPLE = (
    b"ISS (ZARYA)             \n"
    b"1 25544U 98067A   01286.44085648  .00059265  00000-0  81723-3 0  5959\n"
    b"2 25544  51.6394 213.7002 0007838 194.2620 314.2054 15.56596996165535\n"
)
EPOCH = (datetime(2001, 1, 1, tzinfo=timezone.utc)
         + timedelta(days=286.44085648 - 1)).timestamp()
STATIONS = (Path(__file__).parent / "fixtures/norad/stations-selected.synthetic.json").read_bytes()
SAVED_STATIONS = (Path(__file__).parents[1] / "validation/norad-group-20261019/group-response.bin")


def sample_for(catalog_id, name):
    lines = SAMPLE.decode("ascii").splitlines()
    lines[0] = name
    for index in (1, 2):
        body = lines[index][:2] + f"{catalog_id:05}" + lines[index][7:68]
        lines[index] = body + str(sum(int(char) if char.isdigit() else char == "-"
                                      for char in body) % 10)
    return ("\n".join(lines) + "\n").encode("ascii")


class NoradTests(Sandbox):
    def options(self):
        return self.config("NoradEnabled=On\nNoradCatalogIds=25544\n")

    def native_options(self, extra, *, catalog_ids="25544"):
        (self.root / "config.toml").write_text(
            '[cloud]\nprovider = "custom"\nurl = "https://cloud.example.invalid/map.jpg"\n'
            f'[norad]\nenabled = true\ncatalog_ids = "{catalog_ids}"\n' + extra)
        return load(self.fs, "config.toml")

    def test_group_discovery_precedence_dedup_and_profile_styles(self):
        settings = self.native_options('''
[[norad.groups]]
source = "stations"
name_contains = "ISS"
color = "Blue"
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
color = "Violet"
trail = [-5, 0, 5]
align = "Below"
[[norad.profiles]]
catalog_id = 25544
caption = "Station"
color = "Gold"
transparent = [0, 0, 0]
altcirc = 0
''')
        transport = ScriptedTransport(Response(200, {}, STATIONS),
                                      Response(200, {}, SAMPLE),
                                      Response(200, {}, sample_for(12345, "SOYUZ MS-TEST")))
        first = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual((first.outcome, first.count), ("changed", 2))
        selector = self.fs.read(settings.norad.satellite)
        self.assertIn(b'25544 "Station" color=Gold', selector)
        self.assertIn(b'transparent={0,0,0} altcirc=0', selector)
        self.assertIn(b'12345 "SOYUZ MS-TEST" color=Violet trail={orbit,-5,0,5}', selector)
        self.assertIn(b'align=below', selector)
        self.assertEqual(selector.count(b"25544 "), 1)
        self.assertEqual(len(transport.calls), 3)
        self.assertIn("GROUP=STATIONS&FORMAT=JSON", transport.calls[0][0])
        again = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 100)
        self.assertEqual(again.outcome, "unchanged")
        self.assertEqual(len(transport.calls), 3)

    def test_incomplete_group_and_all_unsupported_ids_retain_last_good_pair(self):
        old = self.options()
        self.assertEqual(run(self.fs, old, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, SAMPLE))), now=EPOCH + 10).outcome, "changed")
        prior = self.fs.read(old.norad.satellite)
        settings = self.native_options('''
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
''', catalog_ids="")
        bad = json.dumps([{"OBJECT_NAME": "SOYUZ TEST"}]).encode()
        failed = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, bad))), now=EPOCH + 8000)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(self.fs.read(settings.norad.satellite), prior)
        self.assertEqual(self.read_state(settings)["products"]["norad"]["count"], 1)
        six_digit = json.dumps([
            {"OBJECT_NAME": "SOYUZ NEW", "NORAD_CAT_ID": 100001}]).encode()
        failed = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, six_digit))), now=EPOCH + 16000)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("100001", failed.message)
        self.assertIn("no representable TLE objects", failed.message)
        self.assertEqual(self.fs.read(settings.norad.satellite), prior)
        self.assertEqual(self.read_state(settings)["products"]["norad"]["count"], 1)
        self.assertEqual(failed.successful_at, EPOCH + 10)

    def test_group_skips_unsupported_id_with_persistent_partial_warning(self):
        settings = self.native_options('''
[[norad.groups]]
source = "stations"
name_contains = "ISS"
color = "Blue"
[[norad.profiles]]
catalog_id = 25544
caption = "ISS EXPLICIT"
color = "Gold"
''')
        group = json.dumps([
            {"OBJECT_NAME": "ISS (ZARYA)", "NORAD_CAT_ID": 25544},
            {"OBJECT_NAME": "ISS NEW", "NORAD_CAT_ID": 100057},
            {"OBJECT_NAME": "ISS (NAUKA)", "NORAD_CAT_ID": 49044},
        ]).encode()
        transport = ScriptedTransport(Response(200, {}, group),
                                      Response(200, {}, SAMPLE),
                                      Response(200, {}, sample_for(49044, "ISS (NAUKA)")))
        first = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual((first.outcome, first.count), ("changed", 2))
        self.assertIn("skipped unsupported group catalog IDs 100057", first.message)
        self.assertIn("coverage is partial", first.message)
        record = self.read_state(settings)["products"]["norad"]
        self.assertEqual(record["selected_ids"], [25544, 49044])
        self.assertEqual(record["skipped_unsupported_ids"], [100057])
        self.assertIn(b'25544 "ISS EXPLICIT" color=Gold',
                      self.fs.read(settings.norad.satellite))
        self.assertNotIn(b"100057", self.fs.read(settings.norad.satellite))
        cached = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 100)
        self.assertEqual((cached.outcome, cached.count), ("unchanged", 2))
        self.assertIn("coverage is partial", cached.message)
        self.assertEqual(len(transport.calls), 3)
        complete_group = json.dumps([
            {"OBJECT_NAME": "ISS (ZARYA)", "NORAD_CAT_ID": 25544},
            {"OBJECT_NAME": "ISS (NAUKA)", "NORAD_CAT_ID": 49044},
        ]).encode()
        complete_transport = ScriptedTransport(
            Response(200, {}, complete_group), Response(200, {}, SAMPLE),
            Response(200, {}, sample_for(49044, "ISS (NAUKA)")))
        complete = run(self.fs, settings, fetcher=Fetcher(complete_transport),
                       now=EPOCH + 8000)
        self.assertEqual((complete.outcome, complete.count), ("unchanged", 2))
        self.assertNotIn("coverage is partial", complete.message)
        self.assertEqual(self.read_state(settings)["products"]["norad"]
                         ["skipped_unsupported_ids"], [])

    def test_saved_live_group_response_skips_soyuz_without_publishing_empty_pair(self):
        if not SAVED_STATIONS.exists():
            self.skipTest("private saved CelesTrak group response is unavailable")
        settings = self.native_options('''
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
''', catalog_ids="")
        transport = ScriptedTransport(Response(200, {}, SAVED_STATIONS.read_bytes()))
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual(result.outcome, "failed")
        self.assertIn("100057", result.message)
        self.assertEqual(len(transport.calls), 1)
        self.assertIsNone(self.fs.read(settings.norad.satellite))
        self.assertIsNone(self.fs.read(settings.norad.satellite + ".tle"))
        self.assertIsNone(result.successful_at)

    def test_saved_live_group_response_preserves_explicit_iss_with_warning(self):
        if not SAVED_STATIONS.exists():
            self.skipTest("private saved CelesTrak group response is unavailable")
        settings = self.native_options('''
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
[[norad.profiles]]
catalog_id = 25544
caption = "ISS EXPLICIT"
color = "Gold"
''')
        transport = ScriptedTransport(Response(200, {}, SAVED_STATIONS.read_bytes()),
                                      Response(200, {}, SAMPLE))
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual((result.outcome, result.count), ("changed", 1))
        self.assertIn("100057", result.message)
        self.assertIn("coverage is partial", result.message)
        self.assertEqual(self.read_state(settings)["products"]["norad"]
                         ["skipped_unsupported_ids"], [100057])
        self.assertIn(b'25544 "ISS EXPLICIT" color=Gold',
                      self.fs.read(settings.norad.satellite))
        self.assertEqual(len(transport.calls), 2)

    def test_local_icon_required_and_cached_icon_checked(self):
        settings = self.native_options('''
[[norad.profiles]]
catalog_id = 25544
icon = "iss.png"
caption = ""
''')
        self.fs.write("images/iss.png", b"local fixture")
        transport = ScriptedTransport(Response(200, {}, SAMPLE),
                                      Response(200, {}, SAMPLE))
        self.assertEqual(run(self.fs, settings, fetcher=Fetcher(transport),
                             now=EPOCH + 10).outcome, "changed")
        self.assertIn(b'25544 ""', self.fs.read(settings.norad.satellite))
        self.assertIn(b'image=iss.png', self.fs.read(settings.norad.satellite))
        self.fs.unlink("images/iss.png")
        self.assertEqual(run(self.fs, settings, fetcher=Fetcher(transport),
                             now=EPOCH + 100).outcome, "failed")
        self.assertEqual(len(transport.calls), 1)
        corrected = self.native_options('''
[[norad.profiles]]
catalog_id = 25544
caption = ""
''')
        rebuilt = run(self.fs, corrected, fetcher=Fetcher(transport),
                      now=EPOCH + 8000)
        self.assertEqual(rebuilt.outcome, "changed")
        self.assertNotIn(b"image=iss.png", self.fs.read(corrected.norad.satellite))
        self.assertEqual(len(transport.calls), 2)

    def test_group_rejects_partial_collection(self):
        with self.assertRaisesRegex(FeedError, "incomplete"):
            parse_group(b'[{"OBJECT_NAME":"SOYUZ"}]')
        with self.assertRaisesRegex(FeedError, "JSON"):
            parse_group(b'[{"OBJECT_NAME":"SOYUZ","NORAD_CAT_ID":12345}')
        with self.assertRaisesRegex(FeedError, "duplicate"):
            parse_group(b'[{"OBJECT_NAME":"A","NORAD_CAT_ID":12345},'
                        b'{"OBJECT_NAME":"B","NORAD_CAT_ID":12345}]')

    def test_group_with_no_matching_members_fails_and_keeps_pair(self):
        original = self.options()
        run(self.fs, original, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, SAMPLE))), now=EPOCH + 10)
        old_pair = (self.fs.read(original.norad.satellite),
                    self.fs.read(original.norad.satellite + ".tle"))
        (self.root / "config.toml").write_text('''
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
[norad]
enabled = true
catalog_ids = ""
[[norad.groups]]
source = "stations"
name_contains = "NO SUCH OBJECT"
''')
        grouped = load(self.fs, "config.toml")
        transport = ScriptedTransport(Response(200, {}, STATIONS))
        failed = run(self.fs, grouped, fetcher=Fetcher(transport), now=EPOCH + 8000)
        self.assertEqual(failed.outcome, "failed")
        self.assertIn("no available TLE objects", failed.message)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual((self.fs.read(grouped.norad.satellite),
                          self.fs.read(grouped.norad.satellite + ".tle")), old_pair)

    def test_disabled_profile_and_group_are_not_selected(self):
        settings = self.native_options('''
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
enabled = false
[[norad.profiles]]
catalog_id = 25544
enabled = false
''')
        transport = ScriptedTransport()
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual((result.outcome, result.count), ("changed", 0))
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.fs.read(settings.norad.satellite), b"")
        self.assertEqual(self.fs.read(settings.norad.satellite + ".tle"), b"")

    def test_disabling_final_profile_clears_old_pair_without_provider(self):
        original = self.options()
        first = run(self.fs, original, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, SAMPLE))), now=EPOCH + 10)
        self.assertEqual(first.count, 1)
        disabled = self.native_options('''
[[norad.profiles]]
catalog_id = 25544
enabled = false
''')
        transport = ScriptedTransport()
        empty = run(self.fs, disabled, fetcher=Fetcher(transport), now=EPOCH + 100)
        self.assertEqual((empty.outcome, empty.count), ("changed", 0))
        self.assertEqual((self.fs.read(disabled.norad.satellite),
                          self.fs.read(disabled.norad.satellite + ".tle")), (b"", b""))
        self.assertEqual(self.read_state(disabled)["products"]["norad"]["selected_ids"], [])
        retained = run(self.fs, disabled, fetcher=Fetcher(transport), now=EPOCH + 8000)
        self.assertEqual((retained.outcome, retained.count), ("unchanged", 0))
        self.assertEqual(transport.calls, [])

    def test_disabling_final_group_discovered_profile_clears_pair(self):
        (self.root / "config.toml").write_text('''
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
[norad]
enabled = true
catalog_ids = ""
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
''')
        original = load(self.fs, "config.toml")
        initial = run(self.fs, original, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, STATIONS),
            Response(200, {}, sample_for(12345, "SOYUZ MS-TEST")))),
            now=EPOCH + 10)
        self.assertEqual((initial.outcome, initial.count), ("changed", 1))
        self.assertIn(b'12345 "SOYUZ MS-TEST"',
                      self.fs.read(original.norad.satellite))
        (self.root / "config.toml").write_text('''
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
[norad]
enabled = true
catalog_ids = ""
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
[[norad.profiles]]
catalog_id = 12345
enabled = false
''')
        disabled = load(self.fs, "config.toml")
        transport = ScriptedTransport(Response(200, {}, STATIONS))
        empty = run(self.fs, disabled, fetcher=Fetcher(transport), now=EPOCH + 8000)
        self.assertEqual((empty.outcome, empty.count), ("changed", 0))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual((self.fs.read(disabled.norad.satellite),
                          self.fs.read(disabled.norad.satellite + ".tle")), (b"", b""))
        self.assertEqual(self.read_state(disabled)["products"]["norad"]["selected_ids"], [])
        cached = run(self.fs, disabled, fetcher=Fetcher(transport), now=EPOCH + 8100)
        self.assertEqual((cached.outcome, cached.count), ("unchanged", 0))
        self.assertEqual(len(transport.calls), 1)

    def test_previous_state_without_attempt_timestamp_uses_fetch_time(self):
        original = self.options()
        transport = ScriptedTransport(Response(200, {}, SAMPLE))
        first = run(self.fs, original, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual(first.outcome, "changed")
        state = self.read_state(original)
        state["products"]["norad"].pop("attempted_at")
        self.fs.write(original.state, json_bytes(state))
        changed = self.config("NoradEnabled=On\nNoradCatalogIds=25544\n"
                              "NoradColor=Orange\n")
        deferred = run(self.fs, changed, fetcher=Fetcher(transport), now=EPOCH + 100)
        self.assertEqual(deferred.outcome, "unchanged")
        self.assertEqual(deferred.successful_at, first.successful_at)
        self.assertEqual(len(transport.calls), 1)

    def test_style_change_waits_for_provider_update(self):
        original = self.options()
        transport = ScriptedTransport(Response(200, {}, SAMPLE),
                                      Response(200, {}, SAMPLE))
        first = run(self.fs, original, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual(first.outcome, "changed")
        before = self.fs.read(original.norad.satellite)
        changed = self.config("NoradEnabled=On\nNoradCatalogIds=25544\n"
                              "NoradColor=Orange\n")
        deferred = run(self.fs, changed, fetcher=Fetcher(transport), now=EPOCH + 100)
        self.assertEqual(deferred.outcome, "unchanged")
        self.assertEqual(deferred.successful_at, first.successful_at)
        self.assertEqual(self.fs.read(changed.norad.satellite), before)
        self.assertEqual(len(transport.calls), 1)
        refreshed = run(self.fs, changed, fetcher=Fetcher(transport), now=EPOCH + 8000)
        self.assertEqual(refreshed.outcome, "changed")
        self.assertIn(b"color=Orange", self.fs.read(changed.norad.satellite))
        self.assertEqual(len(transport.calls), 2)

    def test_group_only_selection_and_response_limit(self):
        (self.root / "config.toml").write_text('''
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
[norad]
enabled = true
catalog_ids = ""
group_max_bytes = 2048
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
''')
        settings = load(self.fs, "config.toml")
        class LimitsTransport(ScriptedTransport):
            def __init__(self, *responses):
                super().__init__(*responses)
                self.limits = []
            def request(self, url, headers, timeout, max_bytes):
                self.limits.append(max_bytes)
                return super().request(url, headers, timeout, max_bytes)
        transport = LimitsTransport(Response(200, {}, STATIONS),
                                    Response(200, {}, sample_for(12345, "SOYUZ MS-TEST")))
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual((result.outcome, result.count), ("changed", 1))
        self.assertEqual(transport.limits, [2048, settings.norad.max_bytes])
        self.assertIn(b'12345 "SOYUZ MS-TEST"',
                      self.fs.read(settings.norad.satellite))
        before = self.fs.read(settings.norad.satellite)
        renamed = ScriptedTransport(Response(200, {}, STATIONS),
                                    Response(200, {}, sample_for(12345, "RENAMED")))
        failed = run(self.fs, settings, fetcher=Fetcher(renamed), now=EPOCH + 8000)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(self.fs.read(settings.norad.satellite), before)

    def test_corrupted_selected_id_state_is_rejected(self):
        settings = self.options()
        run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, SAMPLE))), now=EPOCH + 10)
        state = self.read_state(settings)
        state["products"]["norad"]["selected_ids"] = ["25544"]
        self.fs.write(settings.state, json_bytes(state))
        with self.assertRaisesRegex(StorageError, "selected IDs"):
            run(self.fs, settings, now=EPOCH + 100)
        state["products"]["norad"]["selected_ids"] = [25544]
        state["products"]["norad"]["skipped_unsupported_ids"] = ["100057"]
        self.fs.write(settings.state, json_bytes(state))
        with self.assertRaisesRegex(StorageError, "skipped IDs"):
            run(self.fs, settings, now=EPOCH + 100)

    def test_interrupted_fetch_retains_provider_attempt_time(self):
        settings = self.options()
        class InterruptedFetcher:
            def fetch(self, *args, **kwargs):
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            run(self.fs, settings, fetcher=InterruptedFetcher(), now=EPOCH + 10)
        self.assertEqual(self.read_state(settings)["products"]["norad"]["attempted_at"],
                         EPOCH + 10)
        transport = ScriptedTransport()
        deferred = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 100)
        self.assertEqual(deferred.outcome, "failed")
        self.assertEqual(transport.calls, [])

    def test_valid_tle_and_paired_cache(self):
        settings = self.options()
        transport = ScriptedTransport(Response(200, {"content-type": "text/plain"}, SAMPLE))
        first = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 10)
        self.assertEqual(first.outcome, "changed")
        self.assertEqual(first.count, 1)
        selector = self.fs.read(settings.norad.satellite)
        tle = self.fs.read(settings.norad.satellite + ".tle")
        self.assertIn(b'25544 "ISS (ZARYA)"', selector)
        self.assertEqual(tle, SAMPLE.replace(b"             \n", b"\n", 1))
        self.assertIn(b"NORAD Information Last Updated", self.fs.read(settings.labels))
        self.assertEqual(len(transport.calls), 1)
        self.assertIn("CATNR=25544&FORMAT=TLE", transport.calls[0][0])
        again = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 100)
        self.assertEqual(again.outcome, "unchanged")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(self.fs.read(settings.norad.satellite), selector)

    def test_bad_checksum_keeps_last_good_pair(self):
        settings = self.options()
        first = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, SAMPLE))), now=EPOCH + 10)
        self.assertEqual(first.outcome, "changed")
        before = self.fs.read(settings.norad.satellite + ".tle")
        corrupted = SAMPLE.replace(b"0  5959", b"0  5950")
        result = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, corrupted))), now=EPOCH + 8000)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(self.fs.read(settings.norad.satellite + ".tle"), before)
        self.assertEqual(self.read_state(settings)["products"]["norad"]["count"], 1)

    def test_missing_tle_waits_for_provider_interval_before_refetch(self):
        settings = self.options()
        transport = ScriptedTransport(Response(200, {}, SAMPLE),
                                      Response(200, {}, SAMPLE))
        client = Fetcher(transport)
        first = run(self.fs, settings, fetcher=client, now=EPOCH + 10)
        expected = self.fs.read(settings.norad.satellite + ".tle")
        self.fs.unlink(settings.norad.satellite + ".tle")
        deferred = run(self.fs, settings, fetcher=client, now=EPOCH + 70)
        self.assertEqual((first.outcome, deferred.outcome), ("changed", "failed"))
        self.assertEqual(len(transport.calls), 1)
        rebuilt = run(self.fs, settings, fetcher=client, now=EPOCH + 8000)
        self.assertEqual(rebuilt.outcome, "changed")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(self.fs.read(settings.norad.satellite + ".tle"), expected)

    def test_second_catalog_failure_retains_complete_previous_pair(self):
        settings = self.config("NoradEnabled=On\nNoradCatalogIds=25544,20580\n")
        lines = SAMPLE.decode("ascii").splitlines()
        for index in (1, 2):
            line = lines[index][:2] + "20580" + lines[index][7:68]
            checksum = sum(int(ch) if ch.isdigit() else ch == "-"
                           for ch in line) % 10
            lines[index] = line + str(checksum)
        second_tle = ("\n".join(lines) + "\n").encode("ascii")
        transport = ScriptedTransport(Response(200, {}, SAMPLE),
                                      Response(200, {}, second_tle),
                                      Response(200, {}, SAMPLE),
                                      Response(403, {}, b"Forbidden"))
        client = Fetcher(transport)
        initial = run(self.fs, settings, fetcher=client, now=EPOCH + 10)
        self.assertEqual((initial.outcome, initial.count), ("changed", 2))
        before_pair = (self.fs.read(settings.norad.satellite),
                       self.fs.read(settings.norad.satellite + ".tle"))
        failed = run(self.fs, settings, fetcher=client, now=EPOCH + 8000)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(len(transport.calls), 4)
        self.assertEqual(failed.successful_at, initial.successful_at)
        self.assertEqual((self.fs.read(settings.norad.satellite),
                          self.fs.read(settings.norad.satellite + ".tle")), before_pair)

    def test_disabled_and_unsupported_catalog(self):
        settings = self.config()
        self.assertEqual(run(self.fs, settings).outcome, "disabled")
        self.assertIsNone(self.fs.read(settings.state))
        with self.assertRaisesRegex(ConfigError, "one to five"):
            self.config("NoradEnabled=On\nNoradCatalogIds=123456\n")

    def test_numeric_orbital_fields_reject_checksum_correct_garbage(self):
        lines = SAMPLE.decode("ascii").splitlines()
        def mutate(field, value):
            second = lines[2]
            start, end = field
            second = second[:start] + value + second[end:68]
            check = sum(int(ch) if ch.isdigit() else ch == "-"
                        for ch in second) % 10
            return ("\n".join((lines[0], lines[1], second + str(check))) + "\n").encode()
        for field, value in (((8, 16), "ABCDEFGH"),
                             ((8, 16), "999.9999"),
                             ((52, 63), " 0.00000000")):
            with self.subTest(value=value), self.assertRaisesRegex(FeedError, "orbital"):
                parse_tle(mutate(field, value), 25544, EPOCH + 10, 14 * 86400)

    def test_cached_tle_expiry_forces_fetch_without_freshness_advance(self):
        settings = self.options()
        transport = ScriptedTransport(Response(200, {}, SAMPLE),
                                      Response(403, {"content-type": "text/plain"}, b"Forbidden"))
        client = Fetcher(transport)
        first_now = EPOCH + settings.norad.max_age - 60
        first = run(self.fs, settings, fetcher=client, now=first_now)
        self.assertEqual(first.outcome, "changed")
        before = self.fs.read(settings.norad.satellite + ".tle")
        second = run(self.fs, settings, fetcher=client, now=first_now + 120)
        self.assertEqual(second.outcome, "failed")
        self.assertEqual(len(transport.calls), 1)
        second = run(self.fs, settings, fetcher=client, now=first_now + 8000)
        self.assertEqual(second.outcome, "failed")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(second.successful_at, first.successful_at)
        self.assertEqual(self.fs.read(settings.norad.satellite + ".tle"), before)

    def test_prior_version_invalid_tle_cache_forces_fetch(self):
        settings = self.options()
        first = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(
            Response(200, {}, SAMPLE))), now=EPOCH + 10)
        self.assertEqual(first.outcome, "changed")
        selector = self.fs.read(settings.norad.satellite)
        lines = self.fs.read(settings.norad.satellite + ".tle").decode().splitlines()
        altered = lines[2][:8] + "ABCDEFGH" + lines[2][16:68]
        checksum = sum(int(ch) if ch.isdigit() else ch == "-"
                       for ch in altered) % 10
        lines[2] = altered + str(checksum)
        invalid_tle = ("\n".join(lines) + "\n").encode()
        # Model a checksum-correct pair and matching state from the previous
        # release, whose parser accepted this nonnumeric inclination.
        self.fs.write(settings.norad.satellite + ".tle", invalid_tle)
        state = self.read_state(settings)
        record = state["products"]["norad"]
        record["tle_sha256"] = hashlib.sha256(invalid_tle).hexdigest()
        record["body_sha256"] = hashlib.sha256(
            selector + b"\0" + invalid_tle).hexdigest()
        self.fs.write(settings.state, json_bytes(state))
        before_success = record["successful_at"]
        transport = ScriptedTransport(Response(
            403, {"content-type": "text/plain"}, b"Forbidden"))
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=EPOCH + 8000)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(result.successful_at, before_success)
        self.assertEqual(self.fs.read(settings.norad.satellite + ".tle"), invalid_tle)

    def test_not_modified_without_validators_never_rejuvenates_stale_tle(self):
        settings = self.options()
        transport = ScriptedTransport(Response(200, {}, SAMPLE),
                                      Response(304, {}, b""))
        client = Fetcher(transport)
        first_now = EPOCH + settings.norad.max_age - 60
        first = run(self.fs, settings, fetcher=client, now=first_now)
        second = run(self.fs, settings, fetcher=client, now=first_now + 120)
        self.assertEqual(second.outcome, "failed")
        self.assertEqual(len(transport.calls), 1)
        second = run(self.fs, settings, fetcher=client, now=first_now + 8000)
        self.assertEqual(second.outcome, "failed")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(second.successful_at, first.successful_at)

    def test_enabled_cli_success_then_provider_failure(self):
        from totalmarker.cli import main
        settings = self.options()
        transport = ScriptedTransport(Response(200, {}, SAMPLE),
                                      Response(403, {"content-type": "text/plain"}, b"Forbidden"))
        with patch("totalmarker.features.norad.Fetcher", return_value=Fetcher(transport)):
            with patch("totalmarker.features.norad.time.time",
                       side_effect=[EPOCH + 10, EPOCH + 8000]):
                outputs = []
                for _ in range(2):
                    stream = StringIO()
                    with redirect_stdout(stream):
                        code = main(["--root", str(self.root), "--config", "config.ini", "norad"])
                    outputs.append((code, json.loads(stream.getvalue())))
        self.assertEqual([code for code, _ in outputs], [0, 1])
        self.assertEqual([body["outcome"] for _, body in outputs], ["changed", "failed"])
        self.assertEqual(outputs[1][1]["successful_at"],
                         outputs[0][1]["successful_at"])

    def test_parser_rejects_wrong_id_and_stale_epoch(self):
        with self.assertRaises(FeedError):
            parse_tle(SAMPLE, 20580, EPOCH + 10, 14 * 86400)
        with self.assertRaisesRegex(FeedError, "freshness"):
            parse_tle(SAMPLE, 25544, EPOCH + 15 * 86400, 14 * 86400)
