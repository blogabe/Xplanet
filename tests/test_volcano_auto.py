"""Automatic volcano selection, source-specific validators and last-good retention."""
from totalmarker.config import VolcanoOptions
from totalmarker.errors import ConfigError
from totalmarker.features.volcano import run, source_urls
from totalmarker.http import Fetcher, Response
from totalmarker.volcano_weekly import WEEKLY_URL
from .support import Sandbox, ScriptedTransport
from .test_volcano import cap_response, synthetic_info
from .test_volcano_weekly import NOW, weekly_html


CAP_URL = VolcanoOptions.url
CAP = synthetic_info(period="8 October-14 October 2026")
WEEKLY = Response(200, {"content-type": "text/html", "etag": '"weekly"'}, weekly_html())


class AutomaticVolcanoTests(Sandbox):
    def auto(self):
        return self.toml_config('[volcano]\nprovider = "auto"\ncheck_interval_hours = 0\n')

    def run_with(self, settings, transport, now=NOW):
        return run(self.fs, settings, fetcher=Fetcher(transport), now=now)

    def test_cap_success_does_not_contact_weekly(self):
        settings = self.auto()
        transport = ScriptedTransport(cap_response(CAP))
        result = self.run_with(settings, transport)
        self.assertEqual((result.outcome, result.provider), ("changed", "cap"))
        self.assertEqual([url for url, _ in transport.calls], [CAP_URL])
        self.assertEqual(source_urls(settings.volcano), [CAP_URL, WEEKLY_URL])

    def test_fallback_checks_once_and_scopes_all_conditional_headers(self):
        settings = self.auto()
        first = ScriptedTransport(cap_response(CAP, etag='"cap"'))
        self.assertEqual(self.run_with(settings, first).provider, "cap")
        fallback = ScriptedTransport(Response(403, {}), WEEKLY)
        result = self.run_with(settings, fallback, NOW + 1)
        self.assertEqual((result.outcome, result.provider, result.report_period_end),
                         ("changed", "weekly_html", "2026-10-14"))
        self.assertIn("cap: Source returned HTTP 403", result.message)
        self.assertEqual([url for url, _ in fallback.calls], [CAP_URL, WEEKLY_URL])
        self.assertEqual(fallback.calls[0][1]["If-None-Match"], '"cap"')
        self.assertNotIn("If-None-Match", fallback.calls[1][1])
        recheck = ScriptedTransport(Response(503, {}), Response(304, {}))
        self.assertEqual(self.run_with(settings, recheck, NOW + 2).outcome, "unchanged")
        self.assertNotIn("If-None-Match", recheck.calls[0][1])
        self.assertEqual(recheck.calls[1][1]["If-None-Match"], '"weekly"')
        recovered = ScriptedTransport(cap_response(CAP, etag='"cap-new"'))
        self.assertEqual(self.run_with(settings, recovered, NOW + 3).provider, "cap")
        self.assertEqual(len(recovered.calls), 1)
        self.assertNotIn("If-None-Match", recovered.calls[0][1])

    def test_bad_primary_can_fall_back_but_older_or_broken_result_preserves_last_good(self):
        settings = self.auto()
        good = ScriptedTransport(cap_response(CAP))
        self.assertEqual(self.run_with(settings, good).outcome, "changed")
        markers = self.fs.read(settings.volcano.marker)
        for response in (
            Response(503, {}),
            Response(200, {"content-type": "text/html"}, weekly_html(period="1 October-7 October 2026")),
        ):
            with self.subTest(response=response.status):
                transport = ScriptedTransport(cap_response(b"invalid XML"), response)
                result = self.run_with(settings, transport, NOW + 1)
                self.assertEqual((result.outcome, result.successful_at), ("failed", NOW))
                self.assertEqual([url for url, _ in transport.calls], [CAP_URL, WEEKLY_URL])
                self.assertIn("cap:", result.message)
                self.assertIn("weekly_html:", result.message)
                self.assertEqual(self.fs.read(settings.volcano.marker), markers)

    def test_rate_limit_auth_and_pinned_sources_do_not_fall_back(self):
        for provider, status, url in (
            ("auto", 401, CAP_URL), ("auto", 429, CAP_URL),
            ("cap", 403, CAP_URL), ("weekly_html", 403, WEEKLY_URL),
        ):
            with self.subTest(provider=provider, status=status):
                settings = self.toml_config(f'[volcano]\nprovider = "{provider}"\n')
                t = ScriptedTransport(Response(status, {"retry-after": "3600"}))
                self.assertEqual(self.run_with(settings, t).outcome, "failed")
                self.assertEqual([requested for requested, _ in t.calls], [url])

    def test_disabled_and_custom_url_modes(self):
        settings = self.toml_config('[volcano]\nprovider = "auto"\nenabled = false\n')
        transport = ScriptedTransport()
        self.assertEqual(self.run_with(settings, transport).outcome, "disabled")
        self.assertEqual(transport.calls, [])
        self.assertEqual(source_urls(settings.volcano), [])
        with self.assertRaisesRegex(ConfigError, "custom volcano URL"):
            self.toml_config('[volcano]\nprovider = "auto"\nurl = "https://custom.test/report"\n')
        explicit = self.toml_config('[volcano]\nprovider = "cap"\nurl = "https://custom.test/report"\n')
        self.assertEqual(source_urls(explicit.volcano), ["https://custom.test/report"])
