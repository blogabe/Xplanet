"""Normalize INI and TOML without rewriting files; keep provider secrets separate."""
import configparser
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from .errors import ConfigError, DownloadError


def https_url(value, *, allow_query=False):
    try:
        if any(ord(c) <= 32 for c in value):
            raise ValueError
        url = urlsplit(value)
        if (url.scheme.lower() != "https" or not url.hostname or url.username is not None
                or url.password is not None or (url.query and not allow_query) or url.fragment):
            raise ValueError
        _ = url.port
        return urlunsplit(("https", url.netloc, url.path or "/", url.query if allow_query else "", ""))
    except (ValueError, TypeError):
        raise ConfigError("Source URLs must be HTTPS without credentials, query or fragment") from None

XERIC_URL_TEMPLATE = (
    "https://secure.xericdesign.com/xplanet/clouds/"
    "{resolution}/clouds-{resolution}.jpg"
)


def expand_template(value, *, resolution, local_image_name=None):
    """Replace only explicit tokens; no expressions, formatting or escaping."""
    if not isinstance(value, str):
        raise ConfigError("A filename, URL or output template must be a string")
    fields = {"resolution": str(resolution)}
    if local_image_name is not None:
        fields["local_image_name"] = local_image_name
    tokens = re.findall(r"\{([^{}]*)\}", value)
    if any(token not in fields for token in tokens):
        raise ConfigError("Unknown or unsupported configuration template placeholder")
    result = value
    for token in tokens:
        if token == "resolution" and resolution <= 0:
            raise ConfigError("Resolution templates require a positive CloudResolution")
        result = result.replace("{" + token + "}", fields[token])
    if "{" in result or "}" in result:
        raise ConfigError("Invalid configuration template braces")
    return result



@dataclass(frozen=True, repr=False)
class AuthSpec:
    mode: str = "none"
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    username_env: str = ""
    password_env: str = ""

    def __repr__(self):
        return "AuthSpec(mode=" + repr(self.mode) + ", credentials=<redacted>)"

    def resolve(self, environment=None):
        if self.mode == "none":
            return None
        environment = os.environ if environment is None else environment
        user = environment.get(self.username_env, "") if self.username_env else self.username
        password = (environment.get(self.password_env, "") if self.password_env
                    else self.password)
        if not user or not password:
            raise DownloadError("Cloud authentication is missing")
        if ":" in user or any(c in user + password for c in "\r\n"):
            raise DownloadError("Cloud authentication is invalid")
        return user, password


@dataclass(frozen=True)
class Settings:
    provider: str
    url: str = field(repr=False)
    resolution: int
    auth: AuthSpec
    image: str
    labels: str
    state: str
    journal: str
    lock: str
    log: str | None
    interval: int
    timeout: int
    max_bytes: int
    warning: int
    colors: tuple
    labels_enabled: bool
    volcano: "VolcanoOptions" = field(default_factory=lambda: VolcanoOptions())
    quake: "QuakeOptions" = field(default_factory=lambda: QuakeOptions())
    storm: "StormOptions" = field(default_factory=lambda: StormOptions())
    norad: "NoradOptions" = field(default_factory=lambda: NoradOptions())
    eclipse: "EclipseOptions" = field(default_factory=lambda: EclipseOptions())
    santa: "SantaOptions" = field(default_factory=lambda: SantaOptions())
    unrelated: dict = field(default_factory=dict, repr=False)
    deferred_settings: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class VolcanoOptions:
    provider: str = "cap"
    url: str = "https://volcano.si.edu/news/WeeklyVolcanoCAP.xml"
    marker: str = "markers/volcano"
    journal: str = ".state/totalmarker/volcano-pending.json"
    interval: int = 24 * 3600
    timeout: int = 30
    max_bytes: int = 8 * 1024 * 1024
    warning: int = 3 * 24 * 3600
    circle_sizes: tuple = (4, 8, 12)
    circle_colors: tuple = ("Yellow", "Red", "Brown")
    name_enabled: bool = True
    name_color: str = "Brown"
    name_align: str = "Below"
    image: str = ""
    image_transparent: str = ""
    detail: str = ""
    detail_align: str = "Below"
    detail_color: str = "Brown"


@dataclass(frozen=True)
class QuakeOptions:
    duration: str = "Week"
    size: str = "All"
    minimum: float = 6.0
    marker: str = "markers/quake"
    journal: str = ".state/totalmarker/quake-pending.json"
    interval: int = 20 * 60
    timeout: int = 30
    max_bytes: int = 32 * 1024 * 1024
    warning: int = 3 * 3600
    circle_color: str = "Multi"
    pixel_max: float | None = None
    pixel_min: float | None = None
    pixel_factor: float = 1.0
    image: str = ""
    image_transparent: str = ""
    detail: str = "<mag>"
    detail_color: str = "Multi"
    detail_color_min: str = "Green"
    detail_color_int: str = "Yellow"
    detail_color_max: str = "Red"
    detail_align: str = "Above"

    @property
    def url(self):
        return ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
                f"{self.size.lower()}_{self.duration.lower()}.geojson")


@dataclass(frozen=True)
class StormOptions:
    marker: str = "markers/storm"
    arc: str = "arcs/storm"
    journal: str = ".state/totalmarker/storm-pending.json"
    interval: int = 30 * 60
    timeout: int = 30
    max_bytes: int = 16 * 1024 * 1024
    warning: int = 3 * 3600
    track_real_color: str = "Blue"
    track_forecast_color: str = "SkyBlue"
    name_enabled: bool = True
    name_color: str = "SkyBlue"
    name_align: str = "Above"
    detail: str = "<type>"
    detail_color: str = "SkyBlue"
    detail_align: str = "Below"
    image: str = ""
    image_transparent: str = ""
    track_enabled: bool = True


@dataclass(frozen=True)
class NoradStyle:
    enabled: bool | None = None
    icon: str | None = None
    caption: str | None = None
    color: str | None = None
    trail: tuple[int, int, int] | None = None
    transparent: tuple[int, int, int] | None = None
    altcirc: int | None = None
    align: str | None = None


@dataclass(frozen=True)
class NoradGroup:
    source: str
    name_contains: str
    enabled: bool = True
    style: NoradStyle = field(default_factory=NoradStyle)


@dataclass(frozen=True)
class NoradProfile:
    catalog_id: int
    style: NoradStyle


@dataclass(frozen=True)
class NoradOptions:
    enabled: bool = False
    catalog_ids: tuple[int, ...] = ()
    satellite: str = "satellites/totalmarker"
    journal: str = ".state/totalmarker/norad-pending.json"
    interval: int = 2 * 3600
    timeout: int = 30
    max_bytes: int = 64 * 1024
    max_age: int = 14 * 24 * 3600
    warning: int = 24 * 3600
    color: str = "Yellow"
    group_max_bytes: int = 1024 * 1024
    groups: tuple[NoradGroup, ...] = ()
    profiles: tuple[NoradProfile, ...] = ()


@dataclass(frozen=True)
class EclipseOptions:
    enabled: bool = False
    path_url: str = ""
    marker: str = "markers/eclipse"
    arc: str = "arcs/eclipse"
    journal: str = ".state/totalmarker/eclipse-pending.json"
    interval: int = 24 * 3600
    timeout: int = 30
    max_bytes: int = 2 * 1024 * 1024
    notify_hours: int = 48
    notice_enabled: bool = True
    edge_color: str = "Grey"
    center_color: str = "Black"
    notice_color: str = "White"


@dataclass(frozen=True)
class SantaOptions:
    enabled: bool = False
    marker: str = "markers/santa"
    journal: str = ".state/totalmarker/santa-pending.json"
    freshness_seconds: int = 0  # A real provider's documented limit is required.


# TOML names normalize to the same flat keys used by the existing INI loader.
TOML_KEYS = {
    "cloud.provider": "CloudProvider", "cloud.url": "CloudURL",
    "cloud.resolution": "CloudResolution", "cloud.auth_mode": "CloudAuthMode",
    "cloud.local_image_name": "CloudLocalImageName",
    "cloud.local_image_name_template": "CloudLocalImageName",
    "cloud.xeric.url_template": "XericURLTemplate",
    "cloud.xeric.auth_mode": "XericAuthMode",
    "cloud.custom.url_template": "CustomURLTemplate",
    "cloud.custom.auth_mode": "CustomAuthMode",
    "cloud.check_interval_seconds": "CloudCheckIntervalSeconds",
    "cloud.timeout_seconds": "CloudTimeoutSeconds", "cloud.max_bytes": "CloudMaxBytes",
    "cloud.xeric.username": "XericUsername", "cloud.xeric.password": "XericPassword",
    "cloud.xeric.username_env": "XericUsernameEnv",
    "cloud.xeric.password_env": "XericPasswordEnv",
    "cloud.custom.username": "CustomUsername", "cloud.custom.password": "CustomPassword",
    "cloud.custom.username_env": "CustomUsernameEnv",
    "cloud.custom.password_env": "CustomPasswordEnv",
    "paths.image": "CloudOutput", "paths.labels": "LabelOutput",
    "paths.state": "StateFile", "paths.journal": "JournalFile",
    "paths.lock": "LockFile", "paths.log": "LogFile",
    "labels.enabled": "LabelOnOff", "labels.warning_cloud_seconds": "LabelWarningCloud",
    "labels.colors.ok": "LabelColorOk", "labels.colors.warning": "LabelColorWarn",
    "labels.colors.error": "LabelColorError",
    "volcano.url": "VolcanoURL", "volcano.output": "VolcanoOutput",
    "volcano.provider": "VolcanoProvider",
    "volcano.journal": "VolcanoJournalFile",
    "volcano.check_interval_seconds": "VolcanoCheckIntervalSeconds",
    "volcano.timeout_seconds": "VolcanoTimeoutSeconds",
    "volcano.max_bytes": "VolcanoMaxBytes",
    "volcano.circle_size_inner": "VolcanoCircleSizeInner",
    "volcano.circle_size_middle": "VolcanoCircleSizeMiddle",
    "volcano.circle_size_outer": "VolcanoCircleSizeOuter",
    "volcano.circle_color_inner": "VolcanoCircleColorInner",
    "volcano.circle_color_middle": "VolcanoCircleColorMiddle",
    "volcano.circle_color_outer": "VolcanoCircleColorOuter",
    "volcano.name_enabled": "VolcanoNameOnOff",
    "volcano.name_color": "VolcanoNameColor",
    "volcano.name_align": "VolcanoNameAlign",
    "volcano.image": "VolcanoImageList",
    "volcano.image_transparent": "VolcanoImageTransparent",
    "volcano.detail": "VolcanoDetailList",
    "volcano.detail_align": "VolcanoDetailAlign",
    "volcano.detail_color": "VolcanoDetailColor",
    "labels.warning_volcano_seconds": "LabelWarningVolcano",
    "quake.reporting_duration": "QuakeReportingDuration",
    "quake.reporting_size": "QuakeReportingSize",
    "quake.minimum_magnitude": "QuakeMinimumSize",
    "quake.output": "QuakeOutput", "quake.journal": "QuakeJournalFile",
    "quake.check_interval_seconds": "QuakeCheckIntervalSeconds",
    "quake.timeout_seconds": "QuakeTimeoutSeconds",
    "quake.max_bytes": "QuakeMaxBytes",
    "quake.circle_color": "QuakeCircleColor",
    "quake.pixel_max": "QuakePixelMax", "quake.pixel_min": "QuakePixelMin",
    "quake.pixel_factor": "QuakePixelFactor",
    "quake.image": "QuakeImageList",
    "quake.image_transparent": "QuakeImageTransparent",
    "quake.detail": "QuakeDetailList", "quake.detail_color": "QuakeDetailColor",
    "quake.detail_color_min": "QuakeDetailColorMin",
    "quake.detail_color_int": "QuakeDetailColorInt",
    "quake.detail_color_max": "QuakeDetailColorMax",
    "quake.detail_align": "QuakeDetailAlign",
    "labels.warning_quake_seconds": "LabelWarningQuake",
    "storm.output": "StormOutput", "storm.arc_output": "StormArcOutput",
    "storm.journal": "StormJournalFile",
    "storm.check_interval_seconds": "StormCheckIntervalSeconds",
    "storm.timeout_seconds": "StormTimeoutSeconds",
    "storm.max_bytes": "StormMaxBytes",
    "storm.track_real_color": "StormColorTrackReal",
    "storm.track_forecast_color": "StormColorTrackPrediction",
    "storm.name_enabled": "StormNameOnOff",
    "storm.name_color": "StormColorName",
    "storm.name_align": "StormAlignName",
    "storm.detail": "StormDetailList",
    "storm.detail_color": "StormColorDetail",
    "storm.detail_align": "StormAlignDetail",
    "storm.image": "StormImageList",
    "storm.image_transparent": "StormImageTransparent",
    "storm.track_enabled": "StormTrackOnOff",
    "labels.warning_storm_seconds": "LabelWarningStorm",
    "norad.enabled": "NoradEnabled",
    "norad.catalog_ids": "NoradCatalogIds",
    "norad.output": "NoradOutput",
    "norad.journal": "NoradJournalFile",
    "norad.check_interval_seconds": "NoradCheckIntervalSeconds",
    "norad.timeout_seconds": "NoradTimeoutSeconds",
    "norad.max_bytes": "NoradMaxBytes",
    "norad.max_age_seconds": "NoradMaxAgeSeconds",
    "norad.color": "NoradColor",
    "norad.group_max_bytes": "NoradGroupMaxBytes",
    "labels.warning_norad_seconds": "LabelWarningNorad",
    "eclipse.enabled": "EclipseEnabled",
    "eclipse.path_url": "EclipsePathURL",
    "eclipse.marker_output": "EclipseMarkerOutput",
    "eclipse.arc_output": "EclipseArcOutput",
    "eclipse.journal": "EclipseJournalFile",
    "eclipse.check_interval_seconds": "EclipseCheckIntervalSeconds",
    "eclipse.timeout_seconds": "EclipseTimeoutSeconds",
    "eclipse.max_bytes": "EclipseMaxBytes",
    "eclipse.notify_hours": "EclipseNotifyHours",
    "eclipse.notice_enabled": "EclipseNoticeEnabled",
    "eclipse.edge_color": "EclipseEdgeColor",
    "eclipse.center_color": "EclipseCenterColor",
    "eclipse.notice_color": "EclipseNoticeColor",
    "santa.enabled": "SantaEnabled",
    "santa.output": "SantaOutput",
    "santa.journal": "SantaJournalFile",
    "santa.freshness_seconds": "SantaFreshnessSeconds",
}
for _storm_key in ("StormColorTrackReal", "StormColorTrackPrediction",
                   "StormNameOnOff", "StormColorName", "StormAlignName",
                   "StormAlignDetail", "StormDetailList", "StormColorDetail",
                   "StormImageList", "StormImageTransparent", "StormTrackOnOff",
                   "LabelWarningStorm"):
    TOML_KEYS["storm." + _storm_key] = _storm_key
SUPPORTED_KEYS = {value.lower() for value in TOML_KEYS.values()} | {
    "cloudusername", "cloudpassword",
}


def _scalar(value, canonical):
    if canonical.lower() in {"labelonoff", "volcanonameonoff", "stormnameonoff",
                             "stormtrackonoff", "noradenabled", "eclipseenabled",
                             "eclipsenoticeenabled", "santaenabled"} and isinstance(value, bool):
        return "On" if value else "Off"
    if not isinstance(value, (str, int, float, bool)):
        raise ConfigError("A supported configuration setting must be a scalar")
    return str(value).strip()


def _toml_values(raw):
    import tomllib
    try:
        document = tomllib.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, tomllib.TOMLDecodeError):
        raise ConfigError("Cannot parse TOML configuration") from None
    values, deferred = {}, {}

    def add(canonical, value, dotted):
        key = canonical.lower()
        if key in values:
            raise ConfigError("A setting is supplied through more than one configuration name")
        values[key] = _scalar(value, canonical)
        if key not in SUPPORTED_KEYS:
            deferred[dotted] = value

    def visit(table, prefix=""):
        for key, value in table.items():
            dotted = prefix + "." + key if prefix else key
            if dotted in {"norad.groups", "norad.profiles"}:
                if not isinstance(value, list):
                    raise ConfigError("NORAD groups and profiles must be TOML arrays of tables")
                values[dotted.replace(".", "")] = value
            elif dotted in TOML_KEYS:
                canonical = TOML_KEYS[dotted]
                if dotted.startswith("storm.") and dotted.rsplit(".", 1)[-1][:1].isupper():
                    valid_type = isinstance(value, str)  # Existing quoted legacy TOML keys.
                elif dotted in {"labels.enabled", "volcano.name_enabled",
                              "storm.name_enabled", "storm.track_enabled",
                              "norad.enabled", "eclipse.enabled", "santa.enabled",
                              "eclipse.notice_enabled"}:
                    valid_type = isinstance(value, bool)
                elif canonical in {
                        "CloudResolution", "CloudCheckIntervalSeconds",
                        "CloudTimeoutSeconds", "CloudMaxBytes", "LabelWarningCloud",
                        "VolcanoCheckIntervalSeconds", "VolcanoTimeoutSeconds",
                        "VolcanoMaxBytes", "LabelWarningVolcano",
                        "VolcanoCircleSizeInner", "VolcanoCircleSizeMiddle",
                        "VolcanoCircleSizeOuter", "QuakeCheckIntervalSeconds",
                        "QuakeTimeoutSeconds", "QuakeMaxBytes", "LabelWarningQuake",
                        "StormCheckIntervalSeconds", "StormTimeoutSeconds",
                        "StormMaxBytes", "LabelWarningStorm",
                        "NoradCheckIntervalSeconds", "NoradTimeoutSeconds",
                        "NoradMaxBytes", "NoradMaxAgeSeconds", "NoradGroupMaxBytes",
                        "LabelWarningNorad",
                        "EclipseCheckIntervalSeconds", "EclipseTimeoutSeconds",
                        "EclipseMaxBytes", "EclipseNotifyHours",
                        "SantaFreshnessSeconds"}:
                    valid_type = isinstance(value, int) and not isinstance(value, bool)
                elif canonical in {"QuakePixelMax", "QuakePixelMin", "QuakePixelFactor", "QuakeMinimumSize"}:
                    valid_type = (isinstance(value, (int, float)) and not isinstance(value, bool)
                                  or (canonical in {"QuakePixelMax", "QuakePixelMin"}
                                      and value == ""))
                else:
                    valid_type = isinstance(value, str)
                if not valid_type:
                    raise ConfigError("A native TOML configuration setting has the wrong type")
                add(canonical, value, dotted)
            elif prefix == "legacy":
                # Preserve every old setting; only current supported keys are applied.
                if isinstance(value, (str, int, float, bool)):
                    add(key, value, dotted)
                else:
                    deferred[dotted] = value
            elif not prefix and key.lower() in SUPPORTED_KEYS:
                add(key, value, dotted)
            elif isinstance(value, dict):
                visit(value, dotted)
            else:
                # Unknown future-feature structures remain available, never rewritten.
                deferred[dotted] = value
    visit(document)
    return values, deferred


def _ini_values(raw):
    values = {}
    try:
        text = raw.decode("utf-8-sig")
        parser = configparser.ConfigParser(interpolation=None, strict=True,
                                           empty_lines_in_values=False)
        parser.optionxform = str
        if not text.lstrip().startswith("["):
            text = "[totalmarker]\n" + text
        parser.read_string(text)
        for section in parser.sections():
            for key, value in parser.items(section):
                lowered = key.lower()
                if lowered in values:
                    raise ValueError
                values[lowered] = value.strip()
    except (UnicodeError, configparser.Error, ValueError):
        raise ConfigError("Cannot parse INI configuration") from None
    return values, {key: value for key, value in values.items() if key not in SUPPORTED_KEYS}


def _norad_style(row):
    allowed = {"enabled", "icon", "caption", "color", "trail", "transparent",
               "altcirc", "align"}
    if not isinstance(row, dict) or set(row) - allowed:
        raise ConfigError("NORAD style has an unknown or invalid setting")
    enabled = row.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise ConfigError("NORAD style enabled must be a boolean")
    icon = row.get("icon")
    if icon is not None and (not isinstance(icon, str) or
                             (icon != "" and not re.fullmatch(
                                 r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.(?:png|gif|jpg|jpeg)",
                                 icon, re.IGNORECASE))):
        raise ConfigError("NORAD icon must be a local image filename")
    caption = row.get("caption")
    if caption is not None and (not isinstance(caption, str) or
                                not re.fullmatch(r"[A-Za-z0-9 ._()/+ -]{0,64}", caption)):
        raise ConfigError("NORAD caption contains unsupported marker text")
    color = row.get("color")
    if color is not None and (not isinstance(color, str) or
                              not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", color)):
        raise ConfigError("NORAD color is invalid")
    align = row.get("align")
    if align is not None and align not in {"Above", "Below", "Left", "Right", "Center"}:
        raise ConfigError("NORAD alignment is invalid")
    arrays = {}
    for key, lower, upper in (("trail", -1440, 1440), ("transparent", 0, 255)):
        value = row.get(key)
        if value is not None:
            if (not isinstance(value, list) or len(value) != 3 or
                    any(type(item) is not int or not lower <= item <= upper
                        for item in value)):
                raise ConfigError("NORAD style numeric triplet is invalid")
            arrays[key] = tuple(value)
        else:
            arrays[key] = None
    if arrays["trail"] is not None and (arrays["trail"][0] > arrays["trail"][1] or
                                        not 1 <= arrays["trail"][2] <= 60):
        raise ConfigError("NORAD trail range or step is invalid")
    altcirc = row.get("altcirc")
    if altcirc is not None and (type(altcirc) is not int or not 0 <= altcirc <= 90):
        raise ConfigError("NORAD altitude circle elevation angle is invalid")
    return NoradStyle(enabled, icon, caption, color, arrays["trail"],
                      arrays["transparent"], altcirc, align)


def _norad_collections(values):
    groups, profiles = values.get("noradgroups", []), values.get("noradprofiles", [])
    if not isinstance(groups, list) or not isinstance(profiles, list):
        raise ConfigError("NORAD groups and profiles require TOML arrays of tables")
    if len(groups) > 4 or len(profiles) > 16:
        raise ConfigError("NORAD has too many groups or profiles")
    parsed_groups = []
    for row in groups:
        if not isinstance(row, dict) or set(row) - {
                "source", "name_contains", "enabled", "icon", "caption", "color",
                "trail", "transparent", "altcirc", "align"}:
            raise ConfigError("NORAD group has an unknown or invalid setting")
        source, name = row.get("source"), row.get("name_contains")
        if source not in {"stations", "science", "visual"}:
            raise ConfigError("NORAD group source is unsupported")
        if (not isinstance(name, str) or
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()/+-]{0,23}", name)):
            raise ConfigError("NORAD group name_contains is invalid")
        style = _norad_style({key: value for key, value in row.items()
                              if key not in {"source", "name_contains"}})
        parsed_groups.append(NoradGroup(source, name.upper(),
                                        True if style.enabled is None else style.enabled,
                                        style))
    parsed_profiles = []
    for row in profiles:
        if not isinstance(row, dict) or "catalog_id" not in row:
            raise ConfigError("NORAD profile requires catalog_id")
        catalog_id = row["catalog_id"]
        if type(catalog_id) is not int or not 1 <= catalog_id <= 99999:
            raise ConfigError("NORAD profile ID must fit Xplanet TLE format")
        style = _norad_style({key: value for key, value in row.items()
                              if key != "catalog_id"})
        parsed_profiles.append(NoradProfile(catalog_id, style))
    if len({profile.catalog_id for profile in parsed_profiles}) != len(parsed_profiles):
        raise ConfigError("NORAD profile IDs must be distinct")
    return tuple(parsed_groups), tuple(parsed_profiles)


def load(fs, path=None):
    values, deferred = {}, {}
    if path is not None:
        raw = fs.read(path, 1024 * 1024)
        if raw is None:
            raise ConfigError("Configuration file does not exist")
        if Path(path).suffix.lower() == ".toml":
            values, deferred = _toml_values(raw)
        else:
            values, deferred = _ini_values(raw)

    def get(key, default=""):
        return values.get(key.lower(), default)

    def number(key, default, minimum=0, maximum=2**31):
        try:
            value = int(get(key, str(default)) or str(default))
            if not minimum <= value <= maximum:
                raise ValueError
            return value
        except ValueError:
            raise ConfigError(key + " is outside its valid integer range") from None

    def decimal(key, default, *, optional=False):
        raw = get(key, "" if optional else str(default))
        if optional and raw == "":
            return None
        try:
            import math
            value = float(raw)
            if not math.isfinite(value) or value < 0 or value > 100000:
                raise ValueError
            return value
        except ValueError:
            raise ConfigError(key + " is outside its valid numeric range") from None

    provider = get("CloudProvider", "xeric").lower()
    if provider not in {"xeric", "custom"}:
        raise ConfigError("CloudProvider must be xeric or custom")
    resolution = number("CloudResolution", 4096 if provider == "xeric" else 0,
                        maximum=16384)
    default_name = "clouds-{resolution}.jpg" if resolution else "clouds-4096.jpg"
    local_name = expand_template(
        get("CloudLocalImageName", default_name) or default_name,
        resolution=resolution)
    if Path(local_name).name != local_name or local_name in {".", ".."}:
        raise ConfigError("CloudLocalImageName must be a filename; use CloudOutput for paths")

    # Validate both configured templates, but apply width/auth rules only to
    # the selected provider. Literal custom URL/filename values remain valid.
    if get("CloudURL") and get("CustomURLTemplate"):
        raise ConfigError("Supply only one custom cloud URL setting")
    urls = {}
    for prefix, template in [
            ("Xeric", get("XericURLTemplate") or XERIC_URL_TEMPLATE),
            ("Custom", get("CustomURLTemplate") or get("CloudURL"))]:
        # Custom resolution=0 disables width checking for literal URLs. An
        # inactive default Xeric template can be checked with its default width.
        template_resolution = resolution or (4096 if prefix == "Xeric" else 0)
        rendered = expand_template(template, resolution=template_resolution,
                                   local_image_name=local_name)
        urls[prefix] = https_url(rendered) if rendered else ""
    xeric_url = urlsplit(urls["Xeric"])
    if xeric_url.hostname != "secure.xericdesign.com" or xeric_url.port not in {None, 443}:
        raise ConfigError("Xeric URLs must use secure.xericdesign.com on port 443")
    if provider == "xeric":
        if resolution not in {2048, 4096, 8192}:
            raise ConfigError("Xeric resolution must be 2048, 4096 or 8192")
        if get("CloudURL"):
            raise ConfigError("CloudURL is for the custom provider")
        prefix = "Xeric"
        user = get("XericUsername", get("CloudUsername"))
        password = get("XericPassword", get("CloudPassword"))
    else:
        prefix = "Custom"
        # Deliberately never fall back to Xeric or legacy Cloud credentials.
        user, password = get("CustomUsername"), get("CustomPassword")
    url = urls[prefix]
    if not url:
        raise ConfigError("The selected custom provider requires an HTTPS URL")
    user_env = get(prefix + "UsernameEnv")
    pass_env = get(prefix + "PasswordEnv")
    for reference in [user_env, pass_env]:
        if reference and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference):
            raise ConfigError("Invalid authentication environment reference")
    if (user and user_env) or (password and pass_env):
        raise ConfigError("Choose plaintext or an environment reference for each credential")
    auth_mode = get(prefix + "AuthMode", get("CloudAuthMode", "auto")).lower()
    if auth_mode == "auto":
        auth_mode = ("basic" if provider == "xeric" or any(
            [user, password, user_env, pass_env]) else "none")
    if auth_mode not in {"basic", "none"} or (provider == "xeric" and auth_mode != "basic"):
        raise ConfigError("Xeric requires basic authentication; custom allows basic or none")
    if auth_mode == "none" and any([user, password, user_env, pass_env]):
        raise ConfigError("Authentication fields conflict with CloudAuthMode=none")
    colors = tuple(get(key, default) or default for key, default in [
        ("LabelColorOk", "Green"), ("LabelColorWarn", "Yellow"),
        ("LabelColorError", "Red")])
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", color) for color in colors):
        raise ConfigError("Invalid label color")
    enabled = get("LabelOnOff", "On").lower() or "on"
    if enabled not in {"on", "off"}:
        raise ConfigError("LabelOnOff must be On or Off")
    paths = {
        "image": expand_template(
            get("CloudOutput") or "images/{local_image_name}",
            resolution=resolution, local_image_name=local_name),
        "labels": get("LabelOutput") or "markers/updatelabel",
        "state": get("StateFile") or ".state/totalmarker/state.json",
        "journal": get("JournalFile") or ".state/totalmarker/pending.json",
        "lock": get("LockFile") or ".state/totalmarker/job.lock",
        "log": get("LogFile", "logs/totalmarker/events.jsonl") or None,
    }
    def token(key, default):
        value = (get(key) or default).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value):
            raise ConfigError(key + " has an invalid Xplanet option")
        return value

    name_on = get("VolcanoNameOnOff", "On").lower()
    if name_on not in {"on", "off"}:
        raise ConfigError("VolcanoNameOnOff must be On or Off")
    transparency = get("VolcanoImageTransparent").strip()
    if transparency and not re.fullmatch(r"[0-9]{1,9}", transparency):
        raise ConfigError("VolcanoImageTransparent must contain digits")
    image_name = get("VolcanoImageList").strip()
    image_parts = Path(image_name).parts
    if image_name and (image_name in {".", ".."} or Path(image_name).is_absolute() or
                       any(part in {".", ".."} or not re.fullmatch(
                           r"[A-Za-z0-9_.-]+", part) for part in image_parts)):
        raise ConfigError("VolcanoImageList must be a safe relative image path")
    detail = get("VolcanoDetailList")
    if any(c in detail for c in '\r\n"\\') or len(detail) > 1024:
        raise ConfigError("VolcanoDetailList contains unsupported marker text")
    if re.search(r"<[^>]*>", re.sub(r"<(?:lat|long|elevation|elev|name|location)>",
                                   "", detail)):
        raise ConfigError("VolcanoDetailList contains an unsupported placeholder")
    volcano_provider = get("VolcanoProvider", "cap").lower()
    if volcano_provider not in {"cap", "weekly_html"}:
        raise ConfigError("VolcanoProvider must be cap or weekly_html")
    volcano = VolcanoOptions(
        provider=volcano_provider,
        url=https_url(get("VolcanoURL") or VolcanoOptions.url),
        marker=get("VolcanoOutput") or VolcanoOptions.marker,
        journal=get("VolcanoJournalFile") or VolcanoOptions.journal,
        interval=number("VolcanoCheckIntervalSeconds", 24 * 3600),
        timeout=number("VolcanoTimeoutSeconds", 30, minimum=1, maximum=300),
        max_bytes=number("VolcanoMaxBytes", 8 * 1024 * 1024, minimum=1024,
                         maximum=32 * 1024 * 1024),
        warning=number("LabelWarningVolcano", 3 * 24 * 3600),
        circle_sizes=tuple(number("VolcanoCircleSize" + suffix, default) for suffix, default in
                           [("Inner", 4), ("Middle", 8), ("Outer", 12)]),
        circle_colors=tuple(token("VolcanoCircleColor" + suffix, default) for
                            suffix, default in [("Inner", "Yellow"),
                                               ("Middle", "Red"), ("Outer", "Brown")]),
        name_enabled=name_on == "on", name_color=token("VolcanoNameColor", "Brown"),
        name_align=token("VolcanoNameAlign", "Below"), image=image_name,
        image_transparent=transparency, detail=detail,
        detail_align=token("VolcanoDetailAlign", "Below"),
        detail_color=token("VolcanoDetailColor", "Brown"))
    duration = get("QuakeReportingDuration", "Week").title()
    size = get("QuakeReportingSize", "All").lower()
    if duration not in {"Day", "Week", "Month"} or size not in {
            "all", "1.0", "2.5", "4.5", "significant"}:
        raise ConfigError("Invalid quake reporting duration or size")
    qimage = get("QuakeImageList").strip()
    if qimage and (Path(qimage).is_absolute() or any(part in {".", ".."} or not
            re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in Path(qimage).parts)):
        raise ConfigError("QuakeImageList must be a safe relative image path")
    qtrans = get("QuakeImageTransparent").strip()
    if qtrans and not re.fullmatch(r"[0-9]{1,9}", qtrans):
        raise ConfigError("QuakeImageTransparent must contain digits")
    qdetail = get("QuakeDetailList", "<mag>")
    if any(c in qdetail for c in '\r\n"\\') or len(qdetail) > 1024 or re.search(
            r"<[^>]*>", re.sub(r"<(?:date|time|lat|long|depth|mag|quality|location)>",
                                "", qdetail)):
        raise ConfigError("QuakeDetailList contains unsupported marker text")
    quake = QuakeOptions(
        duration=duration, size=size, minimum=decimal("QuakeMinimumSize", 6),
        marker=get("QuakeOutput") or QuakeOptions.marker,
        journal=get("QuakeJournalFile") or QuakeOptions.journal,
        interval=number("QuakeCheckIntervalSeconds", 20 * 60),
        timeout=number("QuakeTimeoutSeconds", 30, minimum=1, maximum=300),
        max_bytes=number("QuakeMaxBytes", 32 * 1024 * 1024, minimum=1024,
                         maximum=128 * 1024 * 1024),
        warning=number("LabelWarningQuake", 3 * 3600),
        circle_color=token("QuakeCircleColor", "Multi"),
        pixel_max=decimal("QuakePixelMax", None, optional=True),
        pixel_min=decimal("QuakePixelMin", None, optional=True),
        pixel_factor=decimal("QuakePixelFactor", 1),
        image=qimage, image_transparent=qtrans, detail=qdetail,
        detail_color=token("QuakeDetailColor", "Multi"),
        detail_color_min=token("QuakeDetailColorMin", "Green"),
        detail_color_int=token("QuakeDetailColorInt", "Yellow"),
        detail_color_max=token("QuakeDetailColorMax", "Red"),
        detail_align=token("QuakeDetailAlign", "Above"))
    storm_name = get("StormNameOnOff", "On").lower()
    storm_track = get("StormTrackOnOff", "On").lower()
    if storm_name not in {"on", "off"} or storm_track not in {"on", "off"}:
        raise ConfigError("Storm name and track switches must be On or Off")
    simage = get("StormImageList").strip()
    if simage and (Path(simage).is_absolute() or any(part in {".", ".."} or not
            re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in Path(simage).parts)):
        raise ConfigError("StormImageList must be a safe relative image path")
    strans = get("StormImageTransparent").strip()
    if strans and not re.fullmatch(r"[0-9]{1,9}", strans):
        raise ConfigError("StormImageTransparent must contain digits")
    sdetail = get("StormDetailList", "<type>")
    if any(c in sdetail for c in '\r\n"\\') or len(sdetail) > 1024 or re.search(
            r"<[^>]*>", re.sub(r"<(?:lat|long|type|name|speed)>", "", sdetail)):
        raise ConfigError("StormDetailList contains unsupported marker text")
    storm = StormOptions(
        marker=get("StormOutput") or StormOptions.marker,
        arc=get("StormArcOutput") or StormOptions.arc,
        journal=get("StormJournalFile") or StormOptions.journal,
        interval=number("StormCheckIntervalSeconds", 30 * 60),
        timeout=number("StormTimeoutSeconds", 30, minimum=1, maximum=300),
        max_bytes=number("StormMaxBytes", 16 * 1024 * 1024, minimum=1024,
                         maximum=32 * 1024 * 1024),
        warning=number("LabelWarningStorm", 3 * 3600),
        track_real_color=token("StormColorTrackReal", "Blue"),
        track_forecast_color=token("StormColorTrackPrediction", "SkyBlue"),
        name_enabled=storm_name == "on", name_color=token("StormColorName", "SkyBlue"),
        name_align=token("StormAlignName", "Above"), detail=sdetail,
        detail_color=token("StormColorDetail", "SkyBlue"),
        detail_align=token("StormAlignDetail", "Below"), image=simage,
        image_transparent=strans, track_enabled=storm_track == "on")
    norad_enabled = get("NoradEnabled", "Off").lower()
    if norad_enabled not in {"on", "off"}:
        raise ConfigError("NoradEnabled must be On or Off")
    raw_ids = get("NoradCatalogIds").strip()
    id_parts = [part.strip() for part in raw_ids.split(",")] if raw_ids else []
    if any(not re.fullmatch(r"[1-9][0-9]{0,4}", part) for part in id_parts):
        raise ConfigError("NORAD TLE catalog IDs must be one to five decimal digits")
    catalog_ids = tuple(int(part) for part in id_parts)
    if len(catalog_ids) > 16 or len(set(catalog_ids)) != len(catalog_ids):
        raise ConfigError("NORAD catalog IDs must be distinct and contain at most 16 entries")
    norad_groups, norad_profiles = _norad_collections(values)
    if (norad_enabled == "on" and not catalog_ids
            and not any(group.enabled for group in norad_groups)):
        raise ConfigError("Enabled NORAD requires explicit IDs or an enabled group")
    norad = NoradOptions(
        enabled=norad_enabled == "on", catalog_ids=catalog_ids,
        satellite=get("NoradOutput") or NoradOptions.satellite,
        journal=get("NoradJournalFile") or NoradOptions.journal,
        interval=number("NoradCheckIntervalSeconds", 7200, minimum=7200),
        timeout=number("NoradTimeoutSeconds", 30, minimum=1, maximum=300),
        max_bytes=number("NoradMaxBytes", 64 * 1024, minimum=1024, maximum=1024 * 1024),
        group_max_bytes=number("NoradGroupMaxBytes", 1024 * 1024,
                               minimum=1024, maximum=2 * 1024 * 1024),
        max_age=number("NoradMaxAgeSeconds", 14 * 24 * 3600, minimum=3600),
        warning=number("LabelWarningNorad", 24 * 3600),
        color=token("NoradColor", "Yellow"), groups=norad_groups,
        profiles=norad_profiles)
    if norad.satellite.endswith(".tle"):
        raise ConfigError("NoradOutput must name the satellite selector without .tle")
    eclipse_enabled = get("EclipseEnabled", "Off").lower()
    if eclipse_enabled not in {"on", "off"}:
        raise ConfigError("EclipseEnabled must be On or Off")
    eclipse_notice_enabled = get("EclipseNoticeEnabled", "On").lower()
    if eclipse_notice_enabled not in {"on", "off"}:
        raise ConfigError("EclipseNoticeEnabled must be On or Off")
    eclipse_url = get("EclipsePathURL").strip()
    if eclipse_url:
        eclipse_url = https_url(eclipse_url)
        parsed_eclipse = urlsplit(eclipse_url)
        if (parsed_eclipse.hostname != "eclipse.gsfc.nasa.gov"
                or parsed_eclipse.port not in {None, 443}
                or not re.fullmatch(
                    r"/SEpath/SEpath[0-9]{4}/SE[0-9]{4}[A-Z][a-z]{2}[0-9]{2}[TAH]path\.html",
                    parsed_eclipse.path)):
            raise ConfigError("EclipsePathURL must be a NASA central solar eclipse path table")
    eclipse = EclipseOptions(
        enabled=eclipse_enabled == "on", path_url=eclipse_url,
        marker=get("EclipseMarkerOutput") or EclipseOptions.marker,
        arc=get("EclipseArcOutput") or EclipseOptions.arc,
        journal=get("EclipseJournalFile") or EclipseOptions.journal,
        interval=number("EclipseCheckIntervalSeconds", 24 * 3600, minimum=6 * 3600),
        timeout=number("EclipseTimeoutSeconds", 30, minimum=1, maximum=300),
        max_bytes=number("EclipseMaxBytes", 2 * 1024 * 1024, minimum=1024,
                         maximum=8 * 1024 * 1024),
        notify_hours=number("EclipseNotifyHours", 48, maximum=14 * 24),
        notice_enabled=eclipse_notice_enabled == "on",
        edge_color=token("EclipseEdgeColor", "Grey"),
        center_color=token("EclipseCenterColor", "Black"),
        notice_color=token("EclipseNoticeColor", "White"))
    santa_enabled = get("SantaEnabled", "Off").lower()
    if santa_enabled not in {"on", "off"}:
        raise ConfigError("SantaEnabled must be On or Off")
    santa = SantaOptions(
        enabled=santa_enabled == "on",
        marker=get("SantaOutput") or SantaOptions.marker,
        journal=get("SantaJournalFile") or SantaOptions.journal,
        freshness_seconds=number("SantaFreshnessSeconds", 0, maximum=24 * 3600))
    if santa.enabled and santa.freshness_seconds == 0:
        raise ConfigError("Enabled Santa requires a documented freshness interval")
    outputs = [value for value in
               [*paths.values(), volcano.marker, volcano.journal,
                quake.marker, quake.journal, storm.marker, storm.arc,
                storm.journal, norad.satellite, norad.satellite + ".tle",
                norad.journal, eclipse.marker, eclipse.arc,
                eclipse.journal, santa.marker, santa.journal] if value]
    if path is not None:
        source = str(fs.resolve(path)).casefold()
        if any(str(fs.resolve(value)).casefold() == source for value in outputs):
            raise ConfigError("Outputs must not overwrite the configuration file")
    resolved = [fs.resolve(value, write=True) for value in outputs]
    # Case variants can name the same file on macOS even before it exists.
    if len(resolved) != len({str(value).casefold() for value in resolved}):
        raise ConfigError("Configured output paths must be distinct")
    return Settings(
        provider, https_url(url), resolution, AuthSpec(auth_mode, user, password,
        user_env, pass_env), **paths,
        interval=number("CloudCheckIntervalSeconds", 3600),
        timeout=number("CloudTimeoutSeconds", 30, minimum=1, maximum=300),
        max_bytes=number("CloudMaxBytes", 32 * 1024 * 1024, minimum=1024,
                         maximum=128 * 1024 * 1024),
        warning=number("LabelWarningCloud", 21600), colors=colors,
        labels_enabled=enabled == "on", volcano=volcano, quake=quake, storm=storm,
        norad=norad, eclipse=eclipse, santa=santa,
        unrelated=values, deferred_settings=deferred)
