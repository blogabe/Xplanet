"""Worldwide active storm markers and tracks with coherent last-good publication."""
import base64
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time

from ..diagnostics import Attempt, finish
from ..errors import DownloadError, FeedError, StorageError
from ..http import Fetcher
from ..labels import refresh_all, storm_timestamp
from ..state import load_state, recover_pending, StormPublisher
from ..storm_model import render_arc, render_bodies, render_marker
from ..storm_sources import collect_snapshot, REQUIRED_GROUPS, NHC_INDEX, NHC_ATCF, JTWC_RSS


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    successful_at: float | None
    source_at: float | None
    count: int | None


# Latest rejection only: bounded public response evidence, never headers/auth.
REJECT_CAPTURE = ".state/totalmarker/storm-rejected.json"
CAPTURE_BODY_LIMIT = 64 * 1024
CAPTURE_TOTAL_LIMIT = 256 * 1024
CAPTURE_RESPONSE_LIMIT = 32


class _SourceCapture:
    def __init__(self, client):
        self.client, self.responses = client, []
        self.remaining, self.omitted = CAPTURE_TOTAL_LIMIT, 0
        self.other_responses = 0
        # Reserve space for both significant advisories fetched after large
        # tracks. Their rejected text is usually the most useful evidence.
        self.other_remaining = CAPTURE_TOTAL_LIMIT - 2 * CAPTURE_BODY_LIMIT

    def fetch(self, url, **kwargs):
        response = self.client.fetch(url, **kwargs)
        # Only source URLs constructed by the storm adapter may contribute
        # bytes. Store a public source identifier, never arbitrary URLs.
        source = {NHC_INDEX: "nhc/CurrentStorms.json", JTWC_RSS: "jtwc/rss"}.get(url)
        if source is None and url.startswith(NHC_ATCF):
            path = url[len(NHC_ATCF):]
            if re.fullmatch(r"(?:btk/b(?:al|ep|cp)[0-9]{6}\.dat|aid_public/a(?:al|ep|cp)[0-9]{6}\.dat\.gz)", path):
                source = "nhc/" + path
        prefix = "https://www.metoc.navy.mil/jtwc/products/"
        if source is None and url.startswith(prefix):
            path = url[len(prefix):]
            if re.fullmatch(r"(?:(?:abpw|abio)web\.txt|(?:wp|io|sh)[0-9]{4}web\.txt|(?:wp|io|sh)[0-9]{4}\.kmz)", path):
                source = "jtwc/" + path
        advisory = source in ("jtwc/abpwweb.txt", "jtwc/abioweb.txt")
        if (source is None or len(self.responses) >= CAPTURE_RESPONSE_LIMIT or
                (not advisory and self.other_responses >= CAPTURE_RESPONSE_LIMIT - 2)):
            self.omitted += 1
            return response
        body = response.body
        budget = self.remaining if advisory else min(self.remaining, self.other_remaining)
        saved = body[:min(CAPTURE_BODY_LIMIT, budget)]
        self.remaining -= len(saved)
        if not advisory:
            self.other_remaining -= len(saved)
            self.other_responses += 1
        self.responses.append({"source": source, "status": response.status,
                               "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                               "captured_bytes": len(saved), "truncated": len(saved) != len(body),
                               "body_base64": base64.b64encode(saved).decode("ascii")})
        return response

    def save(self, fs, settings, now):
        try:
            target = fs.root / REJECT_CAPTURE
            # Refuse pre-existing aliases, even contained ones. RootFS also
            # rejects escaping paths and symlink races during atomic writes.
            if fs.resolve(REJECT_CAPTURE, write=True) != target:
                return
            paths = [getattr(settings, key) for key in
                     ("image", "labels", "state", "journal", "lock", "log")]
            for options in (settings.quake, settings.storm, settings.volcano,
                            settings.norad, settings.eclipse, settings.santa):
                paths.extend(getattr(options, key) for key in
                             ("marker", "arc", "satellite", "journal") if hasattr(options, key))
            paths.append(settings.norad.satellite + ".tle")
            folded_target = tuple(part.casefold() for part in target.parts)
            for path in paths:
                if not path:
                    continue
                folded = tuple(part.casefold() for part in fs.resolve(path, write=True).parts)
                # Protect configured files and parent/child aliases too.
                n = min(len(folded), len(folded_target))
                if folded[:n] == folded_target[:n]:
                    return
            payload = {"schema": 1, "at": now, "responses": self.responses,
                       "omitted_responses": self.omitted,
                       "body_limit": CAPTURE_BODY_LIMIT, "total_body_limit": CAPTURE_TOTAL_LIMIT}
            encoded = (json.dumps(payload, sort_keys=True) + "\n").encode()
            if len(encoded) <= 384 * 1024:
                fs.write(REJECT_CAPTURE, encoded, follow_symlinks=False)
        except (StorageError, OSError):
            pass  # Evidence capture must never replace the primary source failure.


def _source_key(fs, options):
    style = asdict(options)
    for name in ["journal", "interval", "timeout", "max_bytes", "warning"]:
        style.pop(name)
    for name in ["marker", "arc"]:
        style[name] = str(fs.resolve(getattr(options, name), write=True).relative_to(fs.root))
    # Version 9 revalidates cached snapshots for literal-safe, bounded marker
    # text and RGB color-key transparency syntax.
    style["parser_version"] = 9
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
        attempt = Attempt(fetcher if fetcher is not None else Fetcher())
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
            capture = _SourceCapture(attempt)
            try:
                snapshot = collect_snapshot(
                    capture, now=now,
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
                capture.save(fs, settings, now)
        if outcome != "failed" and (marker is not None or valid_existing):
            record["successful_at"] = now
        finish(record, now, outcome, message, attempt)
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
