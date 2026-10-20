import base64
from dataclasses import replace
import io
import ssl
from urllib.error import HTTPError
from unittest.mock import patch

from totalmarker.config import load
from totalmarker.errors import ConfigError, DownloadError, StorageError
from totalmarker.http import Fetcher, HTTPTransport, Response
from .support import Sandbox, ScriptedTransport


class ConfigurationTests(Sandbox):
    def test_default_is_xeric_and_missing_credentials_fail_safely(self):
        settings = load(self.fs)
        self.assertEqual(settings.provider, "xeric")
        self.assertEqual(settings.url,
                         "https://secure.xericdesign.com/xplanet/clouds/4096/clouds-4096.jpg")
        with self.assertRaisesRegex(DownloadError, "authentication is missing"):
            settings.auth.resolve({})

    def test_flat_legacy_ini_plaintext_and_unrelated_options_are_preserved(self):
        settings = self.config("CloudUserName=DUMMY_LEGACY_USER\n"
                               "CloudPassword=DUMMY_LEGACY_PASSWORD\n"
                               "CloudResolution=2048\nQuakeMinimumSize=6\n", custom=False)
        before = (self.root / "config.ini").read_bytes()
        self.assertEqual(settings.auth.resolve({}),
                         ("DUMMY_LEGACY_USER", "DUMMY_LEGACY_PASSWORD"))
        self.assertEqual(settings.unrelated["quakeminimumsize"], "6")
        self.assertEqual((self.root / "config.ini").read_bytes(), before)
        self.assertNotIn("DUMMY_LEGACY_PASSWORD", repr(settings))
        self.assertNotIn("DUMMY_LEGACY_USER", repr(settings))

    def test_custom_does_not_reuse_xeric_or_legacy_secrets(self):
        settings = self.config("CloudUsername=DUMMY_XERIC_USER\n"
                               "CloudPassword=DUMMY_XERIC_PASSWORD\n"
                               "XericUsername=DUMMY_SPECIFIC_USER\n"
                               "XericPassword=DUMMY_SPECIFIC_PASSWORD\n")
        self.assertEqual(settings.auth.mode, "none")
        self.assertIsNone(settings.auth.resolve({}))

    def test_custom_plaintext_credentials_are_independent(self):
        settings = self.config("CustomUsername=DUMMY_CUSTOM_USER\n"
                               "CustomPassword=DUMMY_CUSTOM_PASSWORD\n")
        self.assertEqual(settings.auth.resolve({}),
                         ("DUMMY_CUSTOM_USER", "DUMMY_CUSTOM_PASSWORD"))
        self.assertNotIn("DUMMY_CUSTOM_PASSWORD", repr(settings))

    def test_optional_environment_references(self):
        settings = self.config("CustomUsernameEnv=DUMMY_USER_ENV\n"
                               "CustomPasswordEnv=DUMMY_PASS_ENV\n")
        self.assertEqual(settings.auth.resolve({"DUMMY_USER_ENV": "DUMMY_USER",
                                                "DUMMY_PASS_ENV": "DUMMY_PASSWORD"}),
                         ("DUMMY_USER", "DUMMY_PASSWORD"))
        with self.assertRaises(DownloadError):
            settings.auth.resolve({})

    def test_conflicting_auth_sources_rejected(self):
        with self.assertRaises(ConfigError):
            self.config("CustomUsername=DUMMY_USER\nCustomUsernameEnv=DUMMY_USER_ENV\n")
        with self.assertRaises(ConfigError):
            self.config("CloudAuthMode=none\nCustomPassword=DUMMY_PASSWORD\n")

    def test_urls_and_bad_settings_are_rejected_without_echo(self):
        from totalmarker.config import https_url
        for url in ["http://example.invalid/a.jpg",
                    "https://DUMMY_USER:DUMMY_PASSWORD@example.invalid/a.jpg",
                    "https://example.invalid/a.jpg?token=DUMMY_TOKEN",
                    "https://example.invalid/a.jpg#fragment",
                    "https://example.invalid/\nAuthorization"]:
            with self.assertRaises(ConfigError) as error:
                https_url(url)
            self.assertNotIn("DUMMY", str(error.exception))
        for values in ["CloudResolution=123\n", "CloudAuthMode=none\n"]:
            with self.assertRaises(ConfigError):
                self.config(values, custom=False)
        for values in ["LabelWarningCloud=-1\n", "CloudTimeoutSeconds=0\n",
                       "LabelColorOk=Green injected\n", "CloudOutput=../escape.jpg\n"]:
            with self.assertRaises((ConfigError, StorageError)):
                self.config(values)

    def test_outputs_cannot_collide_or_overwrite_references(self):
        with self.assertRaises(ConfigError):
            self.config("StateFile=markers/updatelabel\n")
        with self.assertRaises(StorageError):
            self.config("CloudOutput=dev/reference/original.jpg\n")

    def test_safe_toml_examples_load_without_rewriting(self):
        from .support import PROJECT
        for path in sorted((PROJECT / "dev" / "examples").glob("*.example.toml")):
            with self.subTest(example=path.name):
                raw = path.read_bytes()
                (self.root / "example.toml").write_bytes(raw)
                settings = load(self.fs, "example.toml")
                self.assertEqual((self.root / "example.toml").read_bytes(), raw)
                if settings.provider == "xeric":
                    self.assertEqual(settings.auth.mode, "basic")
                    with self.assertRaisesRegex(DownloadError, "authentication is missing"):
                        settings.auth.resolve({})
                else:
                    self.assertTrue(settings.url.startswith("https://cloud.example.invalid/"))


class FetchTests(Sandbox):
    def test_verified_tls_context(self):
        transport = HTTPTransport()
        self.assertTrue(transport.context.check_hostname)
        self.assertEqual(transport.context.verify_mode, ssl.CERT_REQUIRED)

    def test_basic_auth_stays_on_exact_origin(self):
        transport = ScriptedTransport(
            Response(302, {"Location": "/second.jpg"}),
            Response(302, {"Location": "https://cdn.example.invalid/map.jpg"}),
            Response(200, {}, b"test"))
        Fetcher(transport).fetch("https://cloud.example.invalid/map.jpg",
                                credentials=("DUMMY_USER", "DUMMY_PASSWORD"))
        expected = "Basic " + base64.b64encode(b"DUMMY_USER:DUMMY_PASSWORD").decode()
        self.assertEqual(transport.calls[0][1]["Authorization"], expected)
        self.assertEqual(transport.calls[1][1]["Authorization"], expected)
        self.assertNotIn("Authorization", transport.calls[2][1])

    def test_port_change_drops_auth(self):
        transport = ScriptedTransport(Response(302, {
            "Location": "https://cloud.example.invalid:444/map.jpg"}), Response(200, {}))
        Fetcher(transport).fetch("https://cloud.example.invalid/map.jpg",
                                credentials=("DUMMY_USER", "DUMMY_PASSWORD"))
        self.assertNotIn("Authorization", transport.calls[1][1])

    def test_downgrade_and_credential_redirects_rejected(self):
        for target in ["http://example.invalid/map.jpg",
                       "https://DUMMY_USER:DUMMY_PASSWORD@example.invalid/map.jpg"]:
            transport = ScriptedTransport(Response(302, {"Location": target}))
            with self.assertRaises(DownloadError) as error:
                Fetcher(transport).fetch("https://cloud.example.invalid/map.jpg")
            self.assertNotIn("DUMMY", str(error.exception))
            self.assertEqual(len(transport.calls), 1)

    def test_errors_timeouts_and_redaction(self):
        for status in [401, 403, 404, 429, 500, 503]:
            transport = ScriptedTransport(Response(status, {}, b"DUMMY_SECRET_ERROR_BODY"))
            with self.assertRaises(DownloadError) as error:
                Fetcher(transport).fetch("https://cloud.example.invalid/map.jpg")
            self.assertIn(str(status), str(error.exception))
            self.assertNotIn("DUMMY", str(error.exception))
        transport = ScriptedTransport(TimeoutError("DUMMY_SECRET_FROM_TRANSPORT"))
        with self.assertRaisesRegex(DownloadError, "^HTTPS request failed$"):
            Fetcher(transport).fetch("https://cloud.example.invalid/map.jpg")

    def test_http_error_logs_only_bounded_allowlisted_diagnostics(self):
        body = (b'<html><h1>Access denied</h1> Error 1020 '
                b'https://private.example.invalid/path?token=DUMMY_URL_TOKEN '
                b'Cookie: DUMMY_COOKIE Authorization: DUMMY_AUTH</html>')
        headers = {"Server": "cloudflare", "Date": "Mon, 19 Oct 2026 09:00:00 GMT",
                   "Content-Type": "text/html; charset=utf-8", "CF-Ray": "abc123-SFO",
                   "Set-Cookie": "DUMMY_COOKIE", "Authorization": "DUMMY_AUTH",
                   "Location": "https://private.example.invalid/?token=DUMMY_URL_TOKEN",
                   "X-Request-ID": "DUMMY_SECRET_ID"}
        wire_error = HTTPError("https://private.example.invalid/?token=DUMMY_URL_TOKEN",
                               403, "Forbidden", headers, io.BytesIO(body))
        transport = HTTPTransport()
        with patch.object(transport.opener, "open", side_effect=wire_error):
            response = transport.request("https://cloud.example.invalid/map.jpg", {}, 1, 10000)
        self.assertEqual(response.status, 403)
        self.assertLessEqual(len(response.body), 4096)
        with self.assertRaises(DownloadError) as error:
            Fetcher(ScriptedTransport(response)).fetch("https://cloud.example.invalid/map.jpg")
        message = str(error.exception)
        for part in ("HTTP 403", "reason=Forbidden", "server=cloudflare",
                     "date=Mon, 19 Oct 2026 09:00:00 GMT", "content-type=text/html",
                     "cf-ray=abc123-SFO", "excerpt=Access denied, Error 1020"):
            self.assertIn(part, message)
        for secret in ("DUMMY", "private.example", "Location", "Set-Cookie", "Authorization"):
            self.assertNotIn(secret, message)
        self.assertLess(len(message), 350)

    def test_error_sample_limits_and_nontext_or_untrusted_values_are_omitted(self):
        transport = HTTPTransport()
        large = HTTPError("https://cloud.example.invalid/map.jpg", 503, "Service Unavailable",
                          {"Content-Type": "text/plain"}, io.BytesIO(b"Access denied " + b"x" * 10000))
        with patch.object(transport.opener, "open", side_effect=large):
            response = transport.request("https://cloud.example.invalid/map.jpg", {}, 1, 10000)
        self.assertEqual(len(response.body), 4096)
        small = HTTPError("https://cloud.example.invalid/map.jpg", 503, "Service Unavailable",
                          {"Content-Type": "text/plain"}, io.BytesIO(b"Access denied " * 100))
        with patch.object(transport.opener, "open", side_effect=small):
            response = transport.request("https://cloud.example.invalid/map.jpg", {}, 1, 16)
        self.assertEqual(len(response.body), 16)
        nontext = HTTPError("https://cloud.example.invalid/map.jpg", 403, "Forbidden",
                            {"Content-Type": "application/octet-stream"},
                            io.BytesIO(b"Access denied DUMMY_BINARY_SECRET"))
        with patch.object(transport.opener, "open", side_effect=nontext):
            response = transport.request("https://cloud.example.invalid/map.jpg", {}, 1, 10000)
        self.assertEqual(response.body, b"")
        bad = Response(403, {"Server": "cloudflare DUMMY_PASSWORD",
                             "Content-Type": "text/html; token=DUMMY_HEADER",
                             "CF-Ray": "DUMMY_SECRET_ID", "X-Request-ID": "x" * 200},
                       b"<h1>Access denied</h1> DUMMY_BODY_SECRET", "Forbidden DUMMY_REASON")
        with self.assertRaises(DownloadError) as error:
            Fetcher(ScriptedTransport(bad)).fetch("https://cloud.example.invalid/map.jpg")
        self.assertEqual(str(error.exception),
                         "Source returned HTTP 403; content-type=text/html; excerpt=Access denied")

    def test_redirect_limit_and_validator_injection(self):
        transport = ScriptedTransport(*[Response(302, {"Location": "/loop"}) for _ in range(6)])
        with self.assertRaisesRegex(DownloadError, "Too many"):
            Fetcher(transport).fetch("https://cloud.example.invalid/map.jpg")
        with self.assertRaises(DownloadError):
            Fetcher(ScriptedTransport()).fetch(
                "https://cloud.example.invalid/map.jpg",
                validators={"If-None-Match": "bad\r\nAuthorization: DUMMY"})

    def test_transport_checks_length_and_size(self):
        class Wire:
            status = 200
            def __init__(self, body, length):
                self.headers = {"Content-Length": str(length)}
                self.body = body
            def read(self, size): return self.body[:size]
            def __enter__(self): return self
            def __exit__(self, *args): pass
        for body, length, limit in [(b"x", 2, 100), (b"x" * 11, 11, 10)]:
            transport = HTTPTransport()
            with patch.object(transport.opener, "open", return_value=Wire(body, length)):
                with self.assertRaises(DownloadError):
                    transport.request("https://cloud.example.invalid/map.jpg", {}, 1, limit)

    def test_response_and_settings_representations_do_not_reveal_sensitive_fields(self):
        response = Response(200, {"Authorization": "Basic DUMMY_HEADER"},
                            b"DUMMY_SECRET_BODY")
        self.assertNotIn("DUMMY", repr(response))
        settings = self.config("CustomUsername=DUMMY_USER\nCustomPassword=DUMMY_PASSWORD\n")
        self.assertNotIn(settings.url, repr(settings))
        self.assertNotIn("DUMMY", repr(settings))
