"""Old storm cache identities must be revalidated after source-rule upgrades."""
from dataclasses import asdict
import hashlib
import json

from totalmarker.errors import FeedError
from totalmarker.features.storm import _source_key, run
from totalmarker.labels import render_storm
from totalmarker.storm_model import (ForecastPoint, Storm, StormSnapshot,
                                     TrackPoint, render_arc, render_bodies,
                                     render_marker)
from totalmarker.storm_sources import REQUIRED_GROUPS
from .support import Sandbox
from .test_storm_sources import MappedFetcher, NOW


class FailingFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, url, **kwargs):
        self.calls += 1
        raise FeedError("Synthetic source failure during cache upgrade")


class StormCacheUpgradeTests(Sandbox):
    def old_source_key(self, settings):
        style = asdict(settings.storm)
        for name in ("journal", "interval", "timeout", "max_bytes", "warning"):
            style.pop(name)
        for name in ("marker", "arc"):
            style[name] = str(self.fs.resolve(getattr(settings.storm, name),
                                              write=True).relative_to(self.fs.root))
        style["parser_version"] = 3
        style["sources"] = "NHC-ATCF+JTWC-RSS-warning-KMZ-ABPW-ABIO"
        return hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()

    def exercise_upgrade(self, storms):
        settings = self.config("StormCheckIntervalSeconds=86400\n")
        old = NOW - 60
        snapshot = StormSnapshot(storms, tuple((group, old)
                                               for group in sorted(REQUIRED_GROUPS)), True)
        marker_body, arc_body = render_bodies(snapshot, settings.storm,
                                              required_groups=REQUIRED_GROUPS)
        marker, arc = render_marker(marker_body, old), render_arc(arc_body, old)
        old_key = self.old_source_key(settings)
        new_key = _source_key(self.fs, settings.storm)
        self.assertNotEqual(old_key, new_key)
        record = {
            "marker_sha256": hashlib.sha256(marker).hexdigest(),
            "arc_sha256": hashlib.sha256(arc).hexdigest(),
            "body_sha256": hashlib.sha256(marker_body + b"\0" + arc_body).hexdigest(),
            "source_key": old_key,
            "installed_at": old,
            "successful_at": old,
            "fetched_at": old,
            "count": len(storms),
        }
        self.fs.write(settings.storm.marker, marker)
        self.fs.write(settings.storm.arc, arc)
        self.fs.write(settings.state, json.dumps({"schema": 1, "products": {
            "storm": record}}).encode())
        self.fs.write(settings.labels, render_storm(
            "", old, old, settings.storm.warning, settings.colors).encode())

        broken = FailingFetcher()
        failed = run(self.fs, settings, fetcher=broken, now=NOW)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(broken.calls, 1)  # Cache was bypassed after upgrade.
        self.assertEqual((failed.installed_at, failed.successful_at), (old, old))
        self.assertEqual((self.fs.read(settings.storm.marker),
                          self.fs.read(settings.storm.arc)), (marker, arc))
        failed_state = self.read_state(settings)["products"]["storm"]
        self.assertEqual((failed_state["source_key"], failed_state["fetched_at"],
                          failed_state["successful_at"]), (old_key, old, old))

        valid = MappedFetcher()
        refreshed = run(self.fs, settings, fetcher=valid, now=NOW + 1)
        self.assertEqual((refreshed.outcome, refreshed.count), ("changed", 5))
        self.assertGreater(len(valid.calls), 0)
        self.assertEqual(refreshed.successful_at, NOW + 1)
        self.assertEqual(self.read_state(settings)["products"]["storm"]["source_key"],
                         new_key)

    def test_false_empty_v3_cache_revalidates_and_keeps_files_on_failure(self):
        self.exercise_upgrade(())

    def test_stale_forecast_v3_cache_revalidates_and_keeps_files_on_failure(self):
        old = NOW - 60
        base = old - 18 * 86400
        storm = Storm("EP212026", "Trudy", "STO",
                      TrackPoint(old, 19.7, -107.6), 75, (),
                      TrackPoint(base, 19.6, -107.4),
                      (ForecastPoint(12, base + 12 * 3600, 19.8, -107.9),),
                      "issued")
        self.exercise_upgrade((storm,))
