"""Bounded CelesTrak GP selections for Xplanet's satellite_file."""
import copy
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import time

from ..errors import DownloadError, FeedError, StorageError
from ..config import NoradStyle
from ..http import Fetcher
from ..labels import refresh_all
from ..state import PairPublisher, json_bytes, load_state, recover_pending, validate_state


CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?CATNR={id}&FORMAT=TLE"
CELESTRAK_GROUP = "https://celestrak.org/NORAD/elements/gp.php?GROUP={source}&FORMAT=JSON"


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    successful_at: float | None
    oldest_epoch_at: float | None
    count: int | None


def _checksum(line):
    return sum(int(ch) if ch.isdigit() else ch == "-" for ch in line[:68]) % 10


def parse_tle(raw, expected_id, now, max_age):
    """Accept a single 2LE/3LE, with checksums and a plausible UTC epoch."""
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError:
        raise FeedError("CelesTrak TLE is not ASCII") from None
    lines = [line.rstrip("\r") for line in lines if line.strip()]
    if len(lines) == 3 and not lines[0].startswith(("1 ", "2 ")):
        name, first, second = lines
        name = name.strip()
    elif len(lines) == 2:
        name, first, second = f"NORAD {expected_id}", *lines
    else:
        raise FeedError("CelesTrak returned an incomplete or multiple-object TLE")
    if not re.fullmatch(r"[A-Za-z0-9 ._()/+ -]{1,64}", name):
        name = f"NORAD {expected_id}"
    for number, line in (("1", first), ("2", second)):
        if (len(line) != 69 or not line.startswith(number + " ")
                or not line[2:7].strip().isdigit()
                or int(line[2:7]) != expected_id
                or not line[68].isdigit() or _checksum(line) != int(line[68])):
            raise FeedError("CelesTrak TLE line or checksum is invalid")
    if first[7] != "U" or not re.fullmatch(r"\d{2}\d{3}\.\d{8}", first[18:32]):
        raise FeedError("CelesTrak TLE identification or epoch is invalid")
    # A checksum only guards transcription; it does not establish valid orbital
    # elements. Check fixed TLE fields before Xplanet is asked to propagate them.
    if (not re.fullmatch(r"[ +\-]\.\d{8}", first[33:43])
            or not re.fullmatch(r"[ +\-]\d{5}[+\-]\d", first[44:52])
            or not re.fullmatch(r"[ +\-]\d{5}[+\-]\d", first[53:61])
            or not first[62].isdigit() or not first[64:68].strip().isdigit()
            or not re.fullmatch(r"\d{7}", second[26:33])):
        raise FeedError("CelesTrak TLE orbital fields are invalid")
    fields = []
    for raw_field, pattern in (
            (second[8:16], r"\s*\d{1,3}\.\d{4}"),
            (second[17:25], r"\s*\d{1,3}\.\d{4}"),
            (second[34:42], r"\s*\d{1,3}\.\d{4}"),
            (second[43:51], r"\s*\d{1,3}\.\d{4}"),
            (second[52:63], r"\s*\d{1,2}\.\d{8}")):
        if not re.fullmatch(pattern, raw_field):
            raise FeedError("CelesTrak TLE orbital fields are invalid")
        fields.append(float(raw_field))
    inclination, ascending_node, argument, anomaly, mean_motion = fields
    if (not 0 <= inclination <= 180 or not 0 <= ascending_node < 360
            or not 0 <= argument < 360 or not 0 <= anomaly < 360
            or not 0 < mean_motion <= 20):
        raise FeedError("CelesTrak TLE orbital fields are outside valid ranges")
    yy = int(first[18:20])
    year = 2000 + yy if yy < 57 else 1900 + yy
    day = float(first[20:32])
    if day < 1:
        raise FeedError("CelesTrak TLE day is outside the epoch year")
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    epoch = start + timedelta(days=day - 1)
    if epoch >= datetime(year + 1, 1, 1, tzinfo=timezone.utc):
        raise FeedError("CelesTrak TLE day is outside the epoch year")
    epoch_at = epoch.timestamp()
    if epoch_at > now + 24 * 3600 or now - epoch_at > max_age:
        raise FeedError("CelesTrak TLE epoch is outside the configured freshness window")
    return name, first, second, epoch_at


def _source_key(fs, options):
    style = asdict(options)
    for key in ("interval", "timeout", "max_bytes", "warning", "journal"):
        style.pop(key)
    style["satellite"] = str(fs.resolve(options.satellite, write=True).relative_to(fs.root))
    style["provider"] = "CelesTrak-GP-TLE-v1"
    return hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()


def _publisher(fs, settings):
    return PairPublisher(fs, settings, "norad", settings.norad.satellite,
                         settings.norad.satellite + ".tle", "satellite_sha256",
                         "tle_sha256")


def parse_group(raw):
    """Validate every discovery row before selecting any member."""
    try:
        rows = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise FeedError("CelesTrak group collection is invalid JSON") from None
    if not isinstance(rows, list) or not rows or len(rows) > 2000:
        raise FeedError("CelesTrak group collection is empty or oversized")
    members, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise FeedError("CelesTrak group collection has an incomplete row")
        name, catalog_id = row.get("OBJECT_NAME"), row.get("NORAD_CAT_ID")
        if (not isinstance(name, str) or not 1 <= len(name) <= 128 or
                any(ord(char) < 32 or ord(char) == 127 for char in name)):
            raise FeedError("CelesTrak group collection has an invalid object name")
        if isinstance(catalog_id, str) and re.fullmatch(r"[1-9][0-9]{0,8}", catalog_id):
            catalog_id = int(catalog_id)
        if (type(catalog_id) is not int or not 1 <= catalog_id <= 999999999
                or catalog_id in seen):
            raise FeedError("CelesTrak group collection has an incomplete or duplicate ID")
        seen.add(catalog_id)
        members.append((catalog_id, name))
    return members


def _style(base, override):
    return type(base)(**{field.name: (getattr(override, field.name)
                                     if getattr(override, field.name) is not None
                                     else getattr(base, field.name))
                         for field in fields(base)})


def _selections(client, options):
    profiles = {profile.catalog_id: profile.style for profile in options.profiles}
    selected, seen, collections = [], set(), {}
    skipped_unsupported = set()
    matched_group_member = False

    def add(catalog_id, group_style, name_contains=None):
        if catalog_id in seen:
            return
        seen.add(catalog_id)
        style = group_style
        if catalog_id in profiles:
            style = _style(style, profiles[catalog_id])
        if style.enabled is False:
            return
        selected.append((catalog_id, style, name_contains))
        if len(selected) > 16:
            raise FeedError("NORAD selection exceeds 16 Xplanet TLE objects")

    for catalog_id in options.catalog_ids:
        add(catalog_id, NoradStyle())
    for group in options.groups:
        if not group.enabled:
            continue
        if group.source not in collections:
            response = client.fetch(
                CELESTRAK_GROUP.format(source=group.source.upper()),
                timeout=options.timeout, max_bytes=options.group_max_bytes,
                allow_query=True)
            if response.status != 200:
                raise FeedError("CelesTrak group discovery failed")
            collections[group.source] = parse_group(response.body)
        for catalog_id, name in collections[group.source]:
            if group.name_contains in name.upper():
                matched_group_member = True
                if catalog_id > 99999:
                    skipped_unsupported.add(catalog_id)
                    continue
                add(catalog_id, group.style, group.name_contains)
    # An empty group result or one containing only unrepresentable matches is
    # a failed selection. Only explicitly disabled, representable matches are
    # an intentional empty selection that may clear the old pair.
    if not selected and skipped_unsupported:
        raise FeedError("NORAD selection has no representable TLE objects; "
                        + _unsupported_warning(skipped_unsupported))
    if (not selected and any(group.enabled for group in options.groups)
            and not matched_group_member):
        raise FeedError("NORAD selection contains no available TLE objects")
    return selected, sorted(skipped_unsupported)


def _unsupported_warning(catalog_ids):
    return ("Warning: skipped unsupported group catalog IDs "
            + ", ".join(map(str, sorted(catalog_ids)))
            + " (Xplanet TLE supports at most five digits)")


def _selector(fs, catalog_id, name, style, default_color):
    caption = name if style.caption is None else style.caption
    color = default_color if style.color is None else style.color
    trail = (-30, 30, 5) if style.trail is None else style.trail
    parts = [f'{catalog_id} "{caption}"', f"color={color}",
             f"trail={{orbit,{trail[0]},{trail[1]},{trail[2]}}}"]
    if style.icon:
        try:
            exists = fs.file_stat("images/" + style.icon) is not None
        except StorageError:
            exists = False
        if not exists:
            raise FeedError("Configured NORAD icon is missing or unsafe")
        parts.append("image=" + style.icon)
    if style.transparent is not None:
        parts.append("transparent={" + ",".join(map(str, style.transparent)) + "}")
    if style.altcirc is not None:
        parts.append("altcirc=" + str(style.altcirc))
    if style.align is not None:
        parts.append("align=" + style.align.lower())
    return " ".join(parts) + "\n"


def _icons_valid(fs, icons):
    if not isinstance(icons, list):
        return False
    try:
        return all(isinstance(icon, str) and re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.(?:png|gif|jpg|jpeg)",
            icon, re.IGNORECASE) and fs.file_stat("images/" + icon) is not None
                   for icon in icons)
    except StorageError:
        return False


def _cached_tles_valid(raw, options, now, recorded_oldest, selected_ids):
    """Recheck saved TLEs, including pairs written by older parser versions."""
    try:
        lines = raw.decode("ascii").splitlines()
        if (not isinstance(selected_ids, list) or not 0 <= len(selected_ids) <= 16
                or any(type(item) is not int or not 1 <= item <= 99999
                       for item in selected_ids)
                or len(set(selected_ids)) != len(selected_ids)
                or len(lines) != 3 * len(selected_ids)):
            return False
        if not selected_ids:
            return raw == b"" and recorded_oldest is None
        epochs = []
        for index, catalog_id in enumerate(selected_ids):
            body = ("\n".join(lines[3 * index:3 * index + 3]) + "\n").encode("ascii")
            _, _, _, epoch = parse_tle(body, catalog_id, now, options.max_age)
            epochs.append(epoch)
        return recorded_oldest is not None and min(epochs) == recorded_oldest
    except (FeedError, UnicodeError):
        return False


def run(fs, settings, *, fetcher=None, now=None):
    options = settings.norad
    if not options.enabled:
        return Result("disabled", "NORAD is disabled in configuration", None, None, None, None)
    with fs.lock(settings.lock):
        now = time.time() if now is None else now
        recover_pending(fs, settings)
        publisher = _publisher(fs, settings)
        state = load_state(fs, settings.state)
        record = state["products"].setdefault("norad", {})
        raw_label = fs.read(settings.labels, 2 * 1024 * 1024)
        try:
            old_label = raw_label.decode("utf-8") if raw_label is not None else ""
        except UnicodeError:
            raise StorageError("Existing labels are not valid UTF-8") from None
        record["checked_at"] = now
        existing_sat = fs.read(options.satellite, PairPublisher.LIMIT)
        existing_tle = fs.read(options.satellite + ".tle", PairPublisher.LIMIT)
        valid_existing = (
            existing_sat is not None and existing_tle is not None
            and hashlib.sha256(existing_sat).hexdigest() == record.get("satellite_sha256")
            and hashlib.sha256(existing_tle).hexdigest() == record.get("tle_sha256"))
        key = _source_key(fs, options)
        elapsed = now - record.get("fetched_at", -1e20)
        oldest = record.get("oldest_epoch_at")
        fresh_epoch = oldest is not None and -24 * 3600 <= now - oldest <= options.max_age
        selected_ids = record.get("selected_ids", list(options.catalog_ids)
                                  if not options.groups else None)
        deliberately_empty = (bool(options.catalog_ids)
                              and not any(group.enabled for group in options.groups)
                              and all(any(profile.catalog_id == catalog_id
                                          and profile.style.enabled is False
                                          for profile in options.profiles)
                                      for catalog_id in options.catalog_ids))
        if selected_ids == [] and record.get("count") == 0:
            fresh_epoch = True
        icons_valid = _icons_valid(fs, record.get("icons", []))
        tle_valid = (valid_existing and fresh_epoch and
                     _cached_tles_valid(existing_tle, options, now, oldest,
                                        selected_ids))
        cached = (valid_existing and record.get("source_key") == key
                  and icons_valid and tle_valid and 0 <= elapsed < options.interval)
        outcome, message, satellite, tle = "unchanged", "Cached NORAD TLEs retained", None, None
        deferred_refresh = False
        attempted_at = record.get("attempted_at", record.get("fetched_at"))
        if deliberately_empty:
            satellite_body, tle_body = b"", b""
            body_hash = hashlib.sha256(satellite_body + b"\0" + tle_body).hexdigest()
            if not valid_existing or record.get("body_sha256") != body_hash:
                satellite, tle = satellite_body, tle_body
                record["satellite_sha256"] = hashlib.sha256(satellite).hexdigest()
                record["tle_sha256"] = hashlib.sha256(tle).hexdigest()
                record["body_sha256"] = body_hash
                record["installed_at"] = now
                outcome, message = "changed", "Empty NORAD selection published"
            else:
                message = "Empty NORAD selection retained"
            record["source_key"] = key
            record["selected_ids"] = []
            record["skipped_unsupported_ids"] = []
            record["icons"] = []
            record["oldest_epoch_at"] = None
            record["count"] = 0
        elif not icons_valid and record.get("source_key") == key:
            deferred_refresh = True
            outcome, message = "failed", "Configured NORAD icon is missing or unsafe"
        elif (not cached and isinstance(attempted_at, (int, float))
                and 0 <= now - attempted_at < options.interval):
            deferred_refresh = True
            outcome = "unchanged" if tle_valid and icons_valid else "failed"
            message = "NORAD refresh waits for the two-hour provider interval"
        elif not cached:
            before = copy.deepcopy(record)
            record["attempted_at"] = now
            # Persist the attempt before contacting CelesTrak, so an interrupted
            # run cannot immediately repeat the same provider request.
            fs.write(settings.state, json_bytes(validate_state(copy.deepcopy(state))))
            try:
                client = fetcher if fetcher is not None else Fetcher()
                selectors, elements, epochs = [], [], []
                selection, skipped_unsupported = _selections(client, options)
                for catalog_id, style, name_contains in selection:
                    response = client.fetch(
                        CELESTRAK.format(id=catalog_id), timeout=options.timeout,
                        max_bytes=options.max_bytes, allow_query=True)
                    if response.status != 200:
                        raise FeedError("CelesTrak did not return a fresh TLE")
                    name, first, second, epoch_at = parse_tle(
                        response.body, catalog_id, now, options.max_age)
                    if name_contains is not None and name_contains not in name.upper():
                        raise FeedError("CelesTrak group membership changed during refresh")
                    selectors.append(_selector(fs, catalog_id, name, style, options.color))
                    elements.extend((name + "\n", first + "\n", second + "\n"))
                    epochs.append(epoch_at)
                satellite_body = "".join(selectors).encode("ascii")
                tle_body = "".join(elements).encode("ascii")
                body_hash = hashlib.sha256(satellite_body + b"\0" + tle_body).hexdigest()
                if not valid_existing or record.get("body_sha256") != body_hash:
                    satellite, tle = satellite_body, tle_body
                    if max(len(satellite), len(tle)) > PairPublisher.LIMIT:
                        raise FeedError("NORAD output exceeds the publication size limit")
                    record["satellite_sha256"] = hashlib.sha256(satellite).hexdigest()
                    record["tle_sha256"] = hashlib.sha256(tle).hexdigest()
                    record["body_sha256"] = body_hash
                    record["installed_at"] = now
                    outcome, message = "changed", "Validated NORAD satellite files published"
                else:
                    message = "Identical NORAD satellite files retained"
                record["source_key"] = key
                record["selected_ids"] = [catalog_id for catalog_id, _, _ in selection]
                record["skipped_unsupported_ids"] = skipped_unsupported
                record["icons"] = [style.icon for _, style, _ in selection if style.icon]
                record["fetched_at"] = now
                record["oldest_epoch_at"] = min(epochs) if epochs else None
                record["count"] = len(epochs)
            except (DownloadError, FeedError) as error:
                outcome, message, satellite, tle = "failed", str(error), None, None
                record.clear()
                record.update(before)
                record["attempted_at"] = now
        if (satellite is not None or valid_existing) and record.get("skipped_unsupported_ids"):
            warning = _unsupported_warning(record["skipped_unsupported_ids"])
            if warning not in message:
                message += "; " + warning + "; group coverage is partial"
        if not deferred_refresh and outcome != "failed" and (satellite is not None or valid_existing):
            record["successful_at"] = now
        record["last_outcome"] = outcome
        label = (refresh_all(old_label, state, settings, now,
                             append_product="norad" if satellite is not None or valid_existing else None)
                 if settings.labels_enabled else None)
        if label == old_label:
            label = None
        publisher.publish(state, label, first=satellite, second=tle)
        if settings.log:
            event = {"time": now, "feature": "norad", "outcome": outcome,
                     "message": message, "installed_at": record.get("installed_at"),
                     "successful_at": record.get("successful_at"),
                     "oldest_epoch_at": record.get("oldest_epoch_at"),
                     "count": record.get("count")}
            try:
                fs.append(settings.log, (json.dumps(event) + "\n").encode())
            except StorageError:
                message += "; diagnostic log unavailable"
        return Result(outcome, message, record.get("installed_at"),
                      record.get("successful_at"), record.get("oldest_epoch_at"),
                      record.get("count"))
