"""USGS GeoJSON earthquake selection and deterministic Xplanet marker rendering."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math

from .errors import FeedError
from .labels import legacy_time


@dataclass(frozen=True)
class Quake:
    id: str
    magnitude: float
    lat: float
    lon: float
    depth: float | None
    origin_at: float
    revised_at: float | None
    place: str
    kind: str


def _number(value, description, minimum, maximum, *, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FeedError(f"Quake {description} is invalid")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise FeedError(f"Quake {description} is outside its valid range") from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise FeedError(f"Quake {description} is outside its valid range")
    return result


def parse_geojson(raw, minimum):
    def invalid_constant(_value):
        raise ValueError

    try:
        document = json.loads(raw, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, TypeError):
        raise FeedError("Quake GeoJSON is malformed") from None
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise FeedError("Quake response is not a GeoJSON FeatureCollection")
    features, metadata = document.get("features"), document.get("metadata")
    if not isinstance(features, list) or not isinstance(metadata, dict):
        raise FeedError("Quake response lacks features or metadata")
    generated = _number(metadata.get("generated"), "feed generation time", 0,
                        32503680000000, nullable=True) / 1000 if metadata.get("generated") is not None else None
    count = metadata.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)
                              or count != len(features)):
        raise FeedError("Quake feed count does not match its features")
    events, seen = [], set()
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise FeedError("Quake feed contains an invalid feature")
        props = feature.get("properties")
        if not isinstance(props, dict):
            raise FeedError("Quake feature lacks properties")
        mag = _number(props.get("mag"), "magnitude", -20, 20, nullable=True)
        if mag is None or mag < minimum:
            continue
        ident = feature.get("id")
        geometry = feature.get("geometry")
        if not isinstance(ident, str) or not ident or len(ident) > 256 or ident in seen:
            raise FeedError("Selected quake lacks a unique identifier")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise FeedError("Selected quake lacks point geometry")
        coords = geometry.get("coordinates")
        if not isinstance(coords, list) or len(coords) < 2:
            raise FeedError("Selected quake has invalid coordinates")
        lon = _number(coords[0], "longitude", -180, 180)
        lat = _number(coords[1], "latitude", -90, 90)
        depth = (_number(coords[2], "depth", -1000, 1000, nullable=True)
                 if len(coords) > 2 else None)
        origin_ms = _number(props.get("time"), "origin time", 0, 32503680000000)
        revision_ms = _number(props.get("updated"), "revision time", 0,
                              32503680000000, nullable=True)
        place, kind = props.get("place"), props.get("type")
        if place is not None and not isinstance(place, str):
            raise FeedError("Selected quake has invalid place")
        if kind is not None and not isinstance(kind, str):
            raise FeedError("Selected quake has invalid type")
        seen.add(ident)
        events.append(Quake(ident, mag, lat, lon, depth, origin_ms / 1000,
                            revision_ms / 1000 if revision_ms is not None else None,
                            place or "", kind or "U"))
    events.sort(key=lambda event: (-event.origin_at, event.id))
    return events, generated


def _color(mag, selected, thresholds):
    if selected != "Multi":
        return selected
    for threshold, color in thresholds:
        if mag < threshold:
            return color
    return thresholds[-1][1]


def _quoted(value):
    value = "".join(" " if c in '\r\n' or ord(c) < 32 else c for c in value)
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _size(mag, options):
    standard = (mag * 20 + 4) * options.pixel_factor
    if options.pixel_max is not None and options.pixel_min is not None:
        value = options.pixel_min + (options.pixel_max - options.pixel_min) * mag / 10
    elif options.pixel_max is not None:
        value = options.pixel_max * mag / 10
    elif options.pixel_min is not None:
        value = options.pixel_min + standard
    else:
        value = standard
    return max(0, value)


def render_body(events, options):
    lines = []
    for event in events:
        coord = f"{event.lat: 7.2f} {event.lon: 7.2f}"
        mag = event.magnitude
        circle = _color(mag, options.circle_color, [
            (2.5, "SeaGreen"), (3.0, "PaleGreen"), (3.5, "Green"),
            (4.0, "ForestGreen"), (4.5, "Khaki"), (5.0, "LightGoldenrodYellow"),
            (5.5, "Yellow"), (6.0, "DarkGoldenrod"), (6.5, "Salmon"),
            (7.0, "Orange"), (7.5, "Tomato"), (8.0, "OrangeRed"),
            (8.5, "Red"), (10.0, "White"), (float("inf"), "Aquamarine")])
        if options.image:
            line = f'{coord} "" image={options.image} color={circle}'
            if options.image_transparent:
                line += f" transparent={options.image_transparent}"
        else:
            line = f'{coord} "" color={circle} symbolsize={_size(mag, options):g}'
        lines.append(line)
        if options.detail:
            origin = datetime.fromtimestamp(event.origin_at, timezone.utc)
            values = {
                "<date>": origin.strftime("%Y-%m-%d"),
                "<time>": origin.strftime("%H:%M:%S"),
                "<lat>": f"{event.lat: 7.2f}",
                "<long>": f"{event.lon: 7.2f}",
                "<depth>": f"{event.depth: 6.1f}" if event.depth is not None else "UNKNOWN",
                "<mag>": f"{mag:.1f}",
                "<quality>": event.kind[:2] or "U",
                "<location>": event.place,
            }
            detail = options.detail
            for token, value in values.items():
                detail = detail.replace(token, value)
            text_color = _color(mag, options.detail_color, [
                (4.5, options.detail_color_min),
                (6.5, options.detail_color_int),
                (8.5, options.detail_color_max),
                (float("inf"), "White")])
            lines.append(f"{coord} {_quoted(detail)} color={text_color} "
                         f"align={options.detail_align}")
    body = ("\n".join(lines) + "\n").encode("utf-8")
    if len(body) > 32 * 1024 * 1024:
        raise FeedError("Quake marker output exceeds the size limit")
    return body


def render_marker(body, installed_at):
    return (("# This Earthquake marker file created by TotalMarker Python\n"
             f"# Last Updated: {legacy_time(installed_at)}\n#\n").encode() + body)
