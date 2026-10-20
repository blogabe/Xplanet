"""Locked state and recoverable publication across product/state/label files."""
import copy
import base64
import binascii
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re

from .errors import FeedError, StorageError
from .santa_model import snapshot_from_record


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


STATE_LIMIT = 2 * 1024 * 1024
PAIR_JOURNAL_LIMIT = 4 * 1024 * 1024


def publication_bytes(intent, journal_limit):
    """Reject an intent before writing files that recovery cannot read."""
    if len(json_bytes(intent["state"])) > STATE_LIMIT:
        raise StorageError("Persistent state exceeds its size limit")
    label = intent["label"]
    if label is not None:
        if not isinstance(label, str) or len(label.encode("utf-8")) > STATE_LIMIT:
            raise StorageError("Label output exceeds its size limit")
    raw = json_bytes(intent)
    if len(raw) > journal_limit:
        raise StorageError("Publication journal exceeds its recovery size limit")
    return raw


def read_json(fs, path, limit=2 * 1024 * 1024):
    raw = fs.read(path, limit)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise StorageError("State or publication journal is invalid; preserve it for recovery") from None


def validate_state(value):
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(
            value.get("products"), dict):
        raise StorageError("Unsupported or invalid persistent state")
    record = value["products"].get("clouds", {})
    if not isinstance(record, dict):
        raise StorageError("Invalid cloud state")
    for key in ["installed_at", "checked_at", "fetched_at",
                "source_created_at", "source_modified_at", "legacy_label_at"]:
        number = record.get(key)
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))
                                   or not 0 <= number <= 32503680000 or not math.isfinite(number)):
            raise StorageError("Invalid state timestamp")
    for key in ["image_sha256", "source_key", "fetch_source_key",
                "source_image_sha256"]:
        digest = record.get(key)
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid state digest")
    volcano = value["products"].get("volcano", {})
    if not isinstance(volcano, dict):
        raise StorageError("Invalid volcano state")
    for key in ["installed_at", "successful_at", "checked_at", "fetched_at", "source_report_at",
                "source_modified_at", "legacy_label_at", "coverage_end_at"]:
        number = volcano.get(key)
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))
                                   or not 0 <= number <= 32503680000 or not math.isfinite(number)):
            raise StorageError("Invalid volcano state timestamp")
    for key in ["marker_sha256", "body_sha256", "source_key"]:
        digest = volcano.get(key)
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid volcano state digest")
    count = volcano.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)
                              or not 0 <= count <= 1_000_000):
        raise StorageError("Invalid volcano event count")
    provider = volcano.get("provider")
    if provider is not None and provider not in {"cap", "weekly_html"}:
        raise StorageError("Invalid volcano provider state")
    period_start, period_end = volcano.get("report_period_start"), volcano.get("report_period_end")
    if (period_start is None) != (period_end is None):
        raise StorageError("Incomplete volcano reporting period")
    if period_start is not None:
        try:
            if (not isinstance(period_start, str) or not isinstance(period_end, str)
                    or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", period_start)
                    or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", period_end)):
                raise ValueError
            start, end = date.fromisoformat(period_start), date.fromisoformat(period_end)
        except (TypeError, ValueError):
            raise StorageError("Invalid volcano reporting period") from None
        cutoff = datetime.combine(end + timedelta(days=1), datetime.min.time(),
                                  timezone.utc).timestamp()
        if (end - start).days != 6 or volcano.get("coverage_end_at") != cutoff:
            raise StorageError("Invalid volcano reporting period length or cutoff")
    quake = value["products"].get("quake", {})
    if not isinstance(quake, dict):
        raise StorageError("Invalid quake state")
    for key in ["installed_at", "successful_at", "checked_at", "fetched_at", "feed_generated_at",
                "latest_origin_at", "latest_revision_at", "source_modified_at",
                "legacy_label_at"]:
        number = quake.get(key)
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))
                                   or not 0 <= number <= 32503680000 or not math.isfinite(number)):
            raise StorageError("Invalid quake state timestamp")
    for key in ["marker_sha256", "body_sha256", "source_key"]:
        digest = quake.get(key)
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid quake state digest")
    count = quake.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)
                              or not 0 <= count <= 1_000_000):
        raise StorageError("Invalid quake event count")
    storm = value["products"].get("storm", {})
    if not isinstance(storm, dict):
        raise StorageError("Invalid storm state")
    for key in ["installed_at", "successful_at", "checked_at", "fetched_at", "source_at",
                "source_valid_until_at", "legacy_label_at"]:
        number = storm.get(key)
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))
                                   or not 0 <= number <= 32503680000 or not math.isfinite(number)):
            raise StorageError("Invalid storm state timestamp")
    for key in ["marker_sha256", "arc_sha256", "body_sha256", "source_key"]:
        digest = storm.get(key)
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid storm state digest")
    count = storm.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)
                              or not 0 <= count <= 1_000_000):
        raise StorageError("Invalid storm count")
    norad = value["products"].get("norad", {})
    if not isinstance(norad, dict):
        raise StorageError("Invalid NORAD state")
    for key in ("installed_at", "successful_at", "checked_at", "fetched_at",
                "attempted_at",
                "oldest_epoch_at"):
        number = norad.get(key)
        if number is not None and (isinstance(number, bool)
                or not isinstance(number, (int, float)) or not 0 <= number <= 32503680000
                or not math.isfinite(number)):
            raise StorageError("Invalid NORAD state timestamp")
    for key in ("satellite_sha256", "tle_sha256", "body_sha256", "source_key"):
        digest = norad.get(key)
        if digest is not None and (not isinstance(digest, str)
                or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid NORAD state digest")
    count = norad.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)
                              or not 0 <= count <= 16):
        raise StorageError("Invalid NORAD object count")
    selected_ids = norad.get("selected_ids")
    if selected_ids is not None and (
            not isinstance(selected_ids, list) or not 0 <= len(selected_ids) <= 16
            or any(type(item) is not int or not 1 <= item <= 99999
                   for item in selected_ids)
            or len(set(selected_ids)) != len(selected_ids)):
        raise StorageError("Invalid NORAD selected IDs")
    skipped_ids = norad.get("skipped_unsupported_ids")
    if skipped_ids is not None and (
            not isinstance(skipped_ids, list) or len(skipped_ids) > 8000
            or any(type(item) is not int or not 99999 < item <= 999999999
                   for item in skipped_ids)
            or skipped_ids != sorted(set(skipped_ids))):
        raise StorageError("Invalid NORAD skipped IDs")
    icons = norad.get("icons")
    if icons is not None and (not isinstance(icons, list) or len(icons) > 16
                             or any(not isinstance(icon, str) or not re.fullmatch(
                                 r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.(?:png|gif|jpg|jpeg)",
                                 icon, re.IGNORECASE) for icon in icons)):
        raise StorageError("Invalid NORAD icon list")
    eclipse = value["products"].get("eclipse", {})
    if not isinstance(eclipse, dict):
        raise StorageError("Invalid eclipse state")
    for key in ("installed_at", "successful_at", "checked_at", "fetched_at",
                "start_at", "end_at"):
        number = eclipse.get(key)
        if number is not None and (isinstance(number, bool)
                or not isinstance(number, (int, float)) or not 0 <= number <= 32503680000
                or not math.isfinite(number)):
            raise StorageError("Invalid eclipse state timestamp")
    for key in ("marker_sha256", "arc_sha256", "body_sha256", "source_key"):
        digest = eclipse.get(key)
        if digest is not None and (not isinstance(digest, str)
                or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid eclipse state digest")
    if eclipse.get("kind") is not None and eclipse["kind"] not in {"Total", "Annular", "Hybrid"}:
        raise StorageError("Invalid eclipse kind")
    event_date = eclipse.get("event_date")
    if event_date is not None:
        try:
            if (not isinstance(event_date, str)
                    or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", event_date)):
                raise ValueError
            date.fromisoformat(event_date)
        except ValueError:
            raise StorageError("Invalid eclipse event date") from None
    if eclipse.get("active") is not None and not isinstance(eclipse["active"], bool):
        raise StorageError("Invalid eclipse activation state")
    count = eclipse.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)
                              or not 0 <= count <= 1000):
        raise StorageError("Invalid eclipse path count")
    santa = value["products"].get("santa", {})
    if not isinstance(santa, dict):
        raise StorageError("Invalid Santa state")
    for key in ("installed_at", "successful_at", "checked_at", "fetched_at"):
        number = santa.get(key)
        if number is not None and (isinstance(number, bool)
                or not isinstance(number, (int, float)) or not 0 <= number <= 32503680000
                or not math.isfinite(number)):
            raise StorageError("Invalid Santa state timestamp")
    digest = santa.get("marker_sha256")
    if digest is not None and (not isinstance(digest, str)
            or not re.fullmatch("[0-9a-f]{64}", digest)):
        raise StorageError("Invalid Santa marker digest")
    if santa.get("stale") is not None and not isinstance(santa["stale"], bool):
        raise StorageError("Invalid Santa stale state")
    count = santa.get("count")
    if count is not None and (type(count) is not int or count not in {0, 1}):
        raise StorageError("Invalid Santa marker count")
    if santa.get("last_good") is not None:
        try:
            snapshot_from_record(santa["last_good"])
        except FeedError:
            raise StorageError("Invalid saved Santa snapshot") from None
    return value


def load_state(fs, path):
    value = read_json(fs, path)
    return {"schema": 1, "products": {}} if value is None else validate_state(value)


class Publisher:
    def __init__(self, fs, settings):
        self.fs, self.settings = fs, settings

    def paths(self):
        s = self.settings
        return {name: str(self.fs.resolve(getattr(s, name), write=True).relative_to(self.fs.root))
                for name in ["image", "state", "labels"]}

    def recover(self):
        intent = read_json(self.fs, self.settings.journal)
        if intent is None:
            return False
        if not isinstance(intent, dict) or intent.get("schema") != 1 or intent.get(
                "paths") != self.paths():
            raise StorageError("Pending publication paths differ; recover with the original configuration")
        next_state = validate_state(intent.get("state"))
        label = intent.get("label")
        if label is not None and not isinstance(label, str):
            raise StorageError("Invalid pending label output")
        publication_bytes(intent, STATE_LIMIT)
        digest = intent.get("digest")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid pending image digest")
        if digest is not None:
            image = self.fs.read(self.settings.image, self.settings.max_bytes)
            if image is None or hashlib.sha256(image).hexdigest() != digest:
                # Image was never installed. Old state/labels still belong to the old image.
                self.fs.unlink(self.settings.journal)
                return False
        self.fs.write(self.settings.state, json_bytes(next_state))
        if label is not None:
            self.fs.write(self.settings.labels, label.encode())
        self.fs.unlink(self.settings.journal)
        return True

    def publish(self, state, label, *, image=None, source_mtime=None):
        next_state = validate_state(copy.deepcopy(state))
        digest = hashlib.sha256(image).hexdigest() if image is not None else None
        paths = self.paths()
        intent = {"schema": 1, "paths": paths, "state": next_state,
                  "label": label, "digest": digest}
        state_bytes = json_bytes(next_state)
        self.fs.write(self.settings.journal, publication_bytes(intent, STATE_LIMIT))
        if image is not None:
            self.fs.write(paths["image"], image, mtime=source_mtime)
        self.fs.write(self.settings.state, state_bytes)
        if label is not None:
            self.fs.write(self.settings.labels, label.encode())
        self.fs.unlink(self.settings.journal)


class MarkerPublisher:
    """Product-specific marker journal under the shared lock."""

    def __init__(self, fs, settings, product="volcano"):
        if product not in {"volcano", "quake", "santa"}:
            raise StorageError("Unsupported marker product")
        self.fs, self.settings, self.product = fs, settings, product

    @property
    def options(self):
        return getattr(self.settings, self.product)

    def paths(self):
        s = self.settings
        return {
            "marker": str(self.fs.resolve(self.options.marker, write=True).relative_to(self.fs.root)),
            "state": str(self.fs.resolve(s.state, write=True).relative_to(self.fs.root)),
            "labels": str(self.fs.resolve(s.labels, write=True).relative_to(self.fs.root)),
        }

    def recover(self):
        intent = read_json(self.fs, self.options.journal)
        if intent is None:
            return False
        if not isinstance(intent, dict) or intent.get("schema") != 1 or intent.get("paths") != self.paths():
            raise StorageError("Pending marker paths differ; recover with the original configuration")
        next_state = validate_state(intent.get("state"))
        label = intent.get("label")
        if label is not None and not isinstance(label, str):
            raise StorageError("Invalid pending label output")
        publication_bytes(intent, STATE_LIMIT)
        digest = intent.get("digest")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise StorageError("Invalid pending marker digest")
        if digest is not None:
            marker = self.fs.read(self.options.marker, 32 * 1024 * 1024)
            if marker is None or hashlib.sha256(marker).hexdigest() != digest:
                self.fs.unlink(self.options.journal)
                return False
        self.fs.write(self.settings.state, json_bytes(next_state))
        if label is not None:
            self.fs.write(self.settings.labels, label.encode("utf-8"))
        self.fs.unlink(self.options.journal)
        return True

    def publish(self, state, label, *, marker=None):
        next_state = validate_state(copy.deepcopy(state))
        digest = hashlib.sha256(marker).hexdigest() if marker is not None else None
        paths = self.paths()
        intent = {"schema": 1, "paths": paths, "state": next_state,
                  "label": label, "digest": digest}
        state_bytes = json_bytes(next_state)
        self.fs.write(self.options.journal, publication_bytes(intent, STATE_LIMIT))
        if marker is not None:
            self.fs.write(paths["marker"], marker)
        self.fs.write(self.settings.state, state_bytes)
        if label is not None:
            self.fs.write(self.settings.labels, label.encode("utf-8"))
        self.fs.unlink(self.options.journal)


class StormPublisher:
    """Replay both storm files from one bounded journal before state and label."""

    LIMIT = 1024 * 1024

    def __init__(self, fs, settings):
        self.fs, self.settings = fs, settings

    def paths(self):
        return {
            "marker": str(self.fs.resolve(self.settings.storm.marker, write=True).relative_to(self.fs.root)),
            "arc": str(self.fs.resolve(self.settings.storm.arc, write=True).relative_to(self.fs.root)),
            "state": str(self.fs.resolve(self.settings.state, write=True).relative_to(self.fs.root)),
            "labels": str(self.fs.resolve(self.settings.labels, write=True).relative_to(self.fs.root)),
        }

    def _payload(self, raw):
        if raw is None:
            return None
        if len(raw) > self.LIMIT:
            raise StorageError("Storm output exceeds its publication size limit")
        return {"base64": base64.b64encode(raw).decode("ascii"),
                "sha256": hashlib.sha256(raw).hexdigest()}

    def _decode(self, item):
        if item is None:
            return None
        if not isinstance(item, dict) or set(item) != {"base64", "sha256"}:
            raise StorageError("Invalid pending storm output")
        try:
            raw = base64.b64decode(item["base64"], validate=True)
        except (ValueError, TypeError, binascii.Error):
            raise StorageError("Invalid pending storm output encoding") from None
        if len(raw) > self.LIMIT or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise StorageError("Pending storm output digest disagrees")
        return raw

    def recover(self):
        intent = read_json(self.fs, self.settings.storm.journal, 4 * 1024 * 1024)
        if intent is None:
            return False
        if (not isinstance(intent, dict) or intent.get("schema") != 1
                or intent.get("paths") != self.paths()):
            raise StorageError("Pending storm paths differ; recover with the original configuration")
        next_state = validate_state(intent.get("state"))
        label = intent.get("label")
        if label is not None and not isinstance(label, str):
            raise StorageError("Invalid pending storm label")
        publication_bytes(intent, PAIR_JOURNAL_LIMIT)
        marker, arc = self._decode(intent.get("marker")), self._decode(intent.get("arc"))
        if (marker is None) != (arc is None):
            raise StorageError("Pending storm marker and arc are incomplete")
        if marker is not None:
            record = next_state["products"].get("storm", {})
            if (record.get("marker_sha256") != hashlib.sha256(marker).hexdigest()
                    or record.get("arc_sha256") != hashlib.sha256(arc).hexdigest()):
                raise StorageError("Pending storm state digests disagree with outputs")
            self.fs.write(self.settings.storm.marker, marker)
            self.fs.write(self.settings.storm.arc, arc)
        self.fs.write(self.settings.state, json_bytes(next_state))
        if label is not None:
            self.fs.write(self.settings.labels, label.encode("utf-8"))
        self.fs.unlink(self.settings.storm.journal)
        return True

    def publish(self, state, label, *, marker=None, arc=None):
        if (marker is None) != (arc is None):
            raise StorageError("Storm marker and arc must publish together")
        intent = {"schema": 1, "paths": self.paths(),
                  "state": validate_state(copy.deepcopy(state)), "label": label,
                  "marker": self._payload(marker), "arc": self._payload(arc)}
        self.fs.write(self.settings.storm.journal,
                      publication_bytes(intent, PAIR_JOURNAL_LIMIT))
        return self.recover()


class PairPublisher:
    """Replay a bounded pair before shared state and labels under the common lock."""

    LIMIT = 1024 * 1024

    def __init__(self, fs, settings, product, first_path, second_path,
                 first_digest, second_digest):
        self.fs, self.settings, self.product = fs, settings, product
        self.first_path, self.second_path = first_path, second_path
        self.first_digest, self.second_digest = first_digest, second_digest
        self.journal = getattr(settings, product).journal

    def paths(self):
        return {
            "first": str(self.fs.resolve(self.first_path, write=True).relative_to(self.fs.root)),
            "second": str(self.fs.resolve(self.second_path, write=True).relative_to(self.fs.root)),
            "state": str(self.fs.resolve(self.settings.state, write=True).relative_to(self.fs.root)),
            "labels": str(self.fs.resolve(self.settings.labels, write=True).relative_to(self.fs.root)),
        }

    def _payload(self, raw):
        if raw is None:
            return None
        if len(raw) > self.LIMIT:
            raise StorageError("Paired output exceeds its publication size limit")
        return {"base64": base64.b64encode(raw).decode("ascii"),
                "sha256": hashlib.sha256(raw).hexdigest()}

    def _decode(self, item):
        if item is None:
            return None
        if not isinstance(item, dict) or set(item) != {"base64", "sha256"}:
            raise StorageError("Invalid pending paired output")
        try:
            raw = base64.b64decode(item["base64"], validate=True)
        except (ValueError, TypeError, binascii.Error):
            raise StorageError("Invalid pending paired output encoding") from None
        if (len(raw) > self.LIMIT
                or hashlib.sha256(raw).hexdigest() != item["sha256"]):
            raise StorageError("Pending paired output digest disagrees")
        return raw

    def recover(self):
        intent = read_json(self.fs, self.journal, 4 * 1024 * 1024)
        if intent is None:
            return False
        if (not isinstance(intent, dict) or intent.get("schema") != 1
                or intent.get("product") != self.product or intent.get("paths") != self.paths()):
            raise StorageError("Pending paired paths differ; recover with the original configuration")
        next_state = validate_state(intent.get("state"))
        label = intent.get("label")
        if label is not None and not isinstance(label, str):
            raise StorageError("Invalid pending paired label")
        publication_bytes(intent, PAIR_JOURNAL_LIMIT)
        first, second = self._decode(intent.get("first")), self._decode(intent.get("second"))
        if (first is None) != (second is None):
            raise StorageError("Pending paired outputs are incomplete")
        if first is not None:
            record = next_state["products"].get(self.product, {})
            if (record.get(self.first_digest) != hashlib.sha256(first).hexdigest()
                    or record.get(self.second_digest) != hashlib.sha256(second).hexdigest()):
                raise StorageError("Pending paired state digests disagree with outputs")
            self.fs.write(self.first_path, first)
            self.fs.write(self.second_path, second)
        self.fs.write(self.settings.state, json_bytes(next_state))
        if label is not None:
            self.fs.write(self.settings.labels, label.encode("utf-8"))
        self.fs.unlink(self.journal)
        return True

    def publish(self, state, label, *, first=None, second=None):
        if (first is None) != (second is None):
            raise StorageError("Paired outputs must publish together")
        intent = {"schema": 1, "product": self.product, "paths": self.paths(),
                  "state": validate_state(copy.deepcopy(state)), "label": label,
                  "first": self._payload(first), "second": self._payload(second)}
        self.fs.write(self.journal, publication_bytes(intent, PAIR_JOURNAL_LIMIT))
        return self.recover()


def recover_pending(fs, settings):
    """Resolve an interrupted publication before reading shared state."""
    cloud_pending = fs.read(settings.journal, 2 * 1024 * 1024) is not None
    volcano_pending = fs.read(settings.volcano.journal, 2 * 1024 * 1024) is not None
    quake_pending = fs.read(settings.quake.journal, 2 * 1024 * 1024) is not None
    storm_pending = fs.read(settings.storm.journal, 4 * 1024 * 1024) is not None
    norad_pending = fs.read(settings.norad.journal, 4 * 1024 * 1024) is not None
    eclipse_pending = fs.read(settings.eclipse.journal, 4 * 1024 * 1024) is not None
    santa_pending = fs.read(settings.santa.journal, 2 * 1024 * 1024) is not None
    if sum([cloud_pending, volcano_pending, quake_pending, storm_pending,
            norad_pending, eclipse_pending, santa_pending]) > 1:
        raise StorageError("Multiple pending product journals require explicit inspection")
    if cloud_pending:
        Publisher(fs, settings).recover()
    if volcano_pending:
        MarkerPublisher(fs, settings).recover()
    if quake_pending:
        MarkerPublisher(fs, settings, "quake").recover()
    if storm_pending:
        StormPublisher(fs, settings).recover()
    if norad_pending:
        PairPublisher(fs, settings, "norad", settings.norad.satellite,
                      settings.norad.satellite + ".tle", "satellite_sha256",
                      "tle_sha256").recover()
    if eclipse_pending:
        PairPublisher(fs, settings, "eclipse", settings.eclipse.marker,
                      settings.eclipse.arc, "marker_sha256",
                      "arc_sha256").recover()
    if santa_pending:
        MarkerPublisher(fs, settings, "santa").recover()
