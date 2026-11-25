"""Bridge CelesTrak OMM JSON to a legacy renderer's Alpha-5 TLE interface."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException
import json
import re

from ..errors import FeedError


ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"
ALPHA5_MAX = 339999


def catalog_field(catalog_id):
    if 1 <= catalog_id <= 99999:
        return f"{catalog_id:05d}"
    if 100000 <= catalog_id <= ALPHA5_MAX:
        prefix, suffix = divmod(catalog_id, 10000)
        return ALPHA5[prefix - 10] + f"{suffix:04d}"
    raise ValueError("Catalog ID does not fit Alpha-5")


def checksum(line):
    return sum(int(ch) if ch.isdigit() else ch == "-" for ch in line[:68]) % 10


def _implied_decimal(value):
    if not value:
        return " 00000-0"
    mantissa = abs(value)
    exponent = mantissa.adjusted() + 1
    if not -9 <= exponent <= 9:
        raise ValueError
    digits = int(mantissa.scaleb(5 - exponent).to_integral_value())
    if digits == 100000:
        digits, exponent = 10000, exponent + 1
    if exponent > 9:
        raise ValueError
    return f"{'-' if value < 0 else ' '}{digits:05d}{exponent:+d}"


def _tle_epoch(text):
    # CelesTrak supplies UTC as an ISO date-time without an offset.
    if not isinstance(text, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z?", text):
        raise ValueError
    epoch = datetime.fromisoformat(text.rstrip("Z")).replace(tzinfo=timezone.utc)
    if not 1957 <= epoch.year <= 2056:
        raise ValueError
    start = datetime(epoch.year, 1, 1, tzinfo=timezone.utc)
    delta = epoch - start
    fraction = Decimal(delta.seconds * 1000000 + delta.microseconds) / 86400000000
    day = (delta.days + 1 + fraction).quantize(Decimal("0.00000001"))
    if day >= (datetime(epoch.year + 1, 1, 1, tzinfo=timezone.utc) - start).days + 1:
        epoch, day = epoch + timedelta(days=1), Decimal(1)
        if epoch.year > 2056:
            raise ValueError
    return f"{epoch.year % 100:02d}{day:012.8f}"


def omm_to_tle(raw, expected_id):
    """Convert one identified SGP4 record; the caller validates the resulting TLE."""
    try:
        rows = json.loads(raw, parse_float=Decimal)
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError
        row = rows[0]
        if type(row.get("NORAD_CAT_ID")) is not int or row["NORAD_CAT_ID"] != expected_id:
            raise ValueError
        for key, expected in (
                ("CENTER_NAME", "EARTH"), ("REF_FRAME", "TEME"), ("TIME_SYSTEM", "UTC"),
                ("MEAN_ELEMENT_THEORY", "SGP4"), ("CLASSIFICATION_TYPE", "U")):
            if row.get(key, expected) != expected:
                raise ValueError
        if type(row.get("EPHEMERIS_TYPE")) is not int or row["EPHEMERIS_TYPE"] != 0:
            raise ValueError

        def number(key, low, high, *, exclusive=False):
            value = row[key]
            if type(value) not in {int, Decimal}:
                raise ValueError
            value = Decimal(value)
            if not value.is_finite() or not low <= value <= high or (exclusive and value == high):
                raise ValueError
            return value

        name = row.get("OBJECT_NAME")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9 ._()/+ -]{1,64}", name.strip()):
            name = f"NORAD {expected_id}"
        name = name.strip()
        designator = row.get("OBJECT_ID") or ""
        if designator and (not isinstance(designator, str)
                           or not re.fullmatch(r"[0-9]{4}-[0-9]{3}[A-Z]{0,3}", designator)):
            raise ValueError
        id_field = catalog_field(expected_id)
        intl = (designator[2:4] + designator[5:]) if designator else ""
        epoch = _tle_epoch(row["EPOCH"])
        derivative = number("MEAN_MOTION_DOT", Decimal("-0.99999999"), Decimal("0.99999999"))
        derivative_text = ("-" if derivative < 0 else " ") + f"{abs(derivative):.8f}"[1:]
        second_dot = _implied_decimal(number("MEAN_MOTION_DDOT", -1, 1))
        bstar = _implied_decimal(number("BSTAR", -10, 10))
        element = row["ELEMENT_SET_NO"]
        rev = row["REV_AT_EPOCH"]
        if type(element) is not int or type(rev) is not int or not 0 <= element <= 999999999 or not 0 <= rev <= 999999999:
            raise ValueError

        def angle(key):
            return f"{number(key, 0, 360, exclusive=True).quantize(Decimal('0.0001')) % 360:8.4f}"

        inclination = number("INCLINATION", 0, 180)
        eccentricity = int(number("ECCENTRICITY", 0, 1, exclusive=True).scaleb(7).to_integral_value())
        if eccentricity > 9999999:
            raise ValueError
        motion = number("MEAN_MOTION", 0, 20)
        first = (f"1 {id_field}U {intl:8} {epoch} {derivative_text} {second_dot} "
                 f"{bstar} 0 {element % 10000:4d}")
        second = (f"2 {id_field} {inclination:8.4f} {angle('RA_OF_ASC_NODE')} {eccentricity:07d} "
                  f"{angle('ARG_OF_PERICENTER')} {angle('MEAN_ANOMALY')} {motion:11.8f}{rev % 100000:5d}")
        if len(first) != 68 or len(second) != 68:
            raise ValueError
        return f"{name}\n{first}{checksum(first)}\n{second}{checksum(second)}\n".encode("ascii")
    except (ValueError, KeyError, DecimalException, RecursionError):
        raise FeedError("CelesTrak OMM record has invalid identity or orbital fields") from None
