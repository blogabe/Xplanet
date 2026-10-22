"""Strict adapters for official NHC and JTWC worldwide active-storm products.

NHC supplies AL/EP/CP current positions plus ATCF best and official forecasts.
JTWC RSS discovers WP/Indian/Southern warning text and KMZ best-track history.
Missing or stale coverage invalidates the entire snapshot.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import gzip
from html.parser import HTMLParser
from io import BytesIO
import json
import re
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

from .errors import FeedError
from .storm_advisory import parse_advisory
from .storm_model import (ForecastPoint, Storm, StormSnapshot, TrackPoint,
                          validate_snapshot)

NHC_INDEX = "https://www.nhc.noaa.gov/CurrentStorms.json"
JTWC_RSS = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
NHC_ATCF = "https://ftp.nhc.noaa.gov/atcf/"
JTWC_ADVISORIES = {"abpw": "abpwweb.txt", "abio": "abioweb.txt"}
REQUIRED_GROUPS = frozenset({"nhc", "jtwc_west", "jtwc_indian", "jtwc_south"})
NHC_ID = re.compile(r"^(AL|EP|CP)([0-9]{2})(20[0-9]{2})$")
JTWC_FILE = re.compile(r"^(wp|io|sh)([0-9]{2})([0-9]{2})web\.txt$")
POSITION = re.compile(r"\b([0-9]{1,2}(?:\.[0-9]+)?)([NS])\s+([0-9]{1,3}(?:\.[0-9]+)?)([EW])\b")
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


def _stamp(value):
    try:
        if not isinstance(value, str):
            raise ValueError
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        raise FeedError("Storm source timestamp is invalid") from None


def _http_stamp(value):
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.timestamp()
    except (ValueError, TypeError, OverflowError):
        raise FeedError("Storm source date header is invalid") from None


def _date10(value):
    try:
        return datetime.strptime(value, "%Y%m%d%H").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        raise FeedError("Storm ATCF cycle is invalid") from None


def _coordinate(value):
    match = re.fullmatch(r"([0-9]{1,4})([NSEW])", value.strip())
    if not match:
        raise FeedError("Storm ATCF coordinate is invalid")
    number = int(match[1]) / 10
    return -number if match[2] in "SW" else number


def _atcf_rows(body, identity):
    try:
        lines = body.decode("ascii").splitlines()
    except UnicodeError:
        raise FeedError("Storm ATCF product is not ASCII") from None
    if len(lines) > 250_000:
        raise FeedError("Storm ATCF product has too many rows")
    rows = []
    for line in lines:
        cells = [part.strip() for part in line.split(",")]
        if len(cells) < 8:
            raise FeedError("Storm ATCF row is incomplete")
        if cells[0].upper() != identity[:2] or cells[1].zfill(2) != identity[2:4]:
            raise FeedError("Storm ATCF product has a different identity")
        rows.append(cells)
    if not rows:
        raise FeedError("Storm ATCF product is empty")
    return rows


def parse_nhc_best(body, identity, current_at):
    points = {}
    for row in _atcf_rows(body, identity):
        if row[4] != "BEST":
            continue
        stamp = _date10(row[2])
        if stamp > current_at:
            continue  # Best-track revisions can run ahead of the current JSON advisory.
        point = TrackPoint(stamp, _coordinate(row[6]), _coordinate(row[7]))
        if stamp in points and points[stamp] != point:
            raise FeedError("Storm best-track cycle has conflicting positions")
        points[stamp] = point
    if not points:
        raise FeedError("Storm best-track product has no usable positions")
    return tuple(points[at] for at in sorted(points) if at < current_at)


def parse_nhc_forecast(body, identity, current_at):
    try:
        with gzip.GzipFile(fileobj=BytesIO(body)) as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
    except (OSError, EOFError):
        raise FeedError("Storm official forecast gzip is invalid") from None
    if len(raw) > 32 * 1024 * 1024:
        raise FeedError("Storm official forecast exceeds the size limit")
    cycles = {}
    for row in _atcf_rows(raw, identity):
        if row[4] != "OFCL":
            continue
        at = _date10(row[2])
        if at > current_at:
            continue
        try:
            lead = int(row[5])
        except ValueError:
            raise FeedError("Storm forecast lead is invalid") from None
        if not 0 <= lead <= 240:
            continue
        point = TrackPoint(at + lead * 3600, _coordinate(row[6]), _coordinate(row[7]))
        group = cycles.setdefault(at, {})
        if lead in group and group[lead] != point:
            raise FeedError("Storm official forecast has conflicting positions")
        group[lead] = point
    if not cycles:
        raise FeedError("Storm official forecast has no issued cycle")
    cycle = max(cycles)
    values = cycles[cycle]
    # NHC advisories normally arrive every six hours. Allow delayed index
    # updates, but never publish an old OFCL deck as a current forecast.
    if current_at - cycle > 24 * 3600:
        raise FeedError("Storm official forecast cycle is stale")
    if 0 not in values or not any(lead > 0 for lead in values):
        raise FeedError("Storm official forecast has no complete track")
    if not any(point.at > current_at for lead, point in values.items() if lead > 0):
        raise FeedError("Storm official forecast has no future positions")
    return values[0], tuple(ForecastPoint(lead, values[lead].at,
                                         values[lead].lat, values[lead].lon)
                            for lead in sorted(values) if lead > 0)


@dataclass(frozen=True)
class JtwcProduct:
    identity: str
    warning_url: str
    kmz_url: str
    group: str
    kind: str = "warning"


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.links = []
        self._href = None
        self._label = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.urls.append(href)
                self._href = href
                self._label = []

    def handle_data(self, data):
        if self._href is not None:
            self._label.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._label).strip()))
            self._href = None
            self._label = []


def _jtwc_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "www.metoc.navy.mil"
            or parsed.port is not None or parsed.query or parsed.fragment
            or not parsed.path.startswith("/jtwc/products/")):
        raise FeedError("Storm RSS linked outside official JTWC products")
    return parsed.path.rsplit("/", 1)[-1]


def parse_jtwc_rss(body):
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise FeedError("Storm JTWC RSS is invalid XML") from None
    if root.tag != "rss":
        raise FeedError("Storm JTWC RSS root is invalid")
    titles = {
        "Current Northwest Pacific/North Indian Ocean* Tropical Systems": "north",
        "Current Southern Hemisphere Tropical Systems": "south",
    }
    items = {}
    advisories = None
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "").strip()
        if title == "Current Significant Tropical Weather Advisories":
            if advisories is not None:
                raise FeedError("Storm JTWC RSS duplicates significant advisories")
            description = item.findtext("description")
            if description is None:
                raise FeedError("Storm JTWC RSS lacks significant advisory links")
            anchors = _Anchors()
            anchors.feed(description)
            found = {}
            for url in anchors.urls:
                filename = _jtwc_url(url)
                for kind, expected in JTWC_ADVISORIES.items():
                    if filename == expected:
                        if kind in found:
                            raise FeedError("Storm JTWC RSS duplicates an advisory link")
                        found[kind] = url
            if set(found) != set(JTWC_ADVISORIES):
                raise FeedError("Storm JTWC RSS lacks both significant advisories")
            advisories = found
            continue
        if title not in titles:
            continue
        category = titles[title]
        if category in items:
            raise FeedError("Storm JTWC RSS duplicates a coverage category")
        date = _http_stamp(item.findtext("pubDate"))
        description = item.findtext("description")
        if description is None:
            raise FeedError("Storm JTWC RSS category lacks a description")
        links = _Anchors()
        links.feed(description)
        product_links = {}
        for url, label in links.links:
            name = _jtwc_url(url)
            if name.endswith("web.txt") or name.endswith(".kmz"):
                if name in product_links:
                    raise FeedError("Storm JTWC RSS repeats a product link")
                product_links[name] = (url, label)
        products = []
        for filename, (url, label) in product_links.items():
            match = JTWC_FILE.fullmatch(filename)
            if not match:
                continue
            prefix, number, year = match.groups()
            if (category == "north" and prefix not in {"wp", "io"}
                    or category == "south" and prefix != "sh"):
                raise FeedError("Storm JTWC RSS product is in the wrong region")
            basename = filename[:-7]
            kmz_name = basename + ".kmz"
            if kmz_name not in product_links:
                raise FeedError("Storm JTWC RSS warning lacks a KMZ track")
            if label == "TC Warning Text":
                kind = "warning"
            elif label == "TCFA Text":
                kind = "formation_alert"
            else:
                raise FeedError("Storm JTWC RSS product type is ambiguous")
            group = ("jtwc_south" if category == "south" else
                     "jtwc_west" if prefix == "wp" else "jtwc_indian")
            products.append(JtwcProduct(prefix.upper() + number + "20" + year,
                                        url, product_links[kmz_name][0], group, kind))
        # A category with no warning link must say so explicitly. Unrecognized
        # templating or a partly published RSS item cannot erase last-good data.
        if not products and not re.search(r"\b(?:no active|none active|no current)\b",
                                          description, flags=re.I):
            raise FeedError("Storm JTWC RSS does not confirm an empty region")
        items[category] = (date, products)
    if set(items) != {"north", "south"}:
        raise FeedError("Storm JTWC RSS lacks worldwide coverage categories")
    if advisories is None:
        raise FeedError("Storm JTWC RSS lacks significant advisories")
    north_at, north = items["north"]
    south_at, south = items["south"]
    return (tuple(north + south),
            {"jtwc_west": north_at, "jtwc_indian": north_at,
             "jtwc_south": south_at}, advisories)


def _warning_coordinate(text):
    match = POSITION.search(text)
    if not match:
        raise FeedError("Storm JTWC warning position is invalid")
    lat, ns, lon, ew = match.groups()
    return (float(lat) * (-1 if ns == "S" else 1),
            float(lon) * (-1 if ew == "W" else 1))


def _jtwc_code_matches(identity, code):
    return (code[:2] == identity[2:4]
            and code[-1] in {"WP": "W", "IO": "AB", "SH": "PS"}.get(identity[:2], ""))


def parse_jtwc_formation_alert(body, identity, rss_at):
    """Validate a TCFA as an invest; its point must agree with an advisory."""
    try:
        lines = body.decode("ascii").splitlines()
    except UnicodeError:
        raise FeedError("Storm JTWC formation alert is not ASCII") from None
    if len(lines) > 5000:
        raise FeedError("Storm JTWC formation alert has too many lines")
    subjects = [line for line in lines if line.startswith("SUBJ/")]
    if len(subjects) != 1:
        raise FeedError("Storm JTWC formation alert lacks one subject")
    subject = re.fullmatch(r"SUBJ/TROPICAL CYCLONE FORMATION ALERT "
                           r"\(INVEST ([0-9]{2}[A-Z])\)//", subjects[0])
    if not subject or not _jtwc_code_matches(identity, subject[1]):
        raise FeedError("Storm JTWC formation alert identity disagrees with RSS")
    if set(re.findall(r"\bINVEST\s+([0-9]{2}[A-Z])\b", "\n".join(lines))) != {subject[1]}:
        raise FeedError("Storm JTWC formation alert repeats a different invest")
    header = re.fullmatch(r"WT[A-Z]{2}[0-9]{2}\s+PGTW\s+([0-9]{6})", lines[0]) if lines else None
    if not header:
        raise FeedError("Storm JTWC formation alert lacks a dated header")
    day, hour, minute = map(int, (header[1][:2], header[1][2:4], header[1][4:]))
    published = datetime.fromtimestamp(rss_at, timezone.utc)
    month_start = published.replace(day=1)
    candidates = []
    for month in (month_start - timedelta(days=1), month_start,
                  month_start + timedelta(days=32)):
        try:
            candidates.append(datetime(month.year, month.month, day, hour, minute,
                                       tzinfo=timezone.utc))
        except ValueError:
            continue
    if not candidates:
        raise FeedError("Storm JTWC formation alert date is invalid")
    observed = min(candidates, key=lambda value: abs(value.timestamp() - rss_at))
    if abs(observed.timestamp() - rss_at) > 48 * 3600:
        raise FeedError("Storm JTWC formation alert date disagrees with RSS")
    season = observed.year + (identity[:2] == "SH" and observed.month >= 7)
    if int(identity[-4:]) != season:
        raise FeedError("Storm JTWC formation alert season disagrees with RSS")
    current = list(re.finditer(r"\bIS NOW LOCATED NEAR\s+" + POSITION.pattern,
                              "\n".join(lines)))
    if len(current) != 1:
        raise FeedError("Storm JTWC formation alert lacks one current position")
    lat, ns, lon, ew = current[0].groups()
    latitude = float(lat) * (-1 if ns == "S" else 1)
    longitude = float(lon) * (-1 if ew == "W" else 1)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise FeedError("Storm JTWC formation alert position is out of range")
    return TrackPoint(observed.timestamp(), latitude, longitude), subject[1]


def parse_jtwc_warning(body, identity, rss_at):
    try:
        lines = body.decode("ascii").splitlines()
    except UnicodeError:
        raise FeedError("Storm JTWC warning is not ASCII") from None
    if len(lines) > 5000:
        raise FeedError("Storm JTWC warning has too many lines")
    header = re.search(r"(?m)^SUBJ/[^\n]*?\b([0-9]{2}[A-Z])\s+\(([^)]+)\)\s+WARNING", "\n".join(lines))
    if not header:
        raise FeedError("Storm JTWC warning lacks a named storm header")
    if not _jtwc_code_matches(identity, header[1]):
        raise FeedError("Storm JTWC warning identity disagrees with RSS")
    base_line = next((i for i, line in enumerate(lines) if "WARNING POSITION:" in line), None)
    if base_line is None or base_line + 1 >= len(lines):
        raise FeedError("Storm JTWC warning lacks its observed position")
    line = lines[base_line + 1]
    valid = re.search(r"\b([0-9]{2})([0-9]{2})([0-9]{2})Z\b", line)
    if not valid:
        raise FeedError("Storm JTWC warning lacks a dated position")
    day, hour, minute = map(int, valid.groups())
    published = datetime.fromtimestamp(rss_at, timezone.utc)
    candidates = []
    month_start = published.replace(day=1)
    for month in (month_start - timedelta(days=1), month_start,
                  month_start + timedelta(days=32)):
        try:
            candidate = datetime(month.year, month.month, day, hour, minute,
                                 tzinfo=timezone.utc)
        except ValueError:
            continue
        candidates.append(candidate)
    if not candidates:
        raise FeedError("Storm JTWC warning position date is invalid")
    observed = min(candidates, key=lambda value: abs(value.timestamp() - rss_at))
    base_at = observed.timestamp()
    if abs(base_at - rss_at) > 48 * 3600:
        raise FeedError("Storm JTWC warning position disagrees with RSS date")
    season = observed.year + (1 if identity[:2] == "SH" and observed.month >= 7 else 0)
    if int(identity[-4:]) != season:
        raise FeedError("Storm JTWC warning season disagrees with RSS")
    lat, lon = _warning_coordinate(line)
    current = TrackPoint(base_at, lat, lon)
    wind = None
    for line in lines[base_line + 1:]:
        match = re.search(r"MAX SUSTAINED WINDS\s*-\s*([0-9]{2,3})\s*KT", line)
        if match:
            wind = int(match[1])
            break
    forecasts = []
    for i, line in enumerate(lines):
        match = re.search(r"\b([0-9]{1,3}) HRS, VALID AT:", line)
        if not match:
            continue
        if i + 1 >= len(lines):
            raise FeedError("Storm JTWC forecast lead lacks a position")
        lead = int(match[1])
        lat, lon = _warning_coordinate(lines[i + 1])
        at = base_at + lead * 3600
        valid = datetime.fromtimestamp(at, timezone.utc).strftime("%d%H%M") + "Z"
        if not re.search(r"\b" + valid + r"\b", lines[i + 1]):
            raise FeedError("Storm JTWC forecast valid time disagrees with lead")
        forecasts.append(ForecastPoint(lead, at, lat, lon))
    if not forecasts:
        raise FeedError("Storm JTWC warning lacks issued forecast points")
    name = header[2].title()
    return current, name, wind, tuple(forecasts), header[1]


def parse_jtwc_kmz(body, current, identity, name):
    try:
        with ZipFile(BytesIO(body)) as archive:
            members = archive.infolist()
            if (len(members) > 100 or sum(member.file_size for member in members) > 8 * 1024 * 1024):
                raise FeedError("Storm JTWC KMZ exceeds safe bounds")
            member = archive.getinfo("doc.kml")
            if member.file_size > 4 * 1024 * 1024:
                raise FeedError("Storm JTWC KML exceeds the size limit")
            root = ET.fromstring(archive.read(member))
    except (BadZipFile, KeyError, ET.ParseError, OSError):
        raise FeedError("Storm JTWC KMZ is invalid") from None
    documents = root.findall("k:Document", KML_NS)
    storm_folders = documents[0].findall("k:Folder", KML_NS) if len(documents) == 1 else []
    if len(storm_folders) != 1:
        raise FeedError("Storm JTWC KMZ lacks one storm identity")
    storm_folder = storm_folders[0]
    kmz_name = storm_folder.findtext("k:name", default="", namespaces=KML_NS)
    description = storm_folder.findtext("k:description", default="", namespaces=KML_NS)
    headers = list(re.finditer(r"\b([0-9]{2}[A-Z])\s+\(([^)]+)\)\s+WARNING\b",
                               description, flags=re.I))
    normalized = lambda value: " ".join(value.split()).casefold()
    if (len(headers) != 1 or
            not _jtwc_code_matches(identity, headers[0][1].upper()) or
            normalized(headers[0][2]) != normalized(name) or
            normalized(kmz_name) != normalized(name)):
        raise FeedError("Storm JTWC KMZ identity disagrees with warning")
    history_folders = [folder for folder in storm_folder.findall(".//k:Folder", KML_NS)
                       if folder.findtext("k:name", default="", namespaces=KML_NS)
                       == "Previous Best Track Posits"]
    if len(history_folders) != 1:
        raise FeedError("Storm JTWC KMZ lacks one previous best-track folder")
    history_folder = history_folders[0]
    points = {}
    for place in history_folder.findall("k:Placemark", KML_NS):
        name = place.findtext("k:name", default="", namespaces=KML_NS)
        coord = place.findtext(".//k:Point/k:coordinates", default="", namespaces=KML_NS)
        if not coord:
            continue  # The folder also contains a whole-track LineString.
        if not re.fullmatch(r"[0-9]{8}Z", name):
            raise FeedError("Storm JTWC history time is invalid")
        try:
            at = datetime.strptime(name, "%y%m%d%HZ").replace(tzinfo=timezone.utc).timestamp()
            lon, lat = [float(value) for value in coord.strip().split(",")[:2]]
        except (ValueError, IndexError):
            raise FeedError("Storm JTWC history coordinate is invalid") from None
        if at > current.at:
            continue
        point = TrackPoint(at, lat, lon)
        if at in points and points[at] != point:
            raise FeedError("Storm JTWC history has conflicting positions")
        points[at] = point
    if not points:
        raise FeedError("Storm JTWC KMZ has no usable history")
    return tuple(points[at] for at in sorted(points) if at < current.at)


def _fresh(at, now, max_age, label):
    if at > now + 3600 or now - at > max_age:
        raise FeedError("Storm " + label + " is stale or future-dated")


def _fresh_advisory(advisory, now, kind):
    if advisory.issue_at > now + 3600 or now > advisory.valid_until_at:
        raise FeedError("Storm JTWC " + kind.upper() + " advisory is stale or future-dated")


def collect_snapshot(fetcher, *, now, timeout=30, max_bytes=16 * 1024 * 1024):
    def get(url, limit=max_bytes):
        response = fetcher.fetch(url, timeout=timeout, max_bytes=limit)
        if response.status != 200:
            raise FeedError("Storm source unexpectedly returned not-modified")
        return response

    nhc_response = get(NHC_INDEX, 2 * 1024 * 1024)
    try:
        index = json.loads(nhc_response.body)
    except (ValueError, UnicodeError):
        raise FeedError("Storm NHC active index is invalid JSON") from None
    if not isinstance(index, dict) or not isinstance(index.get("activeStorms"), list):
        raise FeedError("Storm NHC active index lacks its storm list")
    jtwc_response = get(JTWC_RSS, 2 * 1024 * 1024)
    discovered, source_times, advisory_urls = parse_jtwc_rss(jtwc_response.body)
    rss_times = source_times.copy()
    deadlines = []
    for group, at in source_times.items():
        _fresh(at, now, 12 * 3600, group + " RSS")
        deadlines.append(at + 12 * 3600)
    storms, nhc_times = [], []
    for item in index["activeStorms"]:
        if not isinstance(item, dict):
            raise FeedError("Storm NHC index contains an invalid entry")
        identity = str(item.get("id", "")).upper()
        if not NHC_ID.fullmatch(identity):
            raise FeedError("Storm NHC index contains an unsupported identity")
        at = _stamp(item.get("lastUpdate"))
        _fresh(at, now, 30 * 3600, "NHC advisory")
        deadlines.append(at + 30 * 3600)
        nhc_times.append(at)
        try:
            lat, lon = float(item["latitudeNumeric"]), float(item["longitudeNumeric"])
            wind = float(item["intensity"]) if item.get("intensity") is not None else None
            name = item["name"].strip()
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            raise FeedError("Storm NHC active position is invalid") from None
        current = TrackPoint(at, lat, lon)
        history = parse_nhc_best(get(NHC_ATCF + "btk/b" + identity.lower() + ".dat").body,
                                 identity, at)
        if item.get("forecastTrack") is None:
            forecast_base, forecast, forecast_status = None, (), "not_issued"
        else:
            aid = get(NHC_ATCF + "aid_public/a" + identity.lower() + ".dat.gz")
            forecast_base, forecast = parse_nhc_forecast(aid.body, identity, at)
            forecast_status = "issued"
        storms.append(Storm(identity, name, "DEP" if name.upper().startswith("INVEST") else "STO",
                            current, wind, history, forecast_base, forecast, forecast_status))
    if nhc_times:
        source_times["nhc"] = min(nhc_times)
    else:
        source_times["nhc"] = _http_stamp(nhc_response.headers.get("date"))
    _fresh(source_times["nhc"], now, 30 * 3600, "NHC index")
    deadlines.append(source_times["nhc"] + 30 * 3600)
    warning_codes = set()
    formation_alerts = {}
    for product in discovered:
        if product.kind == "formation_alert":
            current, code = parse_jtwc_formation_alert(
                get(product.warning_url).body, product.identity,
                rss_times[product.group])
            if product.identity in formation_alerts or code in warning_codes:
                raise FeedError("Storm JTWC formation alerts repeat a storm")
            _fresh(current.at, now, 30 * 3600, "JTWC formation alert")
            formation_alerts[product.identity] = (current, code)
            deadlines.append(current.at + 30 * 3600)
            source_times[product.group] = min(source_times[product.group], current.at)
            continue
        if product.identity in formation_alerts:
            raise FeedError("Storm JTWC formation alert and warning repeat a storm")
        current, name, wind, forecast, warning_code = parse_jtwc_warning(
            get(product.warning_url).body, product.identity, rss_times[product.group])
        if warning_code in warning_codes:
            raise FeedError("Storm JTWC warnings repeat a storm code")
        warning_codes.add(warning_code)
        _fresh(current.at, now, 30 * 3600, "JTWC warning")
        deadlines.append(current.at + 30 * 3600)
        history = parse_jtwc_kmz(get(product.kmz_url).body, current, product.identity, name)
        storms.append(Storm(product.identity, name,
                            "DEP" if name.upper().startswith("INVEST") else "STO",
                            current, wind, history, current, forecast, "issued"))
        source_times[product.group] = min(source_times[product.group], current.at)
    advisory_codes = set()
    advisory_invests = []
    for kind, url in advisory_urls.items():
        advisory = parse_advisory(get(url, 256 * 1024).body, kind)
        _fresh_advisory(advisory, now, kind)
        deadlines.append(advisory.valid_until_at)
        for area in advisory.areas:
            source_times[area.group] = min(source_times[area.group], advisory.issue_at)
            for code in area.warned_codes:
                if code in advisory_codes:
                    raise FeedError("Storm JTWC advisories repeat a warning code")
                advisory_codes.add(code)
        advisory_invests.extend(advisory.invests)
    if advisory_codes != warning_codes:
        raise FeedError("Storm JTWC warnings disagree with significant advisories")
    for identity, (alert, code) in formation_alerts.items():
        matching = [invest for invest in advisory_invests if invest.id == identity]
        if len(matching) != 1 or matching[0].name != "Invest " + code:
            raise FeedError("Storm JTWC formation alert disagrees with significant advisories")
        current = matching[0].current
        # A newer advisory can update the observed fix; no position is inferred
        # between the alert and advisory. Same-time observations must agree.
        if (current.at < alert.at or
                (current.at == alert.at and
                 (current.lat, current.lon) != (alert.lat, alert.lon))):
            raise FeedError("Storm JTWC formation alert disagrees with significant advisories")
    storms.extend(advisory_invests)
    snapshot = StormSnapshot(tuple(storms), tuple(sorted(source_times.items())),
                             True, min(deadlines))
    return validate_snapshot(snapshot, required_groups=REQUIRED_GROUPS)
