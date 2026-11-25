"""Official JTWC advisory with a wrapped geographic qualifier."""

import hashlib
import json
from pathlib import Path
import unittest

from totalmarker.errors import FeedError
from totalmarker.storm_advisory import parse_advisory


FIXTURE = Path(__file__).parent / "fixtures/storm/live-20261125-wrapped-basin"
WRAP = b"COAST OF \r\nAFRICA):"


class WrappedBasinTests(unittest.TestCase):
    def test_published_advisory_retains_both_basins_and_invests(self):
        raw = (FIXTURE / "abioweb.txt").read_bytes()
        source = json.loads((FIXTURE / "source.json").read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
        self.assertIn(WRAP, raw)
        advisory = parse_advisory(raw, "abio")
        north, south = advisory.areas
        self.assertEqual((north.name, south.name), ("NORTH INDIAN OCEAN AREA", "SOUTH INDIAN OCEAN AREA"))
        self.assertTrue(north.cyclone_none)
        self.assertEqual(north.invests, ())
        self.assertEqual(len(south.invests), 2)

    def test_bad_wrapping_does_not_turn_incomplete_data_into_an_empty_basin(self):
        raw = (FIXTURE / "abioweb.txt").read_bytes()
        for fragment in (b"COAST OF \r\nAFRICA:", b"COAST OF \r\nTHE \r\nAFRICA):"):
            with self.subTest(fragment=fragment), self.assertRaisesRegex(FeedError, "both expected basin areas"):
                parse_advisory(raw.replace(WRAP, fragment, 1), "abio")
        with self.assertRaisesRegex(FeedError, "both expected basin areas"):
            parse_advisory(raw.replace(b"2. SOUTH INDIAN OCEAN AREA", b"2. UNKNOWN OCEAN AREA"), "abio")
