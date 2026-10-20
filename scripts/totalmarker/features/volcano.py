"""Selectable GVP CAP or weekly HTML markers with last-good retention."""
import copy
from dataclasses import dataclass
from dataclasses import asdict
import hashlib
import json
import time

from ..errors import DownloadError, FeedError, StorageError
from ..http import Fetcher, safe_header
from ..labels import refresh_all, volcano_timestamp
from ..state import load_state, MarkerPublisher, recover_pending
from ..volcano_cap import parse_cap, render_body, render_marker
from ..volcano_weekly import (WEEKLY_URL, join_coordinates,
                              load_coordinate_catalogue, parse_weekly_html)
from .clouds import modified_time


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    successful_at: float | None
    source_report_at: float | None
    count: int | None
    coverage_end_at: float | None = None
    report_period_start: str | None = None
    report_period_end: str | None = None
    provider: str = "cap"


def _source_key(fs, options):
    style = asdict(options)
    for name in ["journal", "interval", "timeout", "max_bytes", "warning"]:
        style.pop(name)
    style["marker"] = str(fs.resolve(options.marker, write=True).relative_to(fs.root))
    style["parser_version"] = 2
    return hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()


def _validate_weekly_coverage(coverage_end_at, now):
    if (coverage_end_at is None or coverage_end_at > now + 3600
            or now - coverage_end_at > 14 * 86400):
        raise FeedError("GVP weekly reporting period is stale or future-dated")


def run(fs, settings, *, fetcher=None, now=None):
    now = time.time() if now is None else now
    options = settings.volcano
    with fs.lock(settings.lock):
        recover_pending(fs, settings)
        publisher = MarkerPublisher(fs, settings)
        state = load_state(fs, settings.state)
        record = state["products"].setdefault("volcano", {})
        raw_label = fs.read(settings.labels, 2 * 1024 * 1024)
        try:
            old_label = raw_label.decode("utf-8") if raw_label is not None else ""
        except UnicodeError:
            raise StorageError("Existing labels are not valid UTF-8") from None
        if record.get("installed_at") is None and record.get("legacy_label_at") is None:
            legacy = volcano_timestamp(old_label)
            if legacy is not None:
                record["legacy_label_at"] = legacy  # Unverified, never a source timestamp.
        record["checked_at"] = now
        existing = fs.read(options.marker, 32 * 1024 * 1024)
        existing_hash = hashlib.sha256(existing).hexdigest() if existing is not None else None
        valid_existing = (existing_hash is not None
                          and existing_hash == record.get("marker_sha256"))
        key = _source_key(fs, options)
        matching = valid_existing and record.get("source_key") == key
        elapsed = now - record.get("fetched_at", -1e20)
        cached = matching and 0 <= elapsed < options.interval
        outcome, message, marker = "unchanged", "Cached volcano markers retained", None
        if cached and options.provider == "weekly_html":
            try:
                _validate_weekly_coverage(record.get("coverage_end_at"), now)
            except FeedError as error:
                outcome, message = "failed", str(error)
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
                source_url = WEEKLY_URL if options.provider == "weekly_html" else options.url
                response = (fetcher if fetcher is not None else Fetcher()).fetch(
                    source_url, validators=validators, credentials=None,
                    timeout=options.timeout, max_bytes=options.max_bytes)
                if response.status == 304:
                    if not matching:
                        raise DownloadError("Not-modified response lacks matching volcano markers")
                    if options.provider == "weekly_html":
                        _validate_weekly_coverage(record.get("coverage_end_at"), now)
                    message = "Source reported no change"
                elif response.status == 200:
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    allowed = ({"", "text/html", "application/xhtml+xml", "application/octet-stream"}
                               if options.provider == "weekly_html" else
                               {"", "application/xml", "text/xml", "application/cap+xml",
                                "application/rss+xml", "application/atom+xml",
                                "application/octet-stream"})
                    if content_type not in allowed:
                        raise FeedError("Volcano response has an unsupported content type")
                    if options.provider == "weekly_html":
                        page = parse_weekly_html(response.body)
                        _validate_weekly_coverage(page.coverage_end_at, now)
                        events = join_coordinates(page, load_coordinate_catalogue())
                        record["coverage_end_at"] = page.coverage_end_at
                        record["report_period_start"] = page.period_start.isoformat()
                        record["report_period_end"] = page.period_end.isoformat()
                        record["source_report_at"] = None  # No publication time on this page.
                        period_note = ("; report covers " + page.period_start.isoformat() +
                                       " through " + page.period_end.isoformat() +
                                       " (publication time unavailable)")
                    else:
                        events = parse_cap(response.body)
                        period_note = ""
                        record["source_report_at"] = max(
                            (e.source_sent_at for e in events if e.source_sent_at is not None),
                            default=None)
                        for field in ["coverage_end_at", "report_period_start", "report_period_end"]:
                            record.pop(field, None)
                    body = render_body(events, options)
                    body_hash = hashlib.sha256(body).hexdigest()
                    if not valid_existing or record.get("body_sha256") != body_hash:
                        marker = render_marker(body, now)
                        record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
                        record["body_sha256"] = body_hash
                        record["installed_at"] = now
                        outcome, message = "changed", "Changed valid volcano markers published" + period_note
                    else:
                        message = "Identical volcano markers retained" + period_note
                    record["count"] = len(events)
                    record["source_key"] = key
                    record["provider"] = options.provider
                else:
                    raise DownloadError("Unexpected volcano HTTP response")
                for key_name, header in [("etag", "etag"), ("last_modified", "last-modified")]:
                    value = response.headers.get(header)
                    if value is not None:
                        if not safe_header(value):
                            raise DownloadError("Source returned an invalid HTTP validator")
                        record[key_name] = value
                    elif response.status == 200:
                        record.pop(key_name, None)
                record["source_modified_at"] = modified_time(record.get("last_modified"))
                record["fetched_at"] = now  # Last successful source verification.
            except (DownloadError, FeedError) as error:
                outcome, message, marker = "failed", str(error), None
                record.clear()
                record.update(before_attempt)
        if outcome != "failed" and (marker is not None or valid_existing):
            record["successful_at"] = now
        record["last_outcome"] = outcome
        label = (refresh_all(old_label, state, settings, now,
                             append_product="volcano" if marker is not None or valid_existing else None)
                 if settings.labels_enabled else None)
        if label == old_label:
            label = None
        publisher.publish(state, label, marker=marker)
        if settings.log:
            event = {"time": now, "feature": "volcano", "outcome": outcome,
                     "message": message, "installed_at": record.get("installed_at"),
                     "successful_at": record.get("successful_at"),
                     "source_report_at": record.get("source_report_at"),
                     "coverage_end_at": record.get("coverage_end_at"),
                     "report_period_start": record.get("report_period_start"),
                     "report_period_end": record.get("report_period_end"),
                     "provider": record.get("provider"),
                     "count": record.get("count")}
            try:
                fs.append(settings.log, (json.dumps(event) + "\n").encode())
            except StorageError:
                message += "; diagnostic log unavailable"
        return Result(outcome, message, record.get("installed_at"),
                      record.get("successful_at"),
                      record.get("source_report_at"), record.get("count"),
                      record.get("coverage_end_at"), record.get("report_period_start"),
                      record.get("report_period_end"), record.get("provider", options.provider))
