"""Verified HTTPS, explicit redirects and origin-scoped Basic authentication."""
import base64
from dataclasses import dataclass, field
from datetime import timezone
from email.utils import parsedate_to_datetime, format_datetime
from html import unescape
import http.client
import json
import os
from pathlib import Path
from http import HTTPStatus
import re
import socket
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import (build_opener, HTTPRedirectHandler, HTTPSHandler,
                            ProxyHandler, Request)

from .config import https_url
from .errors import ConfigError, DownloadError


@dataclass
class Response:
    status: int
    headers: dict = field(repr=False)
    body: bytes = field(default=b"", repr=False)
    reason: str = field(default="", repr=False)


ERROR_SAMPLE_LIMIT = 4096
TEXT_ERRORS = {"text/plain", "text/html", "application/xhtml+xml",
               "application/json", "application/problem+json"}
REQUEST_IDS = ("cf-ray", "x-request-id", "x-correlation-id", "x-amz-request-id",
               "x-amzn-requestid", "x-ms-request-id")
ERROR_PHRASES = ("Access denied", "Request blocked", "Forbidden",
                 "Too many requests", "Rate limit exceeded", "Service unavailable",
                 "Not found", "Automated requests are not permitted")


def _error_sample(response, headers, max_bytes):
    content_type = headers.get("content-type", "")
    kind = content_type.split(";", 1)[0].strip().lower() if isinstance(content_type, str) else ""
    if response.status < 400 or kind not in TEXT_ERRORS:
        return b""
    limit = min(ERROR_SAMPLE_LIMIT, max_bytes)
    try:
        return response.read(limit + 1)[:limit]
    except (OSError, http.client.HTTPException, ValueError):
        return b""  # Preserve the status even when the optional excerpt cannot be read.


def _http_diagnostic(response):
    """Only fixed-format metadata and recognized error phrases enter logs."""
    status = response.status
    if not isinstance(status, int) or not 100 <= status <= 599:
        return "Source returned an invalid HTTP status"
    details = []
    try:
        standard_reason = HTTPStatus(status).phrase
    except ValueError:
        standard_reason = ""
    if isinstance(response.reason, str) and response.reason.strip() == standard_reason:
        details.append("reason=" + standard_reason)
    headers = {str(key).lower(): value for key, value in response.headers.items()}
    server = headers.get("server")
    if (isinstance(server, str) and len(server) <= 64
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._/-]*", server)
            and not re.search(r"(?i)secret|token|password|cookie|bearer|basic|session|key", server)):
        details.append("server=" + server)
    date = headers.get("date")
    if isinstance(date, str) and len(date) <= 80:
        try:
            parsed = parsedate_to_datetime(date)
            if parsed.tzinfo is not None:
                details.append("date=" + format_datetime(parsed.astimezone(timezone.utc), usegmt=True))
        except (TypeError, ValueError, OverflowError):
            pass
    kind = headers.get("content-type")
    if isinstance(kind, str):
        mime = kind.split(";", 1)[0].strip().lower()
        if re.fullmatch(r"[a-z0-9.+-]{1,40}/[a-z0-9.+-]{1,40}", mime):
            details.append("content-type=" + mime)
    for key in REQUEST_IDS:
        value = headers.get(key)
        if (isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", value)
                and not re.search(r"(?i)secret|token|password|cookie|bearer|basic|session|auth|key", value)):
            details.append(key + "=" + value)
    kind = headers.get("content-type", "")
    if (isinstance(kind, str) and kind.split(";", 1)[0].strip().lower() in TEXT_ERRORS
            and response.body):
        sample = unescape(response.body[:ERROR_SAMPLE_LIMIT].decode("utf-8", "replace"))
        sample = re.sub(r"<[^>]{0,512}>", " ", sample)
        phrases = [phrase for phrase in ERROR_PHRASES
                   if re.search(r"(?i)\b" + re.escape(phrase) + r"\b", sample)]
        code = re.search(r"(?i)\berror(?:\s+code)?\s*[:#]?\s*([0-9]{3,4})\b", sample)
        if code:
            phrases.append("Error " + code[1])
        if phrases:
            details.append("excerpt=" + ", ".join(phrases[:2]))
    return "Source returned HTTP " + str(status) + ("; " + "; ".join(details) if details else "")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


DEADLINE_ERROR = "Provider refresh exceeded its total network time budget"


def refresh_budget(timeout):
    """One provider refresh, including all requests, gets 60–300 seconds."""
    return max(60, min(300, 4 * timeout))


def _worker_command():
    # -I prevents an unrelated working directory or PYTHONPATH from injecting
    # worker imports. -B keeps the network child from writing bytecode caches.
    # Only this installation's scripts directory is added.
    scripts = str(Path(__file__).resolve().parent.parent)
    return [sys.executable, '-I', '-B', '-c',
            'import sys; sys.path.insert(0, sys.argv[1]); '
            'from totalmarker.http import _network_worker; _network_worker()', scripts]


def _network_worker():
    """Network-only child: no paths, state, publication or provider credentials on argv."""
    import threading
    stopped = threading.Event()
    watcher = None
    try:
        request = json.loads(sys.stdin.buffer.read())
        deadline, parent_pid = request['deadline'], request['parent_pid']
        def watch_parent():
            # Parent cleanup handles normal interruption. This also bounds a
            # worker left behind by an abruptly terminated parent process.
            while not stopped.wait(min(0.25, max(0, deadline - time.monotonic()))):
                if time.monotonic() >= deadline or os.getppid() != parent_pid:
                    os._exit(124)
        watcher = threading.Thread(target=watch_parent, daemon=True)
        watcher.start()
        response = HTTPTransport()._request(request['url'], request['headers'],
                                            request['timeout'], request['max_bytes'])
        metadata = {'status': response.status, 'headers': response.headers,
                    'reason': response.reason}
        body = response.body
    except DownloadError as error:
        metadata, body = {'error': str(error)}, b''
    except Exception:
        metadata, body = {'error': 'HTTPS request failed'}, b''
    try:
        sys.stdout.buffer.write(json.dumps(metadata).encode('utf-8') + b'\n')
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()
    finally:
        stopped.set()
        if watcher is not None:
            watcher.join()


class HTTPTransport:
    def __init__(self):
        self._context = None
        self._opener = None

    @property
    def context(self):
        if self._context is None:
            self._context = ssl.create_default_context()
        return self._context

    @property
    def opener(self):
        if self._opener is None:
            self._opener = build_opener(ProxyHandler({}), HTTPSHandler(context=self.context),
                                        NoRedirect())
        return self._opener

    def request(self, url, headers, timeout, max_bytes, *, deadline=None):
        """Bound DNS, connect, headers, body and IPC by the parent's deadline.

        Socket timeouts still catch ordinary inactivity sooner. The child only
        obtains bytes; publication always stays in the locked parent process.
        """
        deadline = time.monotonic() + refresh_budget(timeout) if deadline is None else deadline
        if time.monotonic() >= deadline:
            raise DownloadError(DEADLINE_ERROR)
        payload = json.dumps({'url': url, 'headers': headers, 'timeout': timeout,
                              'max_bytes': max_bytes, 'deadline': deadline,
                              'parent_pid': os.getpid()}).encode('utf-8')
        process = None
        try:
            process = subprocess.Popen(_worker_command(), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DownloadError(DEADLINE_ERROR)
            try:
                output, _ = process.communicate(payload, timeout=remaining)
            except subprocess.TimeoutExpired:
                raise DownloadError(DEADLINE_ERROR) from None
            if time.monotonic() >= deadline or process.returncode == 124:
                raise DownloadError(DEADLINE_ERROR)
            if process.returncode != 0:
                raise DownloadError("HTTPS request failed")
            metadata, separator, body = output.partition(b'\n')
            if not separator:
                raise DownloadError("HTTPS request failed")
            result = json.loads(metadata)
            if 'error' in result:
                raise DownloadError(result['error'])
            return Response(result['status'], result['headers'], body, result['reason'])
        except DownloadError:
            raise
        except (OSError, ValueError, KeyError, TypeError):
            raise DownloadError("HTTPS request failed") from None
        finally:
            if process is not None:
                # communicate may be interrupted before it closes its pipes.
                # Kill and reap before releasing the product's shared lock.
                if process.poll() is None:
                    process.kill()
                process.wait()
                for pipe in (process.stdin, process.stdout):
                    if pipe is not None:
                        pipe.close()

    def _request(self, url, headers, timeout, max_bytes):
        """Synchronous urllib operation, run only inside the network child."""
        try:
            try:
                response = self.opener.open(Request(url, headers=headers), timeout=timeout)
            except HTTPError as response:
                status = response.code
                response_headers = {k.lower(): v for k, v in response.headers.items()}
                body = _error_sample(response, response_headers, max_bytes)
                reason = response.reason if isinstance(response.reason, str) else ""
                response.close()
                return Response(status, response_headers, body, reason)
            with response:
                status = response.status
                response_headers = {k.lower(): v for k, v in response.headers.items()}
                if status != 200:
                    return Response(status, response_headers,
                                    _error_sample(response, response_headers, max_bytes),
                                    getattr(response, "reason", ""))
                length = response_headers.get("content-length")
                if length is not None:
                    try:
                        expected = int(length)
                    except ValueError:
                        raise DownloadError("Invalid HTTP content length") from None
                    if expected < 0 or expected > max_bytes:
                        raise DownloadError("HTTP response exceeds the size limit")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise DownloadError("HTTP response exceeds the size limit")
                if length is not None and len(body) != expected:
                    raise DownloadError("HTTP response body is incomplete")
                return Response(status, response_headers, body)
        except DownloadError:
            raise
        except (URLError, OSError, socket.timeout, http.client.HTTPException, ValueError):
            # Exception strings can contain URLs, headers or credential data.
            raise DownloadError("HTTPS request failed") from None


def origin(url):
    parsed = urlsplit(url)
    return parsed.hostname.lower(), parsed.port or 443


def safe_header(value):
    return isinstance(value, str) and len(value) <= 1024 and not any(
        ord(c) < 32 or ord(c) == 127 for c in value)


class Fetcher:
    def __init__(self, transport=None):
        self.transport = transport if transport is not None else HTTPTransport()
        self._deadline = None

    def fetch(self, url, *, validators=None, credentials=None, timeout=30,
              max_bytes=32 * 1024 * 1024, allow_query=False):
        if self._deadline is None:
            self._deadline = time.monotonic() + refresh_budget(timeout)
        initial = https_url(url, allow_query=allow_query)
        current = initial
        validators = validators or {}
        for _ in range(6):
            headers = {"User-Agent": "TotalMarker-Python/0.1", "Accept-Encoding": "identity"}
            for key, value in validators.items():
                if key not in {"If-Modified-Since", "If-None-Match"} or not safe_header(value):
                    raise DownloadError("Invalid stored HTTP validator")
                headers[key] = value
            if credentials is not None and origin(current) == origin(initial):
                user, password = credentials
                encoded = base64.b64encode((user + ":" + password).encode("utf-8")).decode()
                headers["Authorization"] = "Basic " + encoded
            try:
                if time.monotonic() >= self._deadline:
                    raise DownloadError(DEADLINE_ERROR)
                if isinstance(self.transport, HTTPTransport):
                    response = self.transport.request(current, headers, timeout, max_bytes,
                                                      deadline=self._deadline)
                else:
                    # Injected offline transports remain synchronous. Their
                    # elapsed time still counts across requests and redirects.
                    response = self.transport.request(current, headers, timeout, max_bytes)
                if time.monotonic() >= self._deadline:
                    raise DownloadError(DEADLINE_ERROR)
            except DownloadError:
                raise
            except Exception:
                raise DownloadError("HTTPS request failed") from None
            response.headers = {key.lower(): value for key, value in response.headers.items()}
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location:
                    raise DownloadError("HTTPS redirect lacks a destination")
                try:
                    current = https_url(urljoin(current, location), allow_query=allow_query)
                except ConfigError:
                    raise DownloadError("HTTPS redirect destination was rejected") from None
                continue
            if response.status not in {200, 304}:
                raise DownloadError(_http_diagnostic(response))
            if len(response.body) > max_bytes:
                raise DownloadError("HTTP response exceeds the size limit")
            return response
        raise DownloadError("Too many HTTPS redirects")
