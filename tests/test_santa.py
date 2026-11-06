"""Synthetic, fake-clock tests for the provider-independent Santa foundation."""
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import hashlib
import json
import tomllib
from pathlib import Path
from unittest.mock import patch

from totalmarker.cli import main
from totalmarker.config import load
from totalmarker.errors import ConfigError, DownloadError, FeedError, StorageError
from totalmarker.features.santa import run
from totalmarker.santa_model import SantaSnapshot, render_marker, validate_snapshot
from totalmarker.state import recover_pending
from .support import PROJECT, Sandbox


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()


class SantaTests(Sandbox):
    def options(self, freshness=3600):
        return self.config(f"SantaEnabled=On\nSantaFreshnessSeconds={freshness}\n")

    def sample(self, now, *, lifecycle="tracking", source_at=None, season_year=None):
        active = lifecycle == "tracking"
        return SantaSnapshot(
            "synthetic-test", season_year or datetime.fromtimestamp(now, timezone.utc).year,
            lifecycle, 12.3456 if active else None, -45.6789 if active else None,
            now - 60 if source_at is None else source_at, now)

    def test_disabled_by_default_and_example_is_inert(self):
        settings = self.config()
        self.assertFalse(settings.santa.enabled)
        self.assertEqual(settings.santa.freshness_seconds, 0)
        self.assertEqual(run(self.fs, settings, now=at(2026, 12, 24)).outcome, "disabled")
        self.assertIsNone(self.fs.read(settings.santa.marker))
        self.assertIsNone(self.fs.read(settings.state))
        (self.root / "example.toml").write_bytes(
            (PROJECT / "config/totalmarker.example.toml").read_bytes())
        self.assertNotIn("santa", tomllib.loads((self.root / "example.toml").read_text()))
        example = load(self.fs, "example.toml")
        self.assertFalse(example.santa.enabled)
        self.assertEqual(example.santa.freshness_seconds, 0)
        self.assertNotIn("santa.enabled", example.deferred_settings)
        with (self.root / "config.toml").open("w") as handle:
            handle.write('[cloud]\nprovider = "custom"\nurl = "https://cloud.example.invalid/x"\n'
                         '[santa]\nenabled = false\nfreshness_seconds = 0\n')
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--root", str(self.root), "--config", "config.toml", "santa"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "disabled")

    def test_enabled_config_requires_freshness_and_distinct_paths(self):
        with self.assertRaisesRegex(ConfigError, "freshness"):
            self.config("SantaEnabled=On\n")
        with self.assertRaisesRegex(ConfigError, "distinct"):
            self.config("SantaOutput=markers/updatelabel\n")
        settings = self.options()
        self.assertTrue(settings.santa.enabled)
        self.assertEqual(settings.deferred_settings, {})

    def test_tracking_identical_update_and_non_santa_isolation(self):
        settings = self.options()
        now = at(2026, 12, 24, 12)
        for name, value in (("markers/quake", b"quake sentinel"),
                            ("markers/storm", b"storm sentinel"),
                            ("markers/updatelabel", b"label sentinel")):
            self.fs.write(name, value)
        before = {name: hashlib.sha256(self.fs.read(name)).hexdigest()
                  for name in ("markers/quake", "markers/storm", "markers/updatelabel")}
        snapshot = self.sample(now)
        first = run(self.fs, settings, adapter=lambda _now: snapshot, now=now)
        self.assertEqual((first.outcome, first.count, first.stale), ("changed", 1, False))
        marker = self.fs.read(settings.santa.marker)
        self.assertIn(b'12.3456 -45.6789 "Santa (reported ', marker)
        self.assertNotIn(b"stale", marker)
        self.assertEqual(marker, render_marker(snapshot))
        record = self.read_state(settings)["products"]["santa"]
        self.assertEqual(record["last_good"]["source_at"], now - 60)
        same = replace(snapshot, retrieved_at=now + 30)
        second = run(self.fs, settings, adapter=lambda _now: same, now=now + 30)
        self.assertEqual((second.outcome, second.count), ("unchanged", 1))
        self.assertEqual(second.installed_at, first.installed_at)
        self.assertEqual(second.successful_at, now + 30)
        self.assertEqual(self.fs.read(settings.santa.marker), marker)
        self.assertEqual(before, {name: hashlib.sha256(self.fs.read(name)).hexdigest()
                                  for name in before})

    def test_failure_marks_stale_then_expires_only_santa(self):
        settings = self.options()
        now = at(2026, 12, 24, 12)
        self.fs.write("markers/quake", b"unchanged")
        run(self.fs, settings, adapter=lambda _now: self.sample(now), now=now)
        def unavailable(_now):
            raise DownloadError("Santa provider unavailable")
        stale = run(self.fs, settings, adapter=unavailable, now=now + 600)
        self.assertEqual((stale.outcome, stale.stale, stale.count), ("failed", True, 1))
        self.assertIn(b"stale; reported", self.fs.read(settings.santa.marker))
        self.assertTrue(self.read_state(settings)["products"]["santa"]["stale"])
        self.assertEqual(stale.successful_at, now)
        expired = run(self.fs, settings, adapter=unavailable, now=now + 3601)
        self.assertEqual((expired.outcome, expired.stale, expired.count), ("failed", False, 0))
        self.assertEqual(self.fs.read(settings.santa.marker), b"")
        self.assertEqual(self.fs.read("markers/quake"), b"unchanged")
        record = self.read_state(settings)["products"]["santa"]
        self.assertEqual(record["last_good"]["source_at"], now - 60)
        self.assertEqual(record["successful_at"], now)
        self.assertFalse(record["stale"])

    def test_no_provider_is_a_failure_without_fake_position(self):
        settings = self.options()
        now = at(2026, 12, 24, 12)
        result = run(self.fs, settings, now=now)
        self.assertEqual((result.outcome, result.count), ("failed", 0))
        self.assertIn("No verified Santa provider", result.message)
        self.assertEqual(self.fs.read(settings.santa.marker), b"")

    def test_lifecycle_window_and_regression(self):
        settings = self.options()
        early = at(2026, 12, 23)
        pre = run(self.fs, settings, adapter=lambda _now: self.sample(
            early, lifecycle="prelaunch"), now=early)
        self.assertEqual((pre.outcome, pre.count), ("changed", 0))
        tracked = at(2026, 12, 24, 9)
        run(self.fs, settings, adapter=lambda _now: self.sample(tracked), now=tracked)
        ended_at = at(2026, 12, 25, 9)
        ended = run(self.fs, settings, adapter=lambda _now: self.sample(
            ended_at, lifecycle="ended"), now=ended_at)
        self.assertEqual((ended.outcome, ended.count), ("changed", 0))
        self.assertEqual(self.fs.read(settings.santa.marker), b"")
        regressed = run(self.fs, settings, adapter=lambda _now: self.sample(
            ended_at + 60), now=ended_at + 60)
        self.assertEqual((regressed.outcome, regressed.count), ("failed", 0))
        self.assertIn("lifecycle regressed", regressed.message)
        outside = run(self.fs, settings, adapter=lambda _now: self.fail(
            "Off-season adapter must not run"), now=at(2026, 12, 26))
        self.assertEqual((outside.outcome, outside.count), ("unchanged", 0))

    def test_prior_year_active_position_is_not_replayed(self):
        settings = self.options()
        prior = at(2026, 12, 24, 12)
        active = run(self.fs, settings, adapter=lambda _now: self.sample(prior), now=prior)
        self.assertEqual((active.outcome, active.count), ("changed", 1))
        self.assertTrue(self.fs.read(settings.santa.marker))

        def unavailable(_now):
            raise DownloadError("Santa provider unavailable")
        next_year = run(self.fs, settings, adapter=unavailable, now=at(2027, 12, 24, 12))
        self.assertEqual((next_year.outcome, next_year.stale, next_year.count),
                         ("failed", False, 0))
        self.assertEqual(self.fs.read(settings.santa.marker), b"")
        record = self.read_state(settings)["products"]["santa"]
        self.assertEqual(record["last_good"]["season_year"], 2026)
        self.assertEqual(record["successful_at"], prior)

    def test_explicit_season_mismatch_clears_active_position(self):
        settings = self.options()
        now = at(2026, 12, 24, 12)
        run(self.fs, settings, adapter=lambda _now: self.sample(now), now=now)
        self.assertTrue(self.fs.read(settings.santa.marker))
        mismatch = replace(self.sample(now + 60), season_year=2025)
        result = run(self.fs, settings, adapter=lambda _now: mismatch, now=now + 60)
        self.assertEqual((result.outcome, result.stale, result.count),
                         ("failed", False, 0))
        self.assertIn("another season", result.message)
        self.assertEqual(self.fs.read(settings.santa.marker), b"")
        record = self.read_state(settings)["products"]["santa"]
        self.assertEqual(record["last_good"]["season_year"], 2026)
        self.assertEqual(record["successful_at"], now)

    def test_unrepresentable_coordinate_expires_stale_position(self):
        settings = self.options()
        now = at(2026, 12, 24, 12)
        run(self.fs, settings, adapter=lambda _now: self.sample(now), now=now)

        def unavailable(_now):
            raise DownloadError("Santa provider unavailable")
        stale = run(self.fs, settings, adapter=unavailable, now=now + 600)
        self.assertTrue(stale.stale)
        invalid = replace(self.sample(now + 3601), latitude=10**400)
        with self.assertRaisesRegex(FeedError, "latitude"):
            validate_snapshot(invalid, now=now + 3601)
        expired = run(self.fs, settings, adapter=lambda _now: invalid, now=now + 3601)
        self.assertEqual((expired.outcome, expired.stale, expired.count),
                         ("failed", False, 0))
        self.assertEqual(self.fs.read(settings.santa.marker), b"")

    def test_bad_snapshots_and_regression_fail_closed(self):
        now = at(2026, 12, 24, 12)
        base = self.sample(now)
        bad = (
            replace(base, provider_id="bad\nprovider"),
            replace(base, lifecycle=[]),
            replace(base, latitude=True),
            replace(base, longitude=float("nan")),
            replace(base, source_at=now + 301),
            replace(base, retrieved_at=now - 301),
            replace(base, season_year=2025),
            replace(base, lifecycle="ended"),
        )
        for snapshot in bad:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(FeedError):
                    validate_snapshot(snapshot, now=now)
        settings = self.options()
        run(self.fs, settings, adapter=lambda _now: base, now=now)
        marker = self.fs.read(settings.santa.marker)
        regressed = replace(base, source_at=now - 120, retrieved_at=now + 30)
        failed = run(self.fs, settings, adapter=lambda _now: regressed, now=now + 30)
        self.assertEqual((failed.outcome, failed.stale), ("failed", True))
        self.assertEqual(self.read_state(settings)["products"]["santa"]
                         ["last_good"]["source_at"], now - 60)
        self.assertNotEqual(self.fs.read(settings.santa.marker), marker)
        state = self.read_state(settings)
        state["products"]["santa"]["last_good"]["latitude"] = 999
        self.fs.write(settings.state, (json.dumps(state) + "\n").encode())
        with self.assertRaises(StorageError):
            run(self.fs, settings, adapter=lambda _now: base, now=now + 60)

    def test_interrupted_marker_publication_recovers(self):
        settings = self.options()
        now = at(2026, 12, 24, 12)
        real_write = self.fs.write
        def interrupted(path, data, **kwargs):
            if path == settings.state:
                raise StorageError("synthetic interruption")
            return real_write(path, data, **kwargs)
        with patch.object(self.fs, "write", side_effect=interrupted):
            with self.assertRaisesRegex(StorageError, "interruption"):
                run(self.fs, settings, adapter=lambda _now: self.sample(now), now=now)
        self.assertIsNotNone(self.fs.read(settings.santa.journal))
        self.assertIsNotNone(self.fs.read(settings.santa.marker))
        recover_pending(self.fs, settings)
        self.assertIsNone(self.fs.read(settings.santa.journal))
        record = self.read_state(settings)["products"]["santa"]
        self.assertEqual(record["marker_sha256"], hashlib.sha256(
            self.fs.read(settings.santa.marker)).hexdigest())
