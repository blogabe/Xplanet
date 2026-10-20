"""Disabled-by-default Santa layer with an injected, provider-neutral adapter."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import time
from typing import Protocol

from ..errors import DownloadError, FeedError
from ..santa_model import (SantaSnapshot, SeasonMismatch, fresh, render_marker,
                           season_active, snapshot_from_record, snapshot_record,
                           validate_snapshot)
from ..state import MarkerPublisher, load_state, recover_pending


class SantaAdapter(Protocol):
    def __call__(self, now: float) -> SantaSnapshot: ...


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    successful_at: float | None
    source_at: float | None
    count: int
    stale: bool


def run(fs, settings, *, adapter: SantaAdapter | None = None, now=None):
    options = settings.santa
    if not options.enabled:
        return Result("disabled", "Santa is disabled in configuration", None, None, None, 0, False)
    now = time.time() if now is None else now
    with fs.lock(settings.lock):
        recover_pending(fs, settings)
        publisher = MarkerPublisher(fs, settings, "santa")
        state = load_state(fs, settings.state)
        record = state["products"].setdefault("santa", {})
        record["checked_at"] = now
        old_marker = fs.read(options.marker, 1024 * 1024)
        valid_old = (old_marker is not None and
                     hashlib.sha256(old_marker).hexdigest() == record.get("marker_sha256"))
        previous = (snapshot_from_record(record["last_good"])
                    if record.get("last_good") is not None else None)
        failed = False
        stale = False
        if not season_active(now):
            desired = b""
            message = "Santa layer is outside the December 23-25 UTC window"
        else:
            try:
                if adapter is None:
                    raise FeedError("No verified Santa provider is configured")
                snapshot = validate_snapshot(adapter(now), now=now)
                if (previous is not None and snapshot.provider_id == previous.provider_id
                        and snapshot.season_year == previous.season_year):
                    if snapshot.source_at < previous.source_at:
                        raise FeedError("Santa source time regressed")
                    stages = {"prelaunch": 0, "tracking": 1, "ended": 2}
                    if stages[snapshot.lifecycle] < stages[previous.lifecycle]:
                        raise FeedError("Santa lifecycle regressed")
                    if (snapshot.source_at == previous.source_at and
                            (snapshot.lifecycle, snapshot.latitude, snapshot.longitude) !=
                            (previous.lifecycle, previous.latitude, previous.longitude)):
                        raise FeedError("Santa position changed without a new source time")
                if snapshot.lifecycle == "tracking" and not fresh(
                        snapshot, now, options.freshness_seconds):
                    raise FeedError("Santa source position is stale")
                record["last_good"] = snapshot_record(snapshot)
                record["fetched_at"] = snapshot.retrieved_at
                record["successful_at"] = now
                desired = render_marker(snapshot)
                message = "Validated Santa snapshot accepted"
            except (DownloadError, FeedError) as error:
                failed = True
                message = str(error)
                stale = (not isinstance(error, SeasonMismatch)
                         and previous is not None
                         and previous.season_year == datetime.fromtimestamp(now, timezone.utc).year
                         and fresh(previous, now, options.freshness_seconds))
                desired = render_marker(previous, stale=True) if stale else b""
        marker = None
        if not valid_old or old_marker != desired:
            if len(desired) > 1024 * 1024:
                raise FeedError("Santa marker output exceeds the size limit")
            marker = desired
            record["marker_sha256"] = hashlib.sha256(desired).hexdigest()
            record["installed_at"] = now
        outcome = "failed" if failed else "changed" if marker is not None else "unchanged"
        record["last_outcome"] = outcome
        record["stale"] = stale
        record["count"] = 1 if desired else 0
        publisher.publish(state, None, marker=marker)
        source_at = previous.source_at if failed and stale else (
            record["last_good"]["source_at"] if desired and not failed else None)
        return Result(outcome, message, record.get("installed_at"),
                      record.get("successful_at"), source_at,
                      record["count"], stale)
