"""Incomplete fields remain reportable without making them valid."""
import sys
import unittest
from configurator.model import View
from configurator.workspace import configuration_issues

class DraftSummaryTests(unittest.TestCase):
    def test_invalid_planet_shadow_reports_blocking_health_without_crashing(self):
        for target in ('mars', 'moon', 'jupiter'):
            for raw in ('', '-', 'nan', 'inf', 'not a number'):
                with self.subTest(target=target, raw=raw):
                    view=View.from_fields({'target':target, 'planet_shade':raw})
                    self.assertIn('invalid', view.appearance_summary())
                    self.assertTrue(any(issue.severity=='blocking' for issue in configuration_issues(view, sys.executable)))
