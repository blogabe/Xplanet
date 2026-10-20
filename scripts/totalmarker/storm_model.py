"""Provider-neutral worldwide storm snapshot and legacy Xplanet rendering.

Adapters must prove their own basin coverage and distinguish missing products
from an explicit absence of active storms before constructing a snapshot.
"""
from dataclasses import dataclass
import math
import re

from .errors import FeedError
from .labels import legacy_time

IDENTITY = re.compile(r"^(?:AL|EP|CP|WP|NI|IO|SI|SP|SH|SA)[0-9]{2}(?:19|20)[0-9]{2}$")
TIMESTAMP_LIMIT = 32503680000


@dataclass(frozen=True)
class TrackPoint:
    at: float
    lat: float
    lon: float


@dataclass(frozen=True)
class ForecastPoint:
    lead_hours: int
    at: float
    lat: float
    lon: float


@dataclass(frozen=True)
class Storm:
    id: str
    name: str
    kind: str                 # STO or DEP, the visible legacy detail token.
    current: TrackPoint       # Observation/warning position, never bulletin fetch time.
    wind_kt: float | None
    history: tuple[TrackPoint, ...]
    forecast_base: TrackPoint | None
    forecast: tuple[ForecastPoint, ...]
    forecast_status: str      # issued or not_issued; fetch failures invalidate snapshot.


@dataclass(frozen=True)
class StormSnapshot:
    storms: tuple[Storm, ...]
    source_times: tuple[tuple[str, float], ...]  # One issue/observation time per coverage group.
    complete: bool                               # Set only after all required sources validate.
    valid_until_at: float | None = None           # Earliest checked source freshness deadline.

    @property
    def oldest_source_at(self):
        return min((stamp for _, stamp in self.source_times), default=None)


@dataclass(frozen=True)
class StormStyle:
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


def _number(value, label, low, high):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not low <= value <= high or not math.isfinite(value)):
        raise FeedError("Storm " + label + " is invalid")
    return float(value)


def _point(point):
    _number(point.at, "position time", 0, TIMESTAMP_LIMIT)
    _number(point.lat, "latitude", -90, 90)
    _number(point.lon, "longitude", -180, 180)


def validate_snapshot(snapshot, *, required_groups):
    """Reject incomplete global coverage, bad identities and ambiguous tracks."""
    if not isinstance(snapshot, StormSnapshot) or not snapshot.complete:
        raise FeedError("Storm source coverage is incomplete")
    if snapshot.valid_until_at is not None:
        _number(snapshot.valid_until_at, "validity deadline", 0, TIMESTAMP_LIMIT)
    groups = {}
    for group, stamp in snapshot.source_times:
        if not isinstance(group, str) or not group or group in groups:
            raise FeedError("Storm coverage group is missing or duplicated")
        groups[group] = _number(stamp, "source time", 0, TIMESTAMP_LIMIT)
    if not required_groups or not set(required_groups) <= groups.keys():
        raise FeedError("Storm source coverage lacks a required global region")
    identities = set()
    for storm in snapshot.storms:
        if not isinstance(storm, Storm):
            raise FeedError("Storm snapshot contains an invalid record")
        if not isinstance(storm.id, str) or not IDENTITY.fullmatch(storm.id.upper()):
            raise FeedError("Storm identifier is invalid")
        identity = storm.id.upper()
        if identity in identities:
            raise FeedError("Storm identifier is duplicated across sources")
        identities.add(identity)
        if (not isinstance(storm.name, str) or not storm.name or len(storm.name) > 64
                or any(ord(c) < 32 for c in storm.name)):
            raise FeedError("Storm name is invalid")
        if storm.kind not in {"STO", "DEP"}:
            raise FeedError("Storm type is invalid")
        _point(storm.current)
        if storm.wind_kt is not None:
            _number(storm.wind_kt, "wind speed", 0, 300)
        previous = None
        for point in sorted(storm.history, key=lambda item: item.at):
            _point(point)
            if point.at > storm.current.at or (previous is not None and point.at <= previous):
                raise FeedError("Storm observed track has invalid times")
            previous = point.at
        if storm.forecast_status not in {"issued", "not_issued"}:
            raise FeedError("Storm forecast status is invalid")
        if storm.forecast_status == "not_issued":
            if storm.forecast or storm.forecast_base is not None:
                raise FeedError("Storm without an issued forecast has forecast points")
        else:
            if not storm.forecast or storm.forecast_base is None:
                raise FeedError("Issued storm forecast lacks its base or track")
            _point(storm.forecast_base)
            previous_lead = 0
            for point in sorted(storm.forecast, key=lambda item: item.lead_hours):
                if (isinstance(point.lead_hours, bool)
                        or not isinstance(point.lead_hours, int)
                        or not previous_lead < point.lead_hours <= 240):
                    raise FeedError("Storm forecast lead time is invalid")
                _point(point)
                if abs(point.at - (storm.forecast_base.at + point.lead_hours * 3600)) > 3600:
                    raise FeedError("Storm forecast valid time disagrees with lead time")
                previous_lead = point.lead_hours
    return snapshot


def _quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _coord(point):
    return f"{point.lat: 7.2f} {point.lon: 7.2f}"


def render_bodies(snapshot, style, *, required_groups):
    """Render one marker and one great-arc body from the same validated snapshot."""
    validate_snapshot(snapshot, required_groups=required_groups)
    markers, arcs = [], []
    for storm in sorted(snapshot.storms, key=lambda value: value.id.upper()):
        coord = _coord(storm.current)
        image = f" image={style.image}" if style.image else ""
        if style.image_transparent and style.image:
            image += f" transparent={style.image_transparent}"
        if style.name_enabled:
            markers.append(f"{coord} {_quote(storm.name)} align={style.name_align} "
                           f"color={style.name_color}{image}")
        if style.detail:
            substitutions = {
                "<lat>": f"{storm.current.lat: 7.2f}",
                "<long>": f"{storm.current.lon: 7.2f}",
                "<type>": storm.kind,
                "<name>": storm.name,
                "<speed>": f"{storm.wind_kt: 3.0f}" if storm.wind_kt is not None else "UNKNOWN",
            }
            detail = style.detail
            for token, value in substitutions.items():
                detail = detail.replace(token, value)
            markers.append(f"{coord} {_quote(detail)} align={style.detail_align} "
                           f"color={style.detail_color}{image}")
        if not style.track_enabled:
            continue
        observed = sorted(storm.history, key=lambda value: value.at)
        if not observed or observed[-1] != storm.current:
            observed.append(storm.current)
        for start, end in zip(observed, observed[1:]):
            if start.lat != end.lat or start.lon != end.lon:
                arcs.append(f"{_coord(start)} {_coord(end)} color={style.track_real_color}")
        if storm.forecast_status == "issued":
            forecast = sorted(storm.forecast, key=lambda value: value.lead_hours)
            future = [storm.forecast_base, *forecast]
            for start, end in zip(future, future[1:]):
                if start.lat != end.lat or start.lon != end.lon:
                    arcs.append(f"{_coord(start)} {_coord(end)} "
                                f"color={style.track_forecast_color}")
    return (("\n".join(markers) + "\n").encode("utf-8"),
            ("\n".join(arcs) + "\n").encode("utf-8"))


def render_marker(body, installed_at):
    return (("# This Storm marker file created by TotalMarker Python\n"
             f"# Last Updated: {legacy_time(installed_at)}\n#\n").encode() + body)


def render_arc(body, installed_at):
    return (("# This Storm great-arc file created by TotalMarker Python\n"
             f"# Last Updated: {legacy_time(installed_at)}\n#\n").encode() + body)
