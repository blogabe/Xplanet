"""Cloud download contract and shared-label integration; no internal scheduler."""
from dataclasses import dataclass
import copy
from email.utils import parsedate_to_datetime
import hashlib
import json
import time

from ..errors import DownloadError, ImageError, StorageError
from ..http import Fetcher, safe_header
from ..image import cloud_creation_time, validate_jpeg
from ..labels import cloud_timestamp, refresh_all
from ..state import load_state, Publisher, recover_pending


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    source_created_at: float | None


def modified_time(value):
    if not safe_header(value):
        return None
    try:
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None
        result = stamp.timestamp()
        return result if 0 <= result <= 32503680000 else None
    except (ValueError, TypeError, OverflowError):
        return None

def record_creation_time(record, image, digest, now):
    # Re-read the current image as well as new responses. This binds the
    # displayed time to the bytes on disk and migrates old download-time state
    # without trusting a prior label, local mtime or HTTP Last-Modified.
    created = cloud_creation_time(image) if image is not None else None
    if created is not None and not 0 <= created <= now:
        created = None
    record["source_created_at"] = created
    record["source_time_origin"] = (
        "jpeg-earthdesk-comment" if created is not None else "unavailable")
    record["source_image_sha256"] = digest


def run(fs, settings, *, label_only=False, fetcher=None, now=None, environment=None):
    with fs.lock(settings.lock):
        now = time.time() if now is None else now
        publisher = Publisher(fs, settings)
        recover_pending(fs, settings)
        state = load_state(fs, settings.state)
        record = state["products"].setdefault("clouds", {})
        raw_label = fs.read(settings.labels, 2 * 1024 * 1024)
        try:
            old_label = raw_label.decode("utf-8") if raw_label is not None else ""
        except UnicodeError:
            raise StorageError("Existing labels are not valid UTF-8") from None
        # Previous releases sometimes put a label-derived estimate in this
        # local-install field. Retain it as unverified history, never as source
        # creation or as a confirmed publication time.
        if record.get("timestamp_origin") == "legacy-label":
            old_estimate = record.pop("installed_at", None)
            if old_estimate is not None:
                record.setdefault("legacy_label_at", old_estimate)
            record.pop("timestamp_origin", None)
        elif "installed_at" not in record:
            old_estimate = cloud_timestamp(old_label)
            if old_estimate is not None:
                record.setdefault("legacy_label_at", old_estimate)
        record["checked_at"] = now
        existing = fs.read(settings.image, settings.max_bytes)
        valid_existing = False
        if existing is not None:
            try:
                validate_jpeg(existing, settings.resolution)
                valid_existing = True
            except ImageError:
                pass
        existing_hash = hashlib.sha256(existing).hexdigest() if valid_existing else None
        record_creation_time(record, existing if valid_existing else None,
                             existing_hash, now)
        new_image = None
        source_mtime = None
        outcome, message = "unchanged", "Labels aged without fetching"
        if not label_only:
            # Source identity includes request semantics and both configured
            # and resolved destinations. Old URL-only keys force one fresh fetch.
            identity = [settings.provider, settings.resolution, settings.url,
                        str(settings.image),
                        str(fs.resolve(settings.image, write=True).relative_to(fs.root))]
            source_key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            matching = (valid_existing and record.get("source_key") == source_key
                        and record.get("fetch_source_key") == source_key
                        and record.get("image_sha256") == existing_hash)
            elapsed = now - record.get("fetched_at", -1e20)
            cached = matching and 0 <= elapsed < settings.interval
            if cached:
                message = "Cached image retained"
            else:
                record["fetched_at"] = now
                record["fetch_source_key"] = source_key
                validators = {}
                if matching:
                    for key, header in [("etag", "If-None-Match"),
                                        ("last_modified", "If-Modified-Since")]:
                        value = record.get(key)
                        if value is not None:
                            if not safe_header(value):
                                raise StorageError("Invalid stored HTTP validator")
                            validators[header] = value
                previous_record = copy.deepcopy(record)
                try:
                    credentials = settings.auth.resolve(environment)
                    response = (fetcher if fetcher is not None else Fetcher()).fetch(
                        settings.url, validators=validators, credentials=credentials,
                        timeout=settings.timeout, max_bytes=settings.max_bytes)
                    if response.status == 304:
                        if not matching:
                            raise DownloadError("Not-modified response lacks a matching valid local image")
                        message = "Server reported no change"
                    else:
                        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                        if content_type not in {"", "image/jpeg", "image/pjpeg", "application/octet-stream"}:
                            raise ImageError("Cloud response has an unsupported content type")
                        validate_jpeg(response.body, settings.resolution)
                        digest = hashlib.sha256(response.body).hexdigest()
                        if not valid_existing or digest != existing_hash:
                            new_image = response.body
                            record["installed_at"] = now
                            record["timestamp_origin"] = "installed"
                            outcome, message = "changed", "Changed valid image published"
                        else:
                            message = "Identical image retained"
                        record_creation_time(record, response.body, digest, now)
                        record["image_sha256"] = digest
                        record["source_key"] = source_key
                    for key, header in [("etag", "etag"), ("last_modified", "last-modified")]:
                        value = response.headers.get(header)
                        if value is not None:
                            if not safe_header(value):
                                raise DownloadError("Server returned an invalid HTTP validator")
                            record[key] = value
                        elif response.status == 200:
                            record.pop(key, None)
                    source_mtime = modified_time(record.get("last_modified"))
                    record["source_modified_at"] = source_mtime
                except (DownloadError, ImageError) as error:
                    outcome, message = "failed", str(error)
                    new_image = None
                    # Never import an attempt time as a successful installed time.
                    record.clear()
                    record.update(previous_record)
        record["last_outcome"] = outcome
        label = (refresh_all(old_label, state, settings, now, append_product="clouds")
                 if settings.labels_enabled else None)
        publisher.publish(state, label, image=new_image, source_mtime=source_mtime)
        if settings.log:
            # Fixed local messages only: never URLs, response bodies, auth or exception repr.
            event = {"time": now, "feature": "clouds", "outcome": outcome,
                     "message": message, "installed_at": record.get("installed_at"),
                     "source_created_at": record.get("source_created_at")}
            try:
                fs.append(settings.log, (json.dumps(event) + "\n").encode())
            except StorageError:
                message += "; diagnostic log unavailable"
        return Result(outcome, message, record.get("installed_at"),
                      record.get("source_created_at"))
