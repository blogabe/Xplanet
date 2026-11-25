"""Validate saved snapshots from the retired Santa stub for recovery."""
from dataclasses import dataclass
import math
import re

from .errors import FeedError

TIMESTAMP_LIMIT = 32503680000
CLOCK_SKEW = 300


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


def validate_snapshot(snapshot):
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
    return snapshot


def snapshot_from_record(value):
    if not isinstance(value, dict) or set(value) != set(SantaSnapshot.__dataclass_fields__):
        raise FeedError("Saved Santa snapshot is invalid")
    return validate_snapshot(SantaSnapshot(**value))
