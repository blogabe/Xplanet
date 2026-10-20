from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from email.utils import formatdate
import hashlib
import io
import json
import time
from unittest.mock import patch

from totalmarker.cli import main
from totalmarker.errors import StorageError
from totalmarker.features.clouds import run
from totalmarker.http import Fetcher, Response
from totalmarker.labels import legacy_time
from totalmarker.state import Publisher
from .support import Sandbox, ScriptedTransport, image_response, jpeg

NOW = 1700000000


class CloudTests(Sandbox):
    def run_with(self, settings, *responses, now=NOW, label_only=False):
        transport = ScriptedTransport(*responses)
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=now,
                     label_only=label_only, environment={})
        return result, transport

    def test_first_changed_image_state_mtime_and_label(self):
        settings = self.config()
        modified = formatdate(NOW - 5000, usegmt=True)
        result, transport = self.run_with(settings, image_response(ETag='"edition-1"',
                                              **{"Last-Modified": modified}))
        self.assertEqual(result.outcome, "changed")
        self.assertEqual(result.installed_at, NOW)
        self.assertEqual(self.fs.read(settings.image), jpeg())
        self.assertEqual(self.fs.file_stat(settings.image).st_mtime, NOW - 5000)
        state = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(state["source_modified_at"], NOW - 5000)
        self.assertEqual(state["checked_at"], NOW)
        self.assertEqual(state["installed_at"], NOW)
        self.assertIn(legacy_time(NOW).encode(), self.fs.read(settings.labels))
        self.assertIn(b'-53 -12 "', self.fs.read(settings.labels))
        self.assertNotIn("cloud.example", self.fs.read(settings.log).decode())

    def test_cached_check_does_not_fetch_or_advance_timestamp(self):
        settings = self.config()
        self.run_with(settings, image_response())
        result, transport = self.run_with(settings, now=NOW + 1200)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(result.installed_at, NOW)
        self.assertEqual(transport.calls, [])
        state = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(state["checked_at"], NOW + 1200)
        self.assertEqual(state["fetched_at"], NOW)

    def test_304_uses_validators_and_keeps_last_update(self):
        settings = self.config()
        modified = formatdate(NOW - 5000, usegmt=True)
        self.run_with(settings, image_response(ETag='"edition-1"',
                                              **{"Last-Modified": modified}))
        before = self.fs.file_stat(settings.image).st_mtime_ns
        result, transport = self.run_with(settings, Response(304, {}), now=NOW + 21601)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(result.installed_at, NOW)
        self.assertEqual(transport.calls[0][1]["If-None-Match"], '"edition-1"')
        self.assertEqual(transport.calls[0][1]["If-Modified-Since"], modified)
        self.assertEqual(self.fs.file_stat(settings.image).st_mtime_ns, before)
        self.assertIn(b"color=Yellow", self.fs.read(settings.labels))

    def test_identical_200_keeps_timestamp_and_image_mtime(self):
        settings = self.config()
        self.run_with(settings, image_response())
        before = self.fs.file_stat(settings.image).st_mtime_ns
        result, _ = self.run_with(settings, image_response(
            **{"Last-Modified": formatdate(NOW + 100, usegmt=True)}), now=NOW + 3600)
        self.assertEqual(result.outcome, "unchanged")
        self.assertEqual(result.installed_at, NOW)
        self.assertEqual(self.fs.file_stat(settings.image).st_mtime_ns, before)

    def test_changed_edition_advances_only_after_publication(self):
        settings = self.config()
        self.run_with(settings, image_response())
        result, _ = self.run_with(settings, image_response(b"new edition"), now=NOW + 3600)
        self.assertEqual(result.outcome, "changed")
        self.assertEqual(result.installed_at, NOW + 3600)
        self.assertEqual(self.fs.read(settings.image), jpeg(b"new edition"))

    def test_failures_keep_last_good_image_time_and_time_based_colors(self):
        settings = self.config("CloudCheckIntervalSeconds=0\n")
        self.run_with(settings, image_response())
        for index, response in enumerate([
            Response(500, {}, b"DUMMY_BODY_SECRET"), TimeoutError("DUMMY_SECRET"),
            Response(200, {"Content-Type": "text/html"}, b"HTML"),
            Response(200, {"Content-Type": "image/jpeg"}, jpeg()[:-2])
        ]):
            result, _ = self.run_with(settings, response, now=NOW + index + 1)
            self.assertEqual(result.outcome, "failed")
            self.assertEqual(result.installed_at, NOW)
            self.assertEqual(self.fs.read(settings.image), jpeg())
            self.assertIn(b"color=Green", self.fs.read(settings.labels))
        self.assertNotIn(b"DUMMY", self.fs.read(settings.log))

    def test_invalid_validator_does_not_replace_image_or_digest(self):
        settings = self.config("CloudCheckIntervalSeconds=0\n")
        self.run_with(settings, image_response())
        before = self.read_state(settings)["products"]["clouds"]
        result, _ = self.run_with(settings, image_response(b"new",
                            ETag="invalid\r\nDUMMY_SECRET"), now=NOW + 1)
        after = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(after["image_sha256"], before["image_sha256"])
        self.assertEqual(after["installed_at"], before["installed_at"])
        self.assertEqual(self.fs.read(settings.image), jpeg())

    def test_no_file_failure_and_304_do_not_invent_success(self):
        for response in [Response(503, {}), Response(304, {})]:
            settings = self.config()
            result, _ = self.run_with(settings, response)
            self.assertEqual(result.outcome, "failed")
            self.assertIsNone(result.installed_at)
            self.assertIsNone(self.fs.read(settings.image))
            self.assertIn(b"Last Updated UNKNOWN", self.fs.read(settings.labels))
            self.assertIn(b"color=Red", self.fs.read(settings.labels))

    def test_label_only_never_fetches_or_requires_credentials(self):
        settings = self.config(custom=False)
        result, transport = self.run_with(settings, label_only=True)
        self.assertEqual(transport.calls, [])
        self.assertEqual(result.outcome, "unchanged")
        self.assertIsNone(result.installed_at)
        self.assertNotIn("fetched_at", self.read_state(settings)["products"]["clouds"])

    def test_label_only_ages_known_time_and_preserves_other_rows(self):
        settings = self.config()
        self.run_with(settings, image_response())
        other = '-9 -13 "Earthquake Infomation Last Updated UNKNOWN" color=Red image=none position=pixel\n'
        self.fs.write(settings.labels, other.encode() + self.fs.read(settings.labels))
        result, _ = self.run_with(settings, now=NOW + 43201, label_only=True)
        self.assertEqual(result.installed_at, NOW)
        self.assertTrue(self.fs.read(settings.labels).startswith(other.encode()))
        self.assertIn(b"color=Red", self.fs.read(settings.labels).splitlines()[-1])

    def test_legacy_label_is_unverified_history_not_source_creation_or_installation(self):
        settings = self.config()
        self.fs.write(settings.image, jpeg(), mtime=NOW - 50000)
        row = f'-53 -12 "Cloud Map Last Updated {legacy_time(NOW - 1000)}" color=Green image=none position=pixel\n'
        self.fs.write(settings.labels, row.encode())
        result, _ = self.run_with(settings, image_response())
        self.assertEqual(result.outcome, "unchanged")
        self.assertIsNone(result.installed_at)
        self.assertEqual(result.source_created_at, NOW)
        record = self.read_state(settings)["products"]["clouds"]
        self.assertEqual(record["legacy_label_at"], NOW - 1000)
        self.assertIn(legacy_time(NOW).encode(), self.fs.read(settings.labels))

    def test_existing_image_without_creation_metadata_keeps_unknown_timestamp(self):
        settings = self.config()
        self.fs.write(settings.image, jpeg(b""), mtime=NOW - 1000)
        result, _ = self.run_with(settings, image_response(b""))
        self.assertEqual(result.outcome, "unchanged")
        self.assertIsNone(result.installed_at)
        self.assertIsNone(result.source_created_at)
        self.assertIn(b"UNKNOWN", self.fs.read(settings.labels))

    def test_disabled_labels_and_unknown_state_are_preserved(self):
        settings = self.config("LabelOnOff=Off\nQuakeMinimumSize=6\n")
        self.fs.write(settings.labels, b"unchanged other marker\n")
        self.fs.write(settings.state, json.dumps({"schema": 1, "products": {
            "quakes": {"installed_at": NOW - 10, "unknown_future_setting": True}}}).encode())
        before_config = (self.root / "config.ini").read_bytes()
        self.run_with(settings, image_response())
        self.assertEqual(self.fs.read(settings.labels), b"unchanged other marker\n")
        self.assertEqual(self.read_state(settings)["products"]["quakes"]["installed_at"], NOW - 10)
        self.assertEqual((self.root / "config.ini").read_bytes(), before_config)

    def test_url_change_does_not_send_previous_validators(self):
        settings = self.config()
        self.run_with(settings, image_response(ETag='"old-provider"'))
        changed = replace(settings, url="https://alternate.example.invalid/map.jpg")
        result, transport = self.run_with(changed, image_response(), now=NOW + 1)
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        self.assertEqual(result.installed_at, NOW)

    def test_auth_failure_is_clear_and_logs_are_redacted(self):
        settings = self.config(custom=False)
        result, transport = self.run_with(settings)
        self.assertEqual(result.outcome, "failed")
        self.assertIn("authentication is missing", result.message)
        self.assertEqual(transport.calls, [])
        custom = self.config("CustomUsername=DUMMY_USER\nCustomPassword=DUMMY_PASSWORD\n"
                             "CloudCheckIntervalSeconds=0\n")
        result, _ = self.run_with(custom, Response(401, {}, b"DUMMY_PASSWORD"))
        for sensitive in ["DUMMY_USER", "DUMMY_PASSWORD", "Authorization", "Basic "]:
            self.assertNotIn(sensitive, repr(result))
            self.assertNotIn(sensitive.encode(), self.fs.read(custom.log))

    def test_cloud_publication_preserves_internal_image_symlink(self):
        settings = self.config("CloudOutput=images/output/current.jpg\n")
        target = self.root / "images" / "output" / "editions" / "month.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(jpeg(b"old"))
        alias = self.root / "images" / "output" / "current.jpg"
        alias.symlink_to("editions/month.jpg")
        self.run_with(settings, image_response())
        self.assertTrue(alias.is_symlink())
        self.assertEqual(target.read_bytes(), jpeg())

    def test_corrupt_state_fails_closed(self):
        settings = self.config()
        self.fs.write(settings.image, jpeg())
        self.fs.write(settings.state, b"{broken")
        with self.assertRaises(StorageError):
            self.run_with(settings, image_response(b"must not publish"))
        self.assertEqual(self.fs.read(settings.image), jpeg())
        self.assertEqual(self.fs.read(settings.state), b"{broken")

    def test_recovery_after_image_before_state_keeps_original_install_time(self):
        settings = self.config()
        original = self.fs.write
        failed = False
        def interrupted(path, data, **kwargs):
            nonlocal failed
            if path == settings.state and not failed:
                failed = True
                raise StorageError("Simulated publication interruption")
            return original(path, data, **kwargs)
        with patch.object(self.fs, "write", side_effect=interrupted):
            with self.assertRaises(StorageError):
                self.run_with(settings, image_response())
        self.assertEqual(self.fs.read(settings.image), jpeg())
        self.assertIsNotNone(self.fs.read(settings.journal))
        result, transport = self.run_with(settings, now=NOW + 1)
        self.assertEqual(result.installed_at, NOW)
        self.assertEqual(transport.calls, [])
        self.assertIsNone(self.fs.read(settings.journal))

    def test_recovery_before_image_does_not_advance_state(self):
        settings = self.config()
        self.run_with(settings, image_response())
        original = self.fs.write
        def interrupted(path, data, **kwargs):
            if path == settings.image:
                raise StorageError("Simulated image interruption")
            return original(path, data, **kwargs)
        with patch.object(self.fs, "write", side_effect=interrupted):
            with self.assertRaises(StorageError):
                self.run_with(settings, image_response(b"second"), now=NOW + 3600)
        self.assertTrue(Publisher(self.fs, settings).recover() is False)
        self.assertEqual(self.read_state(settings)["products"]["clouds"]["installed_at"], NOW)
        self.assertEqual(self.fs.read(settings.image), jpeg())

    def test_overlapping_jobs_share_lock_and_do_not_double_fetch(self):
        settings = self.config()
        class SlowTransport(ScriptedTransport):
            def request(inner, *args):
                time.sleep(0.08)
                return super().request(*args)
        transport = SlowTransport(image_response())
        fetcher = Fetcher(transport)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(self.fs, settings, fetcher=fetcher,
                                                  now=NOW, environment={}), range(2)))
        self.assertEqual(sorted(r.outcome for r in results), ["changed", "unchanged"])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(self.read_state(settings)["products"]["clouds"]["installed_at"], NOW)

    def test_cli_label_only_is_offline(self):
        self.config()
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            code = main(["--root", str(self.root), "--config", "config.ini", "labels"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "unchanged")

    def test_xeric_dummy_plaintext_mode_with_expected_resolution(self):
        settings = self.config("CloudResolution=2048\nXericUsername=DUMMY_LICENSE_KEY\n"
                               "XericPassword=DUMMY_XERIC_PASSWORD\n", custom=False)
        transport = ScriptedTransport(Response(200, {"Content-Type": "image/jpeg"},
                                               jpeg(width=2048, height=1024)))
        result = run(self.fs, settings, fetcher=Fetcher(transport), now=NOW, environment={})
        self.assertEqual(result.outcome, "changed")
        self.assertIn("Authorization", transport.calls[0][1])
        self.assertNotIn(b"DUMMY", self.fs.read(settings.log))

    def test_recovery_rejects_configuration_path_change(self):
        settings = self.config()
        original = self.fs.write
        def interrupted(path, data, **kwargs):
            if path == settings.state:
                raise StorageError("Simulated interruption")
            return original(path, data, **kwargs)
        with patch.object(self.fs, "write", side_effect=interrupted):
            with self.assertRaises(StorageError):
                self.run_with(settings, image_response())
        changed = replace(settings, image="images/different.jpg")
        with self.assertRaisesRegex(StorageError, "original configuration"):
            Publisher(self.fs, changed).recover()
        self.assertIsNotNone(self.fs.read(settings.journal))

    def test_corrupt_existing_image_is_not_accepted_on_304(self):
        settings = self.config("CloudCheckIntervalSeconds=0\n")
        self.run_with(settings, image_response())
        self.fs.write(settings.image, b"<html>replaced outside the tool</html>")
        result, transport = self.run_with(settings, Response(304, {}), now=NOW + 1)
        self.assertEqual(result.outcome, "failed")
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        self.assertEqual(result.installed_at, NOW)

    def test_provisional_module_entrypoint_help_is_offline(self):
        import os, subprocess, sys
        from .support import PROJECT
        result = subprocess.run([sys.executable, "-B", "-m", "totalmarker", "--help"],
                                cwd=PROJECT, env={**os.environ, "PYTHONPATH": str(PROJECT / "scripts"), "PYTHONDONTWRITEBYTECODE": "1"}, text=True,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("clouds", result.stdout)
        self.assertIn("labels", result.stdout)

    def test_provider_identity_change_with_identical_url_does_not_cache_or_reuse_validators(self):
        from totalmarker.config import AuthSpec
        import base64
        settings = self.config(
            "CloudProvider=custom\nCloudResolution=2048\n"
            "CloudURL=https://secure.xericdesign.com/xplanet/clouds/2048/clouds-2048.jpg\n"
            "CustomUsername=DUMMY_CUSTOM_USER\nCustomPassword=DUMMY_CUSTOM_PASSWORD\n",
            custom=False)
        body = jpeg(width=2048, height=1)
        self.run_with(settings, Response(200, {"ETag": '"old-custom"'}, body))
        changed = replace(settings, provider="xeric",
                          auth=AuthSpec("basic", "DUMMY_XERIC_USER", "DUMMY_XERIC_PASSWORD"))
        result, transport = self.run_with(changed, Response(200, {}, body), now=NOW + 1)
        self.assertEqual(len(transport.calls), 1)
        headers = transport.calls[0][1]
        self.assertNotIn("If-None-Match", headers)
        expected = "Basic " + base64.b64encode(b"DUMMY_XERIC_USER:DUMMY_XERIC_PASSWORD").decode()
        self.assertEqual(headers["Authorization"], expected)
        self.assertEqual(result.installed_at, NOW)

    def test_resolution_change_with_same_url_and_valid_image_forces_unconditional_fetch(self):
        settings = self.config()
        self.run_with(settings, image_response(ETag='"old-resolution"'))
        changed = replace(settings, resolution=2)
        result, transport = self.run_with(changed, image_response(), now=NOW + 1)
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        self.assertEqual(result.installed_at, NOW)

    def test_output_change_to_identical_existing_image_forces_unconditional_fetch(self):
        settings = self.config()
        self.run_with(settings, image_response(ETag='"old-output"'))
        changed = replace(settings, image="images/other.jpg")
        self.fs.write(changed.image, jpeg())
        result, transport = self.run_with(changed, image_response(), now=NOW + 1)
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        self.assertEqual(result.installed_at, NOW)

    def test_internal_alias_retarget_to_identical_image_does_not_use_old_cache(self):
        settings = self.config("CloudOutput=images/output/current.jpg\n")
        directory = self.root / "images" / "output"
        directory.mkdir(parents=True)
        (directory / "a.jpg").write_bytes(jpeg())
        (directory / "b.jpg").write_bytes(jpeg())
        alias = directory / "current.jpg"
        alias.symlink_to("a.jpg")
        self.run_with(settings, image_response(ETag='"old-target"'))
        alias.unlink()
        alias.symlink_to("b.jpg")
        _, transport = self.run_with(settings, image_response(), now=NOW + 1)
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        self.assertTrue(alias.is_symlink())

    def test_failed_source_switch_cannot_lend_attempt_time_or_validators_to_previous_source(self):
        settings = self.config()
        self.run_with(settings, image_response(ETag='"original"'))
        changed = replace(settings, url="https://alternate.example.invalid/map.jpg")
        result, transport = self.run_with(changed, Response(503, {}), now=NOW + 1)
        self.assertEqual(result.outcome, "failed")
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        result, transport = self.run_with(settings, image_response(), now=NOW + 2)
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        self.assertEqual(result.installed_at, NOW)

    def test_previous_url_only_state_key_forces_one_fresh_fetch(self):
        settings = self.config()
        self.run_with(settings, image_response(ETag='"old-version"'))
        state = self.read_state(settings)
        record = state["products"]["clouds"]
        record["source_key"] = hashlib.sha256(settings.url.encode()).hexdigest()
        record.pop("fetch_source_key")
        self.fs.write(settings.state, json.dumps(state).encode())
        _, transport = self.run_with(settings, image_response(ETag='"new-version"'), now=NOW + 1)
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn("If-None-Match", transport.calls[0][1])
        _, cached = self.run_with(settings, now=NOW + 2)
        self.assertEqual(cached.calls, [])
