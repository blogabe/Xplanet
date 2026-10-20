"""Provider-neutral Santa snapshot validation and one-position marker rendering."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
import re

from .errors import FeedError

TIMESTAMP_LIMIT = 32503680000
CLOCK_SKEW = 300


class SeasonMismatch(FeedError):
    """A valid snapshot explicitly names a different Santa season."""


@dataclass(frozen=True)
class SantaSnapshot:
    provider_id: str
    season_year: int
    lifecycle: str
    latitude: float | None
    longitude: float | None
    source_at: float
    retrieved_at: float


def _number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FeedError("Santa " + label + " is invalid")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        raise FeedError("Santa " + label + " is outside its valid range") from None
    if not math.isfinite(number) or not low <= number <= high:
        raise FeedError("Santa " + label + " is outside its valid range")
    return number


def validate_snapshot(snapshot, *, now=None):
    if not isinstance(snapshot, SantaSnapshot):
        raise FeedError("Santa adapter did not return a snapshot")
    if (not isinstance(snapshot.provider_id, str) or not
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", snapshot.provider_id)):
        raise FeedError("Santa provider identity is invalid")
    if type(snapshot.season_year) is not int or not 2000 <= snapshot.season_year <= 3000:
        raise FeedError("Santa season is invalid")
    if (not isinstance(snapshot.lifecycle, str)
            or snapshot.lifecycle not in {"prelaunch", "tracking", "ended"}):
        raise FeedError("Santa lifecycle is invalid")
    source = _number(snapshot.source_at, "source time", 0, TIMESTAMP_LIMIT)
    retrieved = _number(snapshot.retrieved_at, "retrieval time", 0, TIMESTAMP_LIMIT)
    if source > retrieved + CLOCK_SKEW:
        raise FeedError("Santa source time is later than retrieval")
    if snapshot.lifecycle == "tracking":
        _number(snapshot.latitude, "latitude", -90, 90)
        _number(snapshot.longitude, "longitude", -180, 180)
    elif snapshot.latitude is not None or snapshot.longitude is not None:
        raise FeedError("Inactive Santa snapshot has a position")
    if now is not None:
        current = _number(now, "clock", 0, TIMESTAMP_LIMIT)
        if snapshot.season_year != datetime.fromtimestamp(current, timezone.utc).year:
            raise SeasonMismatch("Santa snapshot belongs to another season")
        if abs(retrieved - current) > CLOCK_SKEW or source > current + CLOCK_SKEW:
            raise FeedError("Santa snapshot times disagree with the current clock")
    return snapshot


def snapshot_from_record(value):
    if not isinstance(value, dict) or set(value) != set(SantaSnapshot.__dataclass_fields__):
        raise FeedError("Saved Santa snapshot is invalid")
    return validate_snapshot(SantaSnapshot(**value))


def snapshot_record(snapshot):
    return asdict(validate_snapshot(snapshot))


def season_active(now):
    current = _number(now, "clock", 0, TIMESTAMP_LIMIT)
    date = datetime.fromtimestamp(current, timezone.utc)
    return date.month == 12 and 23 <= date.day <= 25


def fresh(snapshot, now, freshness_seconds):
    validate_snapshot(snapshot)
    current = _number(now, "clock", 0, TIMESTAMP_LIMIT)
    return (snapshot.lifecycle == "tracking" and freshness_seconds > 0
            and -CLOCK_SKEW <= current - snapshot.source_at <= freshness_seconds)


def render_marker(snapshot, *, stale=False):
    """Render no route or icon dependency: one symbol and an honest UTC caption."""
    if snapshot is None:
        return b""
    validate_snapshot(snapshot)
    if snapshot.lifecycle != "tracking":
        return b""
    stamp = datetime.fromtimestamp(snapshot.source_at, timezone.utc).strftime("%Y-%m-%d %H:%M")
    caption = (f"Santa (stale; reported {stamp} UTC)" if stale
               else f"Santa (reported {stamp} UTC)")
    color = "Yellow" if stale else "Red"
    point = f"{snapshot.latitude:.4f} {snapshot.longitude:.4f}"
    return (f'# Santa position from {snapshot.provider_id} at {stamp} UTC\n'
            f'{point} "" color={color} symbolsize=6\n'
            f'{point} "{caption}" color={color} align=Above\n').encode("ascii")
