"""Synthetic narrative repetitions derived from an already-public source fixture."""
import unittest
from totalmarker.errors import FeedError
from totalmarker.storm_advisory import parse_advisory
from .support import PROJECT

SOURCE=PROJECT/'tests/fixtures/storm/live-20261105-slash-reissue/jtwc-abio-advisory.txt'

class AdvisoryRepetitionTests(unittest.TestCase):
    def setUp(self):
        self.raw=SOURCE.read_bytes()
        self.end=self.raw.rindex(b'      (2) NO OTHER SUSPECT AREAS.')
    def repeated(self,code=b'94S'):
        return (self.raw[:self.end]+b'MODELS CONTINUE TO TRACK INVEST '+code+
                b'. INVEST '+code+b' REMAINS ACTIVE.\r\n'+self.raw[self.end:])
    def test_repeated_same_identity_retains_exact_original_storm(self):
        original=parse_advisory(self.raw,'abio')
        result=parse_advisory(self.repeated(),'abio')
        self.assertEqual(result,original)
        self.assertEqual([item.id for item in result.invests],['SH942027'])
    def test_distinct_identity_in_same_paragraph_still_refuses(self):
        with self.assertRaisesRegex(FeedError,'one basin-valid invest code'):
            parse_advisory(self.repeated(b'93S'),'abio')
    def test_wrong_basin_remains_rejected(self):
        with self.assertRaisesRegex(FeedError,'one basin-valid invest code'):
            parse_advisory(self.repeated().replace(b'94S',b'94W'),'abio')
    def test_duplicate_disturbance_records_remain_rejected(self):
        start=self.raw.rindex(b'      (1) THE AREA OF CONVECTION')
        paragraph=self.raw[start:self.end].replace(b'(1)',b'(2)',1)
        raw=self.raw[:self.end]+paragraph+self.raw[self.end:].replace(b'(2) NO OTHER',b'(3) NO OTHER',1)
        with self.assertRaisesRegex(FeedError,'advisory repeats an invest code'):
            parse_advisory(raw,'abio')
