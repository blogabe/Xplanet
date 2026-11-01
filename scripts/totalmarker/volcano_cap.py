"""Strict CAP extraction and legacy Xplanet marker rendering for GVP weekly data."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
import re
import xml.etree.ElementTree as ET

from .errors import FeedError
from .labels import legacy_time

CAP_NAMESPACES = {"urn:oasis:names:tc:emergency:cap:1.1",
                  "urn:oasis:names:tc:emergency:cap:1.2", ""}
CIRCLE = re.compile(
    r"\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)"
    r"(?:\s*,\s*|\s+)([+-]?\d+(?:\.\d+)?)\s*"
)


MONTHS = {month.lower(): index for index, month in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"), 1)}
PERIOD = re.compile(r"(?i)(?<!\d)(\d{1,2})(?:\s+([A-Za-z]+))?(?:\s+(20\d{2}))?\s*[-–]\s*"
                    r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})(?!\d)")


def report_period(text):
    """Read one seven-day GVP period, including '24-30 September 2023'."""
    matches = list(PERIOD.finditer(text))
    if len(matches) != 1:
        raise FeedError("GVP weekly reporting period is missing or ambiguous")
    first_day, first_month, first_year, last_day, last_month, last_year = matches[0].groups()
    try:
        end_year = int(last_year)
        end_month = MONTHS[last_month.lower()]
        start_month = MONTHS[(first_month or last_month).lower()]
        start_year = int(first_year) if first_year else end_year - (start_month > end_month)
        start = date(start_year, start_month, int(first_day))
        end = date(end_year, end_month, int(last_day))
    except (ValueError, KeyError):
        raise FeedError("GVP weekly reporting period is invalid") from None
    if (end - start).days != 6:
        raise FeedError("GVP weekly reporting period is not seven days")
    return start, end


def coverage_end_at(period_end):
    # Coverage includes the entire final day in UTC, not the publication time.
    return datetime.combine(period_end + timedelta(days=1), datetime.min.time(),
                            timezone.utc).timestamp()


@dataclass(frozen=True)
class Volcano:
    name: str
    location: str
    lat: float
    lon: float
    elevation: str = "UNKNOWN"
    source_sent_at: float | None = None
    period_start: date | None = None
    period_end: date | None = None


def _parts(tag):
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return "", tag


def _children(node, name, namespace):
    return [child for child in node if _parts(child.tag) == (namespace, name)]


def _text(node):
    return " ".join((node.text or "").split()) if node is not None else ""


def _one_text(node, name, namespace):
    matches = _children(node, name, namespace)
    if len(matches) != 1:
        raise FeedError("Volcano CAP entry has missing or duplicate required fields")
    value = _text(matches[0])
    if not value:
        raise FeedError("Volcano CAP entry has an empty required field")
    return value


def _coordinates(circle):
    match = CIRCLE.fullmatch(circle)
    if not match:
        raise FeedError("Volcano CAP circle has invalid coordinates")
    lat, lon, radius = (float(value) for value in match.groups())
    if not all(map(math.isfinite, (lat, lon, radius))) or not (
            -90 <= lat <= 90 and -180 <= lon <= 180 and radius >= 0):
        raise FeedError("Volcano CAP circle is outside valid coordinate ranges")
    return lat, lon


class _NoDeclarations(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        # Parser callbacks also cover UTF-16 and other XML encodings; a raw
        # ASCII byte search alone cannot enforce the no-DTD contract.
        raise FeedError("Volcano CAP contains unsupported XML declarations")


def parse_cap(raw):
    """Require complete named entries; a malformed/zero-match feed is never empty success."""
    if not raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise FeedError("Volcano CAP response is empty or contains unsupported XML declarations")
    try:
        root = ET.fromstring(raw, parser=ET.XMLParser(target=_NoDeclarations()))
    except ET.ParseError:
        raise FeedError("Volcano CAP XML is malformed") from None
    alerts = [node for node in root.iter()
              if _parts(node.tag)[0] in CAP_NAMESPACES and _parts(node.tag)[1] == "alert"]
    if not alerts:
        raise FeedError("Volcano CAP response contains no alerts")
    events = []
    for alert in alerts:
        namespace, _ = _parts(alert.tag)
        sent = _children(alert, "sent", namespace)
        if len(sent) > 1:
            raise FeedError("Volcano CAP alert has duplicate sent times")
        source_sent_at = None
        if sent:
            try:
                stamp = datetime.fromisoformat(_text(sent[0]))
                if stamp.tzinfo is None:
                    raise ValueError
                source_sent_at = stamp.timestamp()
                if not 0 <= source_sent_at <= 32503680000:
                    raise ValueError
            except (ValueError, OverflowError):
                raise FeedError("Volcano CAP alert has an invalid sent time") from None
        infos = _children(alert, "info", namespace)
        if not infos:
            raise FeedError("Volcano CAP alert contains no information entries")
        for info in infos:
            start, end = report_period(_one_text(info, "headline", namespace))
            names = []
            for code in _children(info, "eventCode", namespace):
                labels = _children(code, "valueName", namespace)
                if len(labels) == 1 and _text(labels[0]).casefold() == "volcano name":
                    names.append(_one_text(code, "value", namespace))
            if len(names) != 1 or len(names[0]) > 256:
                raise FeedError("Volcano CAP entry lacks one valid volcano name")
            areas = _children(info, "area", namespace)
            positions = []
            for area in areas:
                circles = _children(area, "circle", namespace)
                if circles:
                    location = _one_text(area, "areaDesc", namespace)
                    if len(location) > 256:
                        raise FeedError("Volcano CAP area description is too long")
                    for circle in circles:
                        positions.append((location, *_coordinates(_text(circle))))
            if len(positions) != 1:
                raise FeedError("Volcano CAP entry requires exactly one area circle")
            location, lat, lon = positions[0]
            events.append(Volcano(names[0], location, lat, lon,
                                  source_sent_at=source_sent_at,
                                  period_start=start, period_end=end))
    if not events:
        raise FeedError("Volcano CAP response contains no named volcanoes")
    return events


def _quoted(text):
    text = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in text)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_body(events, options):
    """Three legacy concentric marker lines per entry, plus optional detail."""
    lines = []
    for event in events:
        coord = f"{event.lat: 7.2f} {event.lon: 7.2f}"
        for color, size in zip(options.circle_colors[:2], options.circle_sizes[:2]):
            lines.append(f'{coord} "" color={color} symbolsize={size}')
        outer_color = options.circle_colors[2]
        outer_size = options.circle_sizes[2]
        if options.name_enabled:
            if options.image:
                line = (f"{coord} {_quoted(event.name)} align={options.name_align} "
                        f"color={options.name_color} image={options.image}")
                if options.image_transparent:
                    line += f" transparent={options.image_transparent}"
            else:
                line = (f"{coord} {_quoted(event.name)} color={outer_color} "
                        f"symbolsize={outer_size} align={options.name_align}")
        else:
            line = f'{coord} "" color={outer_color} symbolsize={outer_size}'
        lines.append(line)
        if options.detail:
            values = {
                "<lat>": f"{event.lat: 7.2f}",
                "<long>": f"{event.lon: 7.2f}",
                "<elevation>": event.elevation,
                "<elev>": event.elevation,
                "<name>": event.name,
                "<location>": event.location,
            }
            detail = options.detail
            for token, value in values.items():
                detail = detail.replace(token, value)
            lines.append(f"{coord} {_quoted(detail)} color={options.detail_color} "
                         f"align={options.detail_align} image=none")
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_marker(body, installed_at):
    header = ("# This Volcano marker file created by TotalMarker Python\n"
              f"# Last Updated: {legacy_time(installed_at)}\n#\n")
    marker = header.encode("utf-8") + body
    if len(marker) > 32 * 1024 * 1024:
        raise FeedError("Volcano marker output exceeds the size limit")
    return marker
