"""Worldwide active storm markers and tracks with coherent last-good publication."""
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import time

from ..errors import DownloadError, FeedError, StorageError
from ..http import Fetcher
from ..labels import refresh_all, storm_timestamp
from ..state import load_state, recover_pending, StormPublisher
from ..storm_model import render_arc, render_bodies, render_marker
from ..storm_sources import collect_snapshot, REQUIRED_GROUPS


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    successful_at: float | None
    source_at: float | None
    count: int | None


def _source_key(fs, options):
    style = asdict(options)
    for name in ["journal", "interval", "timeout", "max_bytes", "warning"]:
        style.pop(name)
    for name in ["marker", "arc"]:
        style[name] = str(fs.resolve(getattr(options, name), write=True).relative_to(fs.root))
    # Revalidate cached snapshots against the KMZ storm identity rule.
    style["parser_version"] = 7
    style["sources"] = "NHC-ATCF+JTWC-RSS-warning-KMZ-ABPW-ABIO"
    return hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()


def run(fs, settings, *, fetcher=None, now=None):
    options = settings.storm
    with fs.lock(settings.lock):
        now = time.time() if now is None else now
        recover_pending(fs, settings)
        publisher = StormPublisher(fs, settings)
        state = load_state(fs, settings.state)
        record = state["products"].setdefault("storm", {})
        raw_label = fs.read(settings.labels, 2 * 1024 * 1024)
        try:
            old_label = raw_label.decode("utf-8") if raw_label is not None else ""
        except UnicodeError:
            raise StorageError("Existing labels are not valid UTF-8") from None
        if record.get("installed_at") is None and record.get("legacy_label_at") is None:
            legacy = storm_timestamp(old_label)
            if legacy is not None:
                record["legacy_label_at"] = legacy  # Existing row is unverified.
        record["checked_at"] = now
        existing_marker = fs.read(options.marker, StormPublisher.LIMIT)
        existing_arc = fs.read(options.arc, StormPublisher.LIMIT)
        valid_existing = (existing_marker is not None and existing_arc is not None
                          and hashlib.sha256(existing_marker).hexdigest() == record.get("marker_sha256")
                          and hashlib.sha256(existing_arc).hexdigest() == record.get("arc_sha256"))
        key = _source_key(fs, options)
        matching = valid_existing and record.get("source_key") == key
        elapsed = now - record.get("fetched_at", -1e20)
        deadline = record.get("source_valid_until_at")
        cached = (matching and 0 <= elapsed < options.interval
                  and deadline is not None and now <= deadline)
        outcome, message, marker, arc = "unchanged", "Cached storm tracks retained", None, None
        if not cached:
            before_attempt = copy.deepcopy(record)
            try:
                snapshot = collect_snapshot(
                    fetcher if fetcher is not None else Fetcher(), now=now,
                    timeout=options.timeout, max_bytes=options.max_bytes)
                marker_body, arc_body = render_bodies(
                    snapshot, options, required_groups=REQUIRED_GROUPS)
                body_hash = hashlib.sha256(marker_body + b"\0" + arc_body).hexdigest()
                if not valid_existing or record.get("body_sha256") != body_hash:
                    marker, arc = render_marker(marker_body, now), render_arc(arc_body, now)
                    if max(len(marker), len(arc)) > StormPublisher.LIMIT:
                        raise FeedError("Storm marker or arc output exceeds the size limit")
                    record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
                    record["arc_sha256"] = hashlib.sha256(arc).hexdigest()
                    record["body_sha256"] = body_hash
                    record["installed_at"] = now
                    outcome, message = "changed", "Changed valid worldwide storm tracks published"
                else:
                    message = "Identical storm markers and tracks retained"
                record["source_key"] = key
                record["fetched_at"] = now
                record["source_at"] = snapshot.oldest_source_at
                record["source_valid_until_at"] = snapshot.valid_until_at
                record["count"] = len(snapshot.storms)
            except (DownloadError, FeedError) as error:
                outcome, message, marker, arc = "failed", str(error), None, None
                record.clear()
                record.update(before_attempt)
        if outcome != "failed" and (marker is not None or valid_existing):
            record["successful_at"] = now
        record["last_outcome"] = outcome
        label = (refresh_all(old_label, state, settings, now,
                             append_product="storm" if marker is not None or valid_existing else None)
                 if settings.labels_enabled else None)
        if label == old_label:
            label = None
        publisher.publish(state, label, marker=marker, arc=arc)
        if settings.log:
            event = {"time": now, "feature": "storm", "outcome": outcome,
                     "message": message, "installed_at": record.get("installed_at"),
                     "successful_at": record.get("successful_at"),
                     "source_at": record.get("source_at"), "count": record.get("count")}
            try:
                fs.append(settings.log, (json.dumps(event) + "\n").encode())
            except StorageError:
                message += "; diagnostic log unavailable"
        return Result(outcome, message, record.get("installed_at"),
                      record.get("successful_at"),
                      record.get("source_at"), record.get("count"))
