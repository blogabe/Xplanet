"""Finite provider refresh budgets cover blocking network work and release locks."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
import threading
import time
from unittest.mock import patch

from totalmarker import http
from totalmarker.errors import DownloadError
from totalmarker.features.clouds import run as run_clouds
from totalmarker.health import check, exit_status
from .support import Sandbox, ScriptedTransport, image_response


@contextmanager
def server(mode):
    observed = {name: threading.Event() for name in
                ('request', 'headers_complete', 'body', 'body_complete')}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                observed['request'].set()
                if mode == 'headers':
                    # No socket inactivity occurs during DNS or header parsing
                    # that the normal body-read test could otherwise cover.
                    time.sleep(3)
                observed['headers_complete'].set()
                self.send_response(200)
                self.send_header('Content-Length', '80')
                self.end_headers()
                observed['body'].set()
                for _ in range(80):
                    self.wfile.write(b'x')
                    self.wfile.flush()
                    time.sleep(0.03)
                observed['body_complete'].set()
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=instance.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    worker.start()
    try:
        yield 'http://127.0.0.1:' + str(instance.server_port) + '/data', observed
    finally:
        instance.shutdown()
        instance.server_close()
        worker.join(timeout=2)


def blocked_dns_command(marker):
    command = http._worker_command()
    code = command.index('-c') + 1
    command[code] = (
        'import socket, time\n'
        'from pathlib import Path\n'
        'def blocked_resolver(*args, **kwargs):\n'
        f'    Path({str(marker)!r}).write_text("resolver entered")\n'
        '    time.sleep(5)\n'
        '    return []\n'
        'socket.getaddrinfo = blocked_resolver\n' + command[code])
    return command


class DeadlineTests(Sandbox):
    @contextmanager
    def workers(self):
        created = []
        original = subprocess.Popen
        def launch(*args, **kwargs):
            process = original(*args, **kwargs)
            created.append(process)
            return process
        with patch('totalmarker.http.subprocess.Popen', side_effect=launch):
            yield created
        self.assertTrue(created)
        for process in created:
            self.assertIsNotNone(process.poll(), 'network child was not reaped')
            self.assertTrue(process.stdin.closed)
            self.assertTrue(process.stdout.closed)

    def test_budget_bounds_and_shared_redirect_and_multifetch_budget(self):
        self.assertEqual([http.refresh_budget(value) for value in (1, 30, 300)], [60, 120, 300])
        clock = [0]
        class TimedTransport(ScriptedTransport):
            def request(self, *args):
                result = super().request(*args)
                clock[0] += 4
                return result
        transport = TimedTransport(http.Response(302, {'location': '/next'}),
                                   http.Response(200, {}, b'first'),
                                   http.Response(200, {}, b'too late'))
        with patch('totalmarker.http.time.monotonic', side_effect=lambda: clock[0]), \
                patch('totalmarker.http.refresh_budget', return_value=10):
            fetcher = http.Fetcher(transport)
            self.assertEqual(fetcher.fetch('https://example.invalid/first').body, b'first')
            self.assertEqual(clock[0], 8)
            with self.assertRaisesRegex(DownloadError, 'total network time budget'):
                fetcher.fetch('https://example.invalid/second', timeout=300)
            with self.assertRaisesRegex(DownloadError, 'total network time budget'):
                fetcher.fetch('https://example.invalid/third')
        self.assertEqual(len(transport.calls), 3)

    def test_worker_deadline_covers_trickling_body_and_slow_headers(self):
        for mode in ('body', 'headers'):
            with self.subTest(mode=mode), server(mode) as (url, observed), self.workers():
                start = time.monotonic()
                with self.assertRaisesRegex(DownloadError, 'total network time budget'):
                    http.HTTPTransport().request(url, {}, 2, 1024, deadline=start + 1.5)
                self.assertTrue(observed['request'].is_set(), 'worker never reached response headers')
                if mode == 'body':
                    self.assertTrue(observed['body'].is_set(), 'worker never reached response body')
                    self.assertFalse(observed['body_complete'].is_set())
                else:
                    self.assertFalse(observed['headers_complete'].is_set())
                self.assertLess(time.monotonic() - start, 2.8)

    def test_worker_deadline_covers_blocked_name_resolution(self):
        marker = self.base / 'deadline-dns-entered'
        command = blocked_dns_command(marker)
        with patch('totalmarker.http._worker_command', return_value=command), self.workers():
            start = time.monotonic()
            with self.assertRaisesRegex(DownloadError, 'total network time budget'):
                http.HTTPTransport().request('https://dns.example.invalid/', {}, 2, 1024,
                                             deadline=start + 1.5)
            self.assertEqual(marker.read_text(), 'resolver entered')
            self.assertLess(time.monotonic() - start, 2.8)

    def test_blocked_worker_self_exits_when_its_parent_guard_no_longer_matches(self):
        marker = self.base / 'parent-guard-dns-entered'
        command = blocked_dns_command(marker)
        start = time.monotonic()
        request = json.dumps({'url': 'https://dns.example.invalid/', 'headers': {},
                              'timeout': 5, 'max_bytes': 1024, 'deadline': start + 5,
                              'parent_pid': -1}).encode()
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
        try:
            output, _ = process.communicate(request, timeout=1.5)
            self.assertEqual(process.returncode, 124)
            self.assertEqual(output, b'')
            self.assertEqual(marker.read_text(), 'resolver entered')
            self.assertLess(time.monotonic() - start, 1.5)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdin.close()
            process.stdout.close()

    def test_parent_transport_keeps_tls_setup_inside_supervised_worker(self):
        with patch('totalmarker.http.ssl.create_default_context', side_effect=AssertionError('parent TLS')):
            transport = http.HTTPTransport()
            self.assertIsNone(transport._context)
            self.assertIsNone(transport._opener)

    def test_parent_interrupt_kills_reaps_and_closes_worker_without_secret_output(self):
        original = subprocess.Popen
        processes = []
        def launch(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            process.communicate = lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt())
            return process
        with patch('totalmarker.http.subprocess.Popen', side_effect=launch):
            with self.assertRaises(KeyboardInterrupt):
                http.HTTPTransport().request('https://example.invalid/DUMMY_SECRET',
                                             {'Authorization': 'Basic DUMMY_SECRET'}, 2, 1024)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdin.closed)
        self.assertTrue(processes[0].stdout.closed)

    def test_expired_refresh_records_failure_preserves_image_and_releases_product_lock(self):
        settings = self.config('CloudCheckIntervalSeconds=0\n')
        initial = run_clouds(self.fs, settings,
                             fetcher=http.Fetcher(ScriptedTransport(image_response())), now=1700000100)
        self.assertEqual(initial.outcome, 'changed')
        before = self.read_state(settings)['products']['clouds']
        image = self.fs.read(settings.image)
        with server('body') as (url, observed):
            class LoopbackTransport(http.HTTPTransport):
                def request(self, source, headers, timeout, max_bytes, **kwargs):
                    return super().request(url, headers, timeout, max_bytes, **kwargs)
            with patch('totalmarker.http.refresh_budget', return_value=1.5), self.workers():
                result = run_clouds(self.fs, settings, fetcher=http.Fetcher(LoopbackTransport()),
                                    now=1700000200)
        self.assertTrue(observed['body'].is_set(), 'worker never reached the response body')
        self.assertFalse(observed['body_complete'].is_set())
        self.assertEqual(result.outcome, 'failed')
        self.assertEqual(result.message, http.DEADLINE_ERROR)
        record = self.read_state(settings)['products']['clouds']
        self.assertEqual(record['successful_at'], before['successful_at'])
        self.assertEqual(record['attempted_at'], 1700000200)
        self.assertEqual(record['last_error']['message'], http.DEADLINE_ERROR)
        self.assertEqual(self.fs.read(settings.image), image)
        self.assertEqual(exit_status(check(self.fs, settings, now=1700000200)), 1)
        with self.fs.lock(settings.lock, timeout=0.1):
            pass
