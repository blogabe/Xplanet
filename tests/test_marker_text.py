"""Provider labels cannot escape Xplanet's literal quote parser."""
import json
import unittest
from dataclasses import replace

from totalmarker.config import load_bytes, QuakeOptions, VolcanoOptions
from totalmarker.errors import ConfigError, FeedError
from totalmarker.marker_text import encode_marker_lines, rgb_color_key, transparency_option
from .support import Sandbox
from totalmarker.marker_text import quoted_label
from totalmarker.quake_geojson import _quoted as quake_quote
from totalmarker.volcano_cap import _quoted as volcano_quote
from totalmarker.storm_model import _quote as storm_quote

class MarkerTextTests(unittest.TestCase):
    def test_every_producer_uses_literal_engine_safe_labels(self):
        raw='Place " color=Red image=/private/file \\ line\nnext\x1b'
        expected='"Place \' color=Red image=/private/file / line next "'
        for quote in (quoted_label,quake_quote,volcano_quote,storm_quote):
            with self.subTest(producer=quote):
                self.assertEqual(quote(raw),expected)
                self.assertEqual(quote(raw).count('"'),2)
                self.assertNotIn('\\',quote(raw))


class MarkerConfigurationTests(Sandbox):
    def test_ini_and_native_toml_rgb_triplets_are_canonical_without_rewriting(self):
        for raw in ("{0,255,12}", "0,255,12", " { 000 , 255 , 012 } "):
            for product in ("quake", "volcano", "storm"):
                key = product.title() + "ImageTransparent"
                ini = (key + "=" + raw + "\n").encode()
                toml = (f"[{product}]\nimage_transparent = " + json.dumps(raw) + "\n").encode()
                for payload, name in ((ini, "config.ini"), (toml, "config.toml")):
                    with self.subTest(product=product, raw=raw, syntax=name):
                        settings = load_bytes(self.fs, payload, name)
                        self.assertEqual(getattr(settings, product).image_transparent, "{0,255,12}")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_scalar_and_invalid_color_keys_are_refused_with_actionable_guidance(self):
        for product in ("quake", "volcano", "storm"):
            key = product.title() + "ImageTransparent"
            for raw in ("30", "0", "255", "50%", "{0,0}", "{0,0,256}", "{-1,0,0}",
                        "{0.0,0,0}", "{true,0,0}", "{٠,0,0}", "{0,0,0", "0,0,0}",
                        "{0,0,0} image=other.png", "{0,0,\n0}"):
                payload = (f"[{product}]\nimage_transparent = " + json.dumps(raw) + "\n").encode()
                with self.subTest(product=product, raw=raw), self.assertRaises(ConfigError) as error:
                    load_bytes(self.fs, payload, "config.toml")
                self.assertIn(key, str(error.exception))
                self.assertIn("RGB color key", str(error.exception))
                self.assertIn("scalar opacity values are unsupported", str(error.exception))
                self.assertIn("leave this setting empty", str(error.exception))
            with self.subTest(product=product), self.assertRaises(ConfigError) as error:
                load_bytes(self.fs, (key + "=30\n").encode(), "config.ini")
            self.assertIn("RGB color key", str(error.exception))
        settings = load_bytes(self.fs, b'', "config.ini")
        self.assertTrue(all(getattr(settings, name).image_transparent == ""
                            for name in ("quake", "volcano", "storm")))

    def test_color_key_emission_has_no_scalar_opacity_interpretation(self):
        self.assertEqual(transparency_option("0, 128, 255"), " transparent={0,128,255}")
        self.assertEqual(transparency_option(""), "")
        for invalid in ("30", "{0,0,999}", True, 30, (0, 0, 0)):
            with self.subTest(invalid=invalid), self.assertRaises(FeedError):
                transparency_option(invalid)
        self.assertEqual(rgb_color_key("{ 0, 128, 255 }"), "{0,128,255}")

    def test_line_limit_counts_encoded_bytes_and_preserves_content_at_boundary(self):
        for text in ("x" * 510, "é" * 255):
            with self.subTest(text=text[:5]):
                self.assertEqual(encode_marker_lines([text, 'next']), (text + '\nnext\n').encode())
        for text in ("x" * 511, "é" * 256, "first\nsecond", "first\rsecond"):
            with self.subTest(text=text[:5]), self.assertRaisesRegex(FeedError, "510-byte limit"):
                encode_marker_lines([text, 'next'])
        self.assertEqual(encode_marker_lines([]), b'\n')

    def test_every_emitter_refuses_unvalidated_scalar_options(self):
        from totalmarker.quake_geojson import render_body as quake_body, parse_geojson
        from totalmarker.volcano_cap import render_body as volcano_body, parse_cap
        from totalmarker.storm_model import render_bodies, StormStyle
        from .test_quake import feed, feature
        from .test_volcano import synthetic_info
        from .test_storm_model import snapshot, sample_storm, REQUIRED
        calls = [lambda: quake_body(parse_geojson(feed(feature()), 6)[0],
                                    replace(QuakeOptions(), image="quake.png", image_transparent="30")),
                 lambda: volcano_body(parse_cap(synthetic_info()),
                                      replace(VolcanoOptions(), image="volcano.png", image_transparent="30")),
                 lambda: render_bodies(snapshot(sample_storm()),
                                       replace(StormStyle(), image="storm.png", image_transparent="30"),
                                       required_groups=REQUIRED)]
        for emit in calls:
            with self.subTest(emit=emit), self.assertRaisesRegex(FeedError, "RGB color key"):
                emit()

    def test_impossible_detail_templates_fail_at_load_in_ini_and_toml(self):
        for product in ('quake', 'volcano', 'storm'):
            key = product.title() + 'DetailList'
            for detail in ('x' * 600, 'é' * 260):
                for data, name in (((key + '=' + detail + '\n').encode(), 'config.ini'),
                                   ((f'[{product}]\ndetail = ' + json.dumps(detail)).encode(), 'config.toml')):
                    with self.subTest(product=product, detail=detail[:3], syntax=name), \
                         self.assertRaisesRegex(ConfigError, key + '.*510-byte'):
                        load_bytes(self.fs, data, name)

    def test_static_detail_boundary_includes_utf8_coordinates_and_style(self):
        for product, suffix in (('quake', ' color=Red align=Above'),
                                ('volcano', ' color=Brown align=Below image=none'),
                                ('storm', ' align=Below color=SkyBlue')):
            budget = 510 - len(('   0.00    0.00 ""' + suffix).encode())
            for detail in ('x' * budget, 'é' * (budget // 2) + 'x' * (budget % 2)):
                data = (f'[{product}]\ndetail = ' + json.dumps(detail)).encode()
                settings = load_bytes(self.fs, data, 'config.toml')
                self.assertEqual(getattr(settings, product).detail, detail)
                with self.assertRaisesRegex(ConfigError, '510-byte'):
                    load_bytes(self.fs, (f'[{product}]\ndetail = ' + json.dumps(detail + 'x')).encode(), 'config.toml')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_placeholder_minimums_and_storm_image_overhead_are_counted(self):
        for product, detail in (('quake', '<date>' * 50), ('volcano', '<lat>' * 70),
                                ('storm', '<long>' * 70)):
            with self.subTest(product=product), self.assertRaisesRegex(ConfigError, '510-byte'):
                load_bytes(self.fs, (f'[{product}]\ndetail = ' + json.dumps(detail)).encode(), 'config.toml')
        payload = b'[storm]\ndetail = "' + b'x' * 440 + b'"\nimage = "storm.png"\nimage_transparent = "{0,0,0}"'
        with self.assertRaisesRegex(ConfigError, 'StormDetailList.*510-byte'):
            load_bytes(self.fs, payload, 'config.toml')

    def test_possible_variable_detail_keeps_runtime_guard(self):
        from totalmarker.quake_geojson import render_body, parse_geojson
        from .test_quake import feed, feature
        settings = load_bytes(self.fs, b'[quake]\ndetail = "<location>"', 'config.toml')
        events, _ = parse_geojson(feed(feature()), 6)
        events = [replace(events[0], place='é' * 260)]
        with self.assertRaisesRegex(FeedError, '510-byte'):
            render_body(events, settings.quake)
