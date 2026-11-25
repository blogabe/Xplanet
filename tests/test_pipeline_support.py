"""Contracts shared by the otherwise independent product refreshers."""

import unittest
from unittest.mock import Mock

from totalmarker.diagnostics import append_event
from totalmarker.errors import DownloadError, StorageError
from totalmarker.http import Response, conditional_validators, store_validators
from totalmarker.labels import LABEL_LIMIT, read_labels


class PipelineSupportTests(unittest.TestCase):
    def test_label_read_is_bounded_and_preserves_valid_content(self):
        raw = "line with accent: é\r\n".encode()
        fs = Mock()
        fs.read.side_effect = [raw, None, b"\xff"]
        self.assertEqual(read_labels(fs, "markers/updatelabel"), raw.decode())
        fs.read.assert_called_once_with("markers/updatelabel", LABEL_LIMIT)
        self.assertEqual(read_labels(fs, "markers/updatelabel"), "")
        with self.assertRaisesRegex(StorageError, "Existing labels are not valid UTF-8"):
            read_labels(fs, "markers/updatelabel")

    def test_conditional_headers_and_saved_validator_updates(self):
        record = {"etag": '"v1"', "last_modified": "Mon, 30 Nov 2026 00:00:00 GMT"}
        self.assertEqual(conditional_validators(record), {
            "If-None-Match": '"v1"',
            "If-Modified-Since": "Mon, 30 Nov 2026 00:00:00 GMT",
        })
        store_validators(record, Response(304, {}, b""))
        self.assertIn("last_modified", record)
        store_validators(record, Response(200, {"etag": '"v2"'}, b""))
        self.assertEqual(record, {"etag": '"v2"'})
        with self.assertRaisesRegex(StorageError, "Invalid stored HTTP validator"):
            conditional_validators({"etag": "bad\nvalue"})
        with self.assertRaisesRegex(DownloadError, "custom error"):
            store_validators(record, Response(304, {"etag": "bad\nvalue"}, b""),
                             invalid_message="custom error")
        self.assertEqual(record, {"etag": '"v2"'})

    def test_log_failure_is_reported_without_replacing_product_event(self):
        fs = Mock()
        event = {"feature": "quake", "outcome": "unchanged"}
        self.assertTrue(append_event(fs, "logs/events.jsonl", event))
        fs.append.assert_called_once_with(
            "logs/events.jsonl", b'{"feature": "quake", "outcome": "unchanged"}\n')
        fs.append.side_effect = StorageError("no space")
        self.assertFalse(append_event(fs, "logs/events.jsonl", event))
