"""USGS earthquake markers with last-good retention and data-change labels."""
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import time

from ..errors import DownloadError, FeedError, StorageError
from ..http import Fetcher, safe_header
from ..labels import quake_timestamp, refresh_all
from ..quake_geojson import parse_geojson, render_body, render_marker
from ..state import load_state, MarkerPublisher, recover_pending
from .clouds import modified_time


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    successful_at: float | None
    feed_generated_at: float | None
    latest_origin_at: float | None
    latest_revision_at: float | None
    count: int | None


def _source_key(fs, options):
    style = asdict(options)
    for name in ["journal", "interval", "timeout", "max_bytes", "warning"]:
        style.pop(name)
    style["marker"] = str(fs.resolve(options.marker, write=True).relative_to(fs.root))
    style["parser_version"] = 1
    return hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()


def run(fs, settings, *, fetcher=None, now=None):
    options = settings.quake
    with fs.lock(settings.lock):
        now = time.time() if now is None else now
        recover_pending(fs, settings)
        publisher = MarkerPublisher(fs, settings, "quake")
        state = load_state(fs, settings.state)
        record = state["products"].setdefault("quake", {})
        raw_label = fs.read(settings.labels, 2 * 1024 * 1024)
        try:
            old_label = raw_label.decode("utf-8") if raw_label is not None else ""
        except UnicodeError:
            raise StorageError("Existing labels are not valid UTF-8") from None
        if record.get("installed_at") is None and record.get("legacy_label_at") is None:
            legacy = quake_timestamp(old_label)
            if legacy is not None:
                record["legacy_label_at"] = legacy  # Existing row is unverified.
        record["checked_at"] = now
        existing = fs.read(options.marker, 32 * 1024 * 1024)
        existing_hash = hashlib.sha256(existing).hexdigest() if existing is not None else None
        valid_existing = (existing_hash is not None
                          and existing_hash == record.get("marker_sha256"))
        key = _source_key(fs, options)
        matching = valid_existing and record.get("source_key") == key
        elapsed = now - record.get("fetched_at", -1e20)
        cached = matching and 0 <= elapsed < options.interval
        outcome, message, marker = "unchanged", "Cached quake markers retained", None
        if not cached:
            before_attempt = copy.deepcopy(record)
            try:
                validators = {}
                if matching:
                    for key_name, header in [("etag", "If-None-Match"),
                                             ("last_modified", "If-Modified-Since")]:
                        value = record.get(key_name)
                        if value is not None:
                            if not safe_header(value):
                                raise StorageError("Invalid stored HTTP validator")
                            validators[header] = value
                response = (fetcher if fetcher is not None else Fetcher()).fetch(
                    options.url, validators=validators, credentials=None,
                    timeout=options.timeout, max_bytes=options.max_bytes)
                if response.status == 304:
                    if not matching:
                        raise DownloadError("Not-modified response lacks matching quake markers")
                    message = "Source reported no change"
                elif response.status == 200:
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type not in {"", "application/json", "application/geo+json",
                                            "application/octet-stream"}:
                        raise FeedError("Quake response has an unsupported content type")
                    events, generated_at = parse_geojson(response.body, options.minimum)
                    body = render_body(events, options)
                    body_hash = hashlib.sha256(body).hexdigest()
                    if not valid_existing or record.get("body_sha256") != body_hash:
                        marker = render_marker(body, now)
                        if len(marker) > 32 * 1024 * 1024:
                            raise FeedError("Quake marker output exceeds the size limit")
                        record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
                        record["body_sha256"] = body_hash
                        record["installed_at"] = now
                        outcome, message = "changed", "Changed valid quake markers published"
                    else:
                        message = "Identical quake markers retained"
                    record["count"] = len(events)
                    record["source_key"] = key
                    record["feed_generated_at"] = generated_at
                    record["latest_origin_at"] = max((e.origin_at for e in events), default=None)
                    record["latest_revision_at"] = max(
                        (e.revised_at for e in events if e.revised_at is not None), default=None)
                else:
                    raise DownloadError("Unexpected quake HTTP response")
                for key_name, header in [("etag", "etag"), ("last_modified", "last-modified")]:
                    value = response.headers.get(header)
                    if value is not None:
                        if not safe_header(value):
                            raise DownloadError("Source returned an invalid HTTP validator")
                        record[key_name] = value
                    elif response.status == 200:
                        record.pop(key_name, None)
                record["source_modified_at"] = modified_time(record.get("last_modified"))
                record["fetched_at"] = now
            except (DownloadError, FeedError) as error:
                outcome, message, marker = "failed", str(error), None
                record.clear()
                record.update(before_attempt)
        if outcome != "failed" and (marker is not None or valid_existing):
            record["successful_at"] = now
        record["last_outcome"] = outcome
        label = (refresh_all(old_label, state, settings, now,
                             append_product="quake" if marker is not None or valid_existing else None)
                 if settings.labels_enabled else None)
        if label == old_label:
            label = None
        publisher.publish(state, label, marker=marker)
        if settings.log:
            event = {"time": now, "feature": "quake", "outcome": outcome,
                     "message": message, "installed_at": record.get("installed_at"),
                     "successful_at": record.get("successful_at"),
                     "feed_generated_at": record.get("feed_generated_at"),
                     "latest_origin_at": record.get("latest_origin_at"),
                     "latest_revision_at": record.get("latest_revision_at"),
                     "count": record.get("count")}
            try:
                fs.append(settings.log, (json.dumps(event) + "\n").encode())
            except StorageError:
                message += "; diagnostic log unavailable"
        return Result(outcome, message, record.get("installed_at"),
                      record.get("successful_at"),
                      record.get("feed_generated_at"), record.get("latest_origin_at"),
                      record.get("latest_revision_at"), record.get("count"))
