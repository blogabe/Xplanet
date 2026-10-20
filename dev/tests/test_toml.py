import contextlib
from dataclasses import replace
import io
import json
import re
import tomllib
from unittest.mock import patch

from totalmarker.cli import main
from totalmarker.config import AuthSpec, TOML_KEYS, load
from totalmarker.errors import ConfigError, DownloadError
from totalmarker.http import HTTPTransport
from .support import PROJECT, Sandbox


class TomlConfigurationTests(Sandbox):
    def toml(self, text, name="config.toml"):
        (self.root / name).write_text(text)
        return load(self.fs, name)

    def test_structured_toml_and_ini_normalize_identically(self):
        toml = self.toml("""
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
resolution = 4096
auth_mode = "basic"
local_image_name = "map.jpg"
check_interval_seconds = 7200
timeout_seconds = 20
max_bytes = 2097152
[cloud.custom]
username = "DUMMY_CUSTOM_USER"
password = "DUMMY_CUSTOM_PASSWORD"
[paths]
image = "images/current.jpg"
labels = "markers/labels"
state = ".state/totalmarker/data.json"
journal = ".state/totalmarker/intent.json"
lock = ".state/totalmarker/job.lock"
log = ""
[labels]
enabled = false
warning_cloud_seconds = 12345
[labels.colors]
ok = "ForestGreen"
warning = "Gold"
error = "Crimson"
[legacy]
QuakeMinimumSize = "6"
""")
        ini = self.config(
            "CloudResolution=4096\nCloudAuthMode=basic\n"
            "CloudLocalImageName=map.jpg\nCloudCheckIntervalSeconds=7200\n"
            "CloudTimeoutSeconds=20\nCloudMaxBytes=2097152\n"
            "CustomUsername=DUMMY_CUSTOM_USER\nCustomPassword=DUMMY_CUSTOM_PASSWORD\n"
            "CloudOutput=images/current.jpg\nLabelOutput=markers/labels\n"
            "StateFile=.state/totalmarker/data.json\nJournalFile=.state/totalmarker/intent.json\n"
            "LockFile=.state/totalmarker/job.lock\nLogFile=\nLabelOnOff=Off\n"
            "LabelWarningCloud=12345\nLabelColorOk=ForestGreen\n"
            "LabelColorWarn=Gold\nLabelColorError=Crimson\nQuakeMinimumSize=6\n")
        self.assertEqual(replace(toml, unrelated={}, deferred_settings={}),
                         replace(ini, unrelated={}, deferred_settings={}))
        self.assertEqual(toml.deferred_settings, {})
        self.assertEqual(ini.deferred_settings, {})
        self.assertNotIn("DUMMY", repr(toml))

    def test_blank_xeric_credentials_validate_but_cannot_fetch(self):
        settings = self.toml("""
[cloud]
provider = "xeric"
resolution = 2048
[cloud.xeric]
username = ""
password = ""
""")
        self.assertEqual(settings.provider, "xeric")
        self.assertEqual(settings.resolution, 2048)
        with self.assertRaisesRegex(DownloadError, "authentication is missing"):
            settings.auth.resolve({})

    def test_custom_never_uses_xeric_credentials(self):
        settings = self.toml("""
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
[cloud.xeric]
username = "DUMMY_XERIC_USER"
password = "DUMMY_XERIC_PASSWORD"
""")
        self.assertEqual(settings.auth.mode, "none")
        self.assertIsNone(settings.auth.resolve({}))

    def test_optional_environment_references(self):
        settings = self.toml("""
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
[cloud.custom]
username_env = "DUMMY_USER_ENV"
password_env = "DUMMY_PASS_ENV"
""")
        self.assertEqual(settings.auth.resolve({"DUMMY_USER_ENV": "DUMMY_USER",
                                                "DUMMY_PASS_ENV": "DUMMY_PASSWORD"}),
                         ("DUMMY_USER", "DUMMY_PASSWORD"))

    def test_flat_and_legacy_aliases_remain_compatible(self):
        settings = self.toml("""
CloudProvider = "custom"
CloudURL = "https://cloud.example.invalid/map.jpg"
[legacy]
LabelOnOff = "Off"
CloudCheckIntervalSeconds = 1200
QuakeMinimumSize = 6
""", name="config.TOML")
        self.assertFalse(settings.labels_enabled)
        self.assertEqual(settings.interval, 1200)
        self.assertEqual(settings.unrelated["quakeminimumsize"], "6")

    def test_deferred_future_structures_are_retained_without_rewrite(self):
        raw = b"""
[cloud]
provider = "custom"
url = "https://cloud.example.invalid/map.jpg"
[legacy]
NORADImageFile = ""
QuakeMinimumSize = 6
[storms]
providers = ["future-a", "future-b"]
enabled = true
[storms.forecast]
hours = 72
"""
        (self.root / "config.toml").write_bytes(raw)
        settings = load(self.fs, "config.toml")
        self.assertEqual(settings.deferred_settings, {
            "legacy.NORADImageFile": "",
            "storms.providers": ["future-a", "future-b"],
            "storms.enabled": True, "storms.forecast.hours": 72})
        self.assertEqual((self.root / "config.toml").read_bytes(), raw)

    def test_invalid_toml_and_wrong_types_are_sanitized(self):
        for raw in [b'[cloud]\npassword = "DUMMY_UNTERMINATED',
                    b'\xffDUMMY_INVALID_UTF8', b'CloudResolution = [2048, 4096]',
                    b'CloudResolution = 2020-06-23',
                    b'[cloud]\nprovider = ["DUMMY_BAD_TYPE"]']:
            with self.subTest(raw=raw):
                (self.root / "config.toml").write_bytes(raw)
                with self.assertRaises(ConfigError) as error:
                    load(self.fs, "config.toml")
                self.assertNotIn("DUMMY", str(error.exception))

    def test_duplicate_aliases_are_rejected(self):
        for text in ['CloudProvider = "custom"\n[cloud]\nprovider = "xeric"\n',
                     '[cloud]\nresolution = 2048\n[legacy]\nCloudResolution = 4096\n']:
            with self.assertRaisesRegex(ConfigError, "more than one"):
                self.toml(text)

    def test_safe_toml_examples_load_without_network_or_rewrite(self):
        examples = sorted((PROJECT / "dev" / "examples").glob("*.example.toml"))
        self.assertTrue({"custom.example.toml", "xeric.example.toml"} <=
                        {path.name for path in examples})
        for path in examples:
            with self.subTest(example=path.name):
                raw = path.read_bytes()
                (self.root / "example.toml").write_bytes(raw)
                settings = load(self.fs, "example.toml")
                self.assertEqual((self.root / "example.toml").read_bytes(), raw)
                if settings.provider == "custom":
                    self.assertTrue(settings.url.startswith("https://cloud.example.invalid/"))
                    self.assertIsNone(settings.auth.resolve({}))
                else:
                    with self.assertRaises(DownloadError):
                        settings.auth.resolve({})

    def test_segmented_project_example_applies_quake_volcano_and_storm(self):
        raw = (PROJECT / "config/totalmarker.example.toml").read_bytes()
        document = tomllib.loads(raw.decode("utf-8"))
        self.assertEqual(list(document), ["paths", "labels", "cloud", "quake",
                                          "volcano", "storm", "norad", "eclipse"])
        self.assertIn("track_real_color", document["storm"])
        self.assertNotIn("StormColorTrackReal", document["storm"])
        self.assertNotIn("legacy", document)
        self.assertFalse(document["norad"]["enabled"])
        self.assertFalse(document["eclipse"]["enabled"])
        self.assertNotIn("santa", document)
        (self.root / "example.toml").write_bytes(raw)
        settings = load(self.fs, "example.toml")
        self.assertFalse(settings.santa.enabled)
        self.assertEqual(settings.santa.freshness_seconds, 0)
        self.assertEqual(settings.quake.minimum, 6)
        self.assertEqual((settings.quake.pixel_min, settings.quake.pixel_max),
                         (None, None))
        self.assertEqual(settings.volcano.circle_sizes, (4, 8, 12))
        self.assertEqual(settings.quake.warning, 10800)
        self.assertEqual(settings.volcano.warning, 259200)
        self.assertEqual(settings.storm.track_real_color, "Blue")
        self.assertEqual(settings.storm.warning, 10800)
        self.assertEqual(settings.deferred_settings, {})
        self.assertNotIn("storm.StormColorTrackReal", settings.deferred_settings)
        self.assertEqual((self.root / "example.toml").read_bytes(), raw)

    def test_project_example_documents_first_class_toml_settings(self):
        text = (PROJECT / "config/totalmarker.example.toml").read_text()
        section, documented = "", set()
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("#"):
                line = line[1:].strip()
            if line.startswith("[") and line.endswith("]"):
                section = line.strip("[]")
            elif match := re.match(r"([a-z][a-z0-9_]*)\s*=", line):
                documented.add(f"{section}.{match[1]}")
        alternatives = {"cloud.url", "cloud.auth_mode", "cloud.local_image_name"}
        first_class = {key for key in TOML_KEYS if not (
            key.startswith("storm.") and key.rsplit(".", 1)[-1][:1].isupper()
        )} - alternatives
        self.assertFalse(first_class - documented)

        def active_keys(table, prefix=""):
            keys = set()
            for name, value in table.items():
                dotted = prefix + name
                keys |= active_keys(value, dotted + ".") if isinstance(value, dict) else {dotted}
            return keys

        active = active_keys(tomllib.loads(text))
        self.assertFalse(active - (set(TOML_KEYS) | {"norad.groups", "norad.profiles"}))

    def test_native_storm_and_warning_keys_preserve_legacy_effective_settings(self):
        common = '[cloud]\nprovider = "custom"\nurl = "https://cloud.example.invalid/map.jpg"\n'
        old = self.toml(common + '''
[storm]
"StormColorTrackReal" = "Violet"
"StormNameOnOff" = "Off"
"StormTrackOnOff" = "Off"
"LabelWarningStorm" = "7200"
[legacy]
"LabelWarningNorad" = "90000"
"QuakeFade" = "Off"
''', name="old.toml")
        modern = self.toml(common + '''
[labels]
warning_storm_seconds = 7200
warning_norad_seconds = 90000
[storm]
track_real_color = "Violet"
name_enabled = false
track_enabled = false
[norad]
enabled = false
catalog_ids = ""
[eclipse]
enabled = false
path_url = ""
[legacy]
"QuakeFade" = "Off"
''', name="modern.toml")
        self.assertEqual(replace(old, unrelated={}, deferred_settings={}),
                         replace(modern, unrelated={}, deferred_settings={}))
        self.assertEqual(old.deferred_settings, modern.deferred_settings)

    def test_norad_collections_and_eclipse_notice_are_typed(self):
        common = ('[cloud]\nprovider = "custom"\n'
                  'url = "https://cloud.example.invalid/map.jpg"\n'
                  '[norad]\nenabled = false\ncatalog_ids = "25544"\n'
                  'group_max_bytes = 131072\n')
        settings = self.toml(common + '''
[[norad.groups]]
source = "stations"
name_contains = "SOYUZ"
enabled = false
color = "Blue"
[[norad.profiles]]
catalog_id = 25544
enabled = true
caption = "Station"
icon = "iss.png"
trail = [-10, 0, 5]
transparent = [0, 0, 0]
altcirc = 0
align = "Above"
[eclipse]
notice_enabled = false
''')
        self.assertFalse(settings.eclipse.notice_enabled)
        self.assertEqual(settings.norad.group_max_bytes, 131072)
        self.assertEqual(settings.norad.groups[0].name_contains, "SOYUZ")
        self.assertFalse(settings.norad.groups[0].enabled)
        self.assertEqual(settings.norad.profiles[0].style.trail, (-10, 0, 5))
        self.assertEqual(settings.deferred_settings, {})
        for bad in ('icon = "../unsafe.png"', 'caption = "bad\\\" injection"',
                    'trail = [-10, 0, 0]', 'transparent = [0, 0, 256]',
                    'color = "Blue newline"', 'altcirc = 91',
                    'altcirc = -1', 'unknown = true'):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                self.toml(common + '[[norad.profiles]]\ncatalog_id = 25544\n' + bad)

    def test_native_quake_blank_pixel_bounds_accept_only_blanks_or_numbers(self):
        settings = self.toml('[cloud]\nprovider = "custom"\n'
                             'url = "https://cloud.example.invalid/map.jpg"\n'
                             '[quake]\npixel_min = ""\npixel_max = 20\n')
        self.assertEqual((settings.quake.pixel_min, settings.quake.pixel_max),
                         (None, 20))
        with self.assertRaises(ConfigError):
            self.toml('[cloud]\nprovider = "custom"\n'
                      'url = "https://cloud.example.invalid/map.jpg"\n'
                      '[quake]\npixel_min = "unspecified"\n')

    def test_cli_labels_reports_deferred_settings_and_remains_offline(self):
        self.toml("""
[cloud]
provider = "xeric"
[cloud.xeric]
username = ""
password = ""
[legacy]
QuakeMinimumSize = 6
[storms]
providers = ["future"]
""")
        raw = (self.root / "config.toml").read_bytes()
        stream = io.StringIO()
        with (patch.object(HTTPTransport, "request", side_effect=AssertionError("Network")),
              patch.object(AuthSpec, "resolve", side_effect=AssertionError("Auth")),
              contextlib.redirect_stdout(stream)):
            status = main(["--root", str(self.root), "--config", "config.toml", "labels"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stream.getvalue())["deferred_settings_count"], 1)
        self.assertEqual((self.root / "config.toml").read_bytes(), raw)

    def test_outputs_cannot_overwrite_loaded_config_or_its_symlink_target(self):
        for name, raw in [
            ("config.toml", b'[paths]\nimage = "config.toml"\n'),
            ("config.ini", b"CloudOutput=config.ini\n")]:
            with self.subTest(name=name):
                (self.root / name).write_bytes(raw)
                with self.assertRaisesRegex(ConfigError, "configuration file"):
                    load(self.fs, name)
                self.assertEqual((self.root / name).read_bytes(), raw)
        (self.root / "config.toml").write_text('[paths]\nimage = "alias.toml"\n')
        (self.root / "alias.toml").symlink_to("config.toml")
        with self.assertRaisesRegex(ConfigError, "configuration file"):
            load(self.fs, "config.toml")
