"""Publication must not create journals its recovery path cannot read."""
from totalmarker.errors import StorageError
from totalmarker.state import (MarkerPublisher, PairPublisher, Publisher,
                               StormPublisher, load_state, recover_pending)
from .support import Sandbox


class PublicationBoundsTests(Sandbox):
    def test_escaped_label_exceeds_journal_limit_before_any_write(self):
        settings = self.config()
        state = load_state(self.fs, settings.state)
        # UTF-8 fits the label reader, but JSON escaping expands it over 4 MiB.
        label = "😀" * 350_000
        publishers = (
            (Publisher(self.fs, settings), settings.journal,
             lambda publisher: publisher.publish(state, label)),
            (MarkerPublisher(self.fs, settings, "quake"), settings.quake.journal,
             lambda publisher: publisher.publish(state, label)),
            (StormPublisher(self.fs, settings), settings.storm.journal,
             lambda publisher: publisher.publish(state, label)),
            (PairPublisher(self.fs, settings, "eclipse", settings.eclipse.marker,
                           settings.eclipse.arc, "marker_sha256", "arc_sha256"),
             settings.eclipse.journal,
             lambda publisher: publisher.publish(state, label)),
        )
        for publisher, journal, publish in publishers:
            with self.subTest(publisher=type(publisher).__name__):
                with self.assertRaisesRegex(StorageError, "journal.*size limit"):
                    publish(publisher)
                self.assertIsNone(self.fs.read(journal))
        self.assertIsNone(self.fs.read(settings.state))
        self.assertIsNone(self.fs.read(settings.labels))
        recover_pending(self.fs, settings)
        Publisher(self.fs, settings).publish(state, "short\n")
        self.assertEqual(self.fs.read(settings.labels), b"short\n")

    def test_state_bound_is_checked_before_journal_write(self):
        settings = self.config()
        state = load_state(self.fs, settings.state)
        state["products"]["future"] = {"large": "x" * (2 * 1024 * 1024)}
        with self.assertRaisesRegex(StorageError, "state exceeds"):
            StormPublisher(self.fs, settings).publish(state, "short\n")
        self.assertIsNone(self.fs.read(settings.storm.journal))
        self.assertIsNone(self.fs.read(settings.state))
