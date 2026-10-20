from datetime import datetime, timezone
from email.utils import formatdate
import hashlib
import json

from totalmarker.errors import StorageError
from totalmarker.features.clouds import modified_time, run
from totalmarker.http import Fetcher, Response
from totalmarker.image import cloud_creation_time, validate_jpeg
from totalmarker.labels import legacy_time
from .support import Sandbox, ScriptedTransport, jpeg

NOW = 1700000000
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
          "Sep", "Oct", "Nov", "Dec")


def created_comment(timestamp):
    stamp = datetime.fromtimestamp(timestamp, timezone.utc)
    return (f"EarthDesk Cloud Image Created {WEEKDAYS[stamp.weekday()]} "
            f"{MONTHS[stamp.month - 1]} {stamp.day:02d} "
            f"{stamp.hour:02d}:{stamp.minute:02d}:{stamp.second:02d} "
            f"UTC {stamp.year}").encode()


def response(body, **headers):
    return Response(200, {"Content-Type": "image/jpeg", **headers}, body)


class CloudCreationTimeTests(Sandbox):
    def run_with(self, settings, *responses, now=NOW, label_only=False):
        transport = ScriptedTransport(*responses)
        result = run(self.fs, settings, fetcher=Fetcher(transport),
                     now=now, label_only=label_only, environment={})
        return result, transport

    def test_fresh_download_of_old_image_uses_embedded_creation_not_later_server_time(self):
        settings = self.config()
        old = NOW - 50000
        server_modified = NOW - 5000
        body = jpeg(created_comment(old))
        result, _ = self.run_with(settings, response(
            body, **{"Last-Modified": formatdate(server_modified, usegmt=True)}))
        record = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(result.installed_at, NOW)
        self.assertEqual(result.source_created_at, old)
        self.assertEqual(record["checked_at"], NOW)
        self.assertEqual(record["fetched_at"], NOW)
        self.assertEqual(record["installed_at"], NOW)
        self.assertEqual(record["source_modified_at"], server_modified)
        self.assertEqual(record["source_created_at"], old)
        self.assertEqual(record["source_time_origin"], "jpeg-earthdesk-comment")
        self.assertEqual(record["source_image_sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(self.fs.file_stat(settings.image).st_mtime, server_modified)
        label = self.fs.read(settings.labels)
        self.assertIn(legacy_time(old).encode(), label)
        self.assertIn(b"color=Red", label)
        self.assertNotIn(legacy_time(NOW).encode(), label)

    def test_existing_download_time_state_migrates_from_current_image_without_network(self):
        settings = self.config()
        created = NOW - 50000
        body = jpeg(created_comment(created))
        self.fs.write(settings.image, body, mtime=NOW - 1000)
        old_record = {"installed_at": NOW, "checked_at": NOW, "fetched_at": NOW,
                      "timestamp_origin": "installed",
                      "last_modified": formatdate(NOW - 1000, usegmt=True),
                      "source_modified_at": NOW - 1000,
                      "image_sha256": hashlib.sha256(body).hexdigest()}
        self.fs.write(settings.state, json.dumps({
            "schema": 1, "products": {"clouds": old_record}}).encode())
        self.fs.write(settings.labels, (
            f'-53 -12 "Cloud Map Last Updated {legacy_time(NOW)}" color=Green '
            'image=none position=pixel\n').encode())
        result, transport = self.run_with(settings, label_only=True)
        self.assertEqual(transport.calls, [])
        self.assertEqual(result.installed_at, NOW)
        self.assertEqual(result.source_created_at, created)
        record = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(record["installed_at"], NOW)
        self.assertEqual(record["source_created_at"], created)
        self.assertEqual(record["source_modified_at"], NOW - 1000)
        self.assertIn(legacy_time(created).encode(), self.fs.read(settings.labels))
        self.assertIn(b"color=Red", self.fs.read(settings.labels))

    def test_legacy_label_origin_is_kept_only_as_unverified_history(self):
        settings = self.config()
        created = NOW - 50000
        body = jpeg(created_comment(created))
        self.fs.write(settings.image, body)
        self.fs.write(settings.state, json.dumps({"schema": 1, "products": {
            "clouds": {"installed_at": NOW - 100,
                       "timestamp_origin": "legacy-label",
                       "image_sha256": hashlib.sha256(body).hexdigest()}}}).encode())
        result, _ = self.run_with(settings, label_only=True)
        record = self.read_state(settings)["products"]["clouds"]
        self.assertIsNone(result.installed_at)
        self.assertEqual(record["legacy_label_at"], NOW - 100)
        self.assertEqual(result.source_created_at, created)

    def test_missing_creation_comment_does_not_fall_back_to_last_modified_or_install(self):
        settings = self.config()
        modified = NOW - 1000
        body = jpeg(b"")
        result, _ = self.run_with(settings, response(
            body, **{"Last-Modified": formatdate(modified, usegmt=True)}))
        self.assertEqual(result.installed_at, NOW)
        self.assertIsNone(result.source_created_at)
        record = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(record["source_modified_at"], modified)
        self.assertEqual(record["source_time_origin"], "unavailable")
        self.assertIn(b"Last Updated UNKNOWN", self.fs.read(settings.labels))
        self.assertIn(b"color=Red", self.fs.read(settings.labels))

    def test_malformed_or_conflicting_embedded_comments_do_not_create_a_time(self):
        valid = created_comment(NOW - 3600)
        cases = [
            b"EarthDesk Cloud Image Created Thu Nov 14 22:13:20 UTC 2023",
            b"EarthDesk Cloud Image Created Tue Feb 31 22:13:20 UTC 2023",
            b"EarthDesk Cloud Image Created Tue Nov 14 22:13:20 2023",
            b"EarthDesk Cloud Image Created garbage",
            b"unrelated image comment"]
        for comment in cases:
            with self.subTest(comment=comment):
                self.assertIsNone(cloud_creation_time(jpeg(comment)))
        other = created_comment(NOW - 7200)
        extra = b"\xff\xfe" + (len(other) + 2).to_bytes(2, "big") + other
        conflict = jpeg(valid)[:2] + extra + jpeg(valid)[2:]
        validate_jpeg(conflict)
        self.assertIsNone(cloud_creation_time(conflict))
        # A string in compressed scan bytes is not metadata.
        no_comment = jpeg(b"")
        scan_text = no_comment[:-2] + valid + no_comment[-2:]
        self.assertIsNone(cloud_creation_time(scan_text))

    def test_future_creation_comment_is_unavailable_until_clock_reaches_it(self):
        settings = self.config()
        future = NOW + 3600
        body = jpeg(created_comment(future))
        result, _ = self.run_with(settings, response(
            body, **{"Last-Modified": formatdate(NOW - 100, usegmt=True)}))
        self.assertIsNone(result.source_created_at)
        self.assertIn(b"UNKNOWN", self.fs.read(settings.labels))
        self.assertIn(b"color=Red", self.fs.read(settings.labels))
        result, transport = self.run_with(settings, now=future + 1, label_only=True)
        self.assertEqual(transport.calls, [])
        self.assertEqual(result.source_created_at, future)
        self.assertIn(legacy_time(future).encode(), self.fs.read(settings.labels))

    def test_304_and_identical_200_with_different_last_modified_keep_creation_time(self):
        settings = self.config("CloudCheckIntervalSeconds=0\n")
        created = NOW - 40000
        body = jpeg(created_comment(created))
        self.run_with(settings, response(
            body, ETag='"first"', **{"Last-Modified": formatdate(NOW - 5000, usegmt=True)}))
        result, transport = self.run_with(settings, response(
            body, ETag='"second"', **{"Last-Modified": formatdate(NOW - 1000, usegmt=True)}),
            now=NOW + 1)
        self.assertEqual(result.source_created_at, created)
        self.assertIn("If-Modified-Since", transport.calls[0][1])
        result, transport = self.run_with(
            settings, Response(304, {"Last-Modified": formatdate(NOW + 5, usegmt=True)}),
            now=NOW + 2)
        self.assertEqual(result.source_created_at, created)
        record = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(record["source_modified_at"], NOW + 5)
        self.assertIn(legacy_time(created).encode(), self.fs.read(settings.labels))
        self.assertIn(b"color=Yellow", self.fs.read(settings.labels))

    def test_cache_and_failed_fetch_age_creation_time_without_advancing_it(self):
        settings = self.config()
        created = NOW - 50000
        self.run_with(settings, response(jpeg(created_comment(created))))
        cached, transport = self.run_with(settings, now=NOW + 1200)
        self.assertEqual(transport.calls, [])
        self.assertEqual(cached.source_created_at, created)
        self.assertIn(b"color=Red", self.fs.read(settings.labels))
        failed, transport = self.run_with(settings, Response(503, {}),
                                          now=NOW + 3600)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.source_created_at, created)
        self.assertEqual(failed.installed_at, NOW)
        self.assertIn(legacy_time(created).encode(), self.fs.read(settings.labels))

    def test_changed_image_without_creation_metadata_clears_prior_display_time(self):
        settings = self.config("CloudCheckIntervalSeconds=0\n")
        first = NOW - 1000
        self.run_with(settings, response(jpeg(created_comment(first))))
        changed, _ = self.run_with(
            settings, response(jpeg(b"new pixels, no creation time"),
                               **{"Last-Modified": formatdate(NOW + 1, usegmt=True)}),
            now=NOW + 2)
        self.assertEqual(changed.outcome, "changed")
        self.assertEqual(changed.installed_at, NOW + 2)
        self.assertIsNone(changed.source_created_at)
        self.assertIn(b"UNKNOWN", self.fs.read(settings.labels))
        self.assertIn(b"color=Red", self.fs.read(settings.labels))

    def test_external_image_replacement_updates_label_from_current_bytes(self):
        settings = self.config()
        self.run_with(settings, response(jpeg(created_comment(NOW - 1000))))
        self.fs.write(settings.image, jpeg(b"no production metadata"))
        result, _ = self.run_with(settings, label_only=True)
        self.assertIsNone(result.source_created_at)
        self.assertIn(b"UNKNOWN", self.fs.read(settings.labels))

    def test_header_timezone_normalization_is_separate_from_embedded_utc(self):
        offset_header = "Tue, 14 Nov 2023 18:13:20 -0400"
        self.assertEqual(modified_time(offset_header), NOW)
        self.assertIsNone(modified_time("Tue, 14 Nov 2023 22:13:20"))
        settings = self.config()
        created = NOW - 3600
        self.run_with(settings, response(
            jpeg(created_comment(created)), **{"Last-Modified": offset_header}))
        record = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(record["source_modified_at"], NOW)
        self.assertEqual(record["source_created_at"], created)
        self.assertIn(legacy_time(created).encode(), self.fs.read(settings.labels))

    def test_invalid_new_source_time_state_fails_closed(self):
        settings = self.config()
        self.fs.write(settings.state, json.dumps({"schema": 1, "products": {
            "clouds": {"source_created_at": True}}}).encode())
        with self.assertRaises(StorageError):
            self.run_with(settings, label_only=True)
