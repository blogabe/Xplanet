"""Screen hints are bounded, read-only and independent of native scene defaults."""
import json
import subprocess
import unittest
from unittest.mock import patch

from configurator.display_geometry import detect,parse,SCRIPT
from configurator.geometry import DEFAULT_GEOMETRY
from configurator.model import View


def report(pixels=(3840,2160),points=(1920,1080)):
    return {'pixels':list(pixels),'points':list(points)}


class DisplayGeometryTests(unittest.TestCase):
    def test_retina_points_are_not_mistaken_for_backing_pixels(self):
        hint=parse(json.dumps([report()]))
        self.assertEqual(hint.default,'3840x2160')
        self.assertIn('3840x2160 backing pixels (1920x1080 points)',hint.description)
        self.assertEqual(View().geometry,DEFAULT_GEOMETRY)

    def test_primary_display_wins_over_larger_secondary_and_portrait_is_preserved(self):
        hint=parse(json.dumps([report((1080,1920),(1080,1920)),report((5120,2880))]))
        self.assertEqual(hint.default,'1080x1920')
        self.assertIn('display 2 5120x2880',hint.description)

    def test_oversized_primary_has_visible_fallback_without_silent_scaling(self):
        hint=parse(json.dumps([report((6016,3384),(3008,1692))]))
        self.assertEqual(hint.default,DEFAULT_GEOMETRY)
        self.assertIn('6016x3384',hint.description)
        self.assertIn('exceeds preview limits',hint.description)

    def test_malformed_ambiguous_and_unbounded_reports_are_refused(self):
        bad=[[],{},[None],[{'pixels':[1,2]}],[report((True,1080))],
             [report((0,1080))],[report((1920.5,1080))],
             [report((float('nan'),1080))],[report((float('inf'),1080))],
             [report((131073,1080))],[report()]*33]
        for value in bad:
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)):
                parse(json.dumps(value))
        for raw in (b'not JSON',b'\xff',b' '*16385):
            with self.assertRaises(ValueError):parse(raw)

    def test_probe_is_absolute_bounded_and_not_a_renderer_or_service(self):
        with patch('configurator.display_geometry.sys.platform','darwin'),patch(
                'configurator.display_geometry.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps([report()]).encode())) as run:
            self.assertEqual(detect().default,'3840x2160')
        args,kwargs=run.call_args
        self.assertEqual(args[0],['/usr/bin/osascript','-l','JavaScript','-e',SCRIPT])
        self.assertEqual(kwargs['timeout'],2)
        self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
        self.assertNotIn('shell',kwargs)

    def test_failed_or_headless_probe_falls_back_and_nonmac_does_not_spawn(self):
        with patch('configurator.display_geometry.sys.platform','linux'),patch('configurator.display_geometry.subprocess.run') as run:
            self.assertEqual(detect().default,DEFAULT_GEOMETRY);run.assert_not_called()
        for error in (OSError(),subprocess.TimeoutExpired('probe',2),subprocess.CalledProcessError(1,'probe')):
            with patch('configurator.display_geometry.sys.platform','darwin'),patch('configurator.display_geometry.subprocess.run',side_effect=error):
                self.assertIn('unavailable',detect().description)
        with patch('configurator.display_geometry.sys.platform','darwin'),patch('configurator.display_geometry.subprocess.run',return_value=subprocess.CompletedProcess([],0,b'[]')):
            self.assertEqual(detect().default,DEFAULT_GEOMETRY)
