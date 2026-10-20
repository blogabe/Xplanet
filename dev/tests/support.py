from pathlib import Path
import os
import select
import struct
import tempfile
import time
import unittest

from totalmarker.config import load
from totalmarker.http import Fetcher, Response
from totalmarker.paths import RootFS

PROJECT = Path(__file__).resolve().parents[2]
TEMP = PROJECT / "dev" / "tests" / ".tmp"


def wait_for_prompt(process, phrase, timeout=5):
    """Wait until an isolated shell fixture is blocked at a named prompt."""
    streams = [process.stdout, process.stderr]
    seen = b""
    deadline = time.monotonic() + timeout
    while phrase not in seen and streams and time.monotonic() < deadline:
        ready, _, _ = select.select(streams, [], [], max(0, deadline - time.monotonic()))
        for stream in ready:
            chunk = os.read(stream.fileno(), 4096)
            if chunk:
                seen += chunk
            else:
                streams.remove(stream)
    if phrase not in seen:
        raise AssertionError(f"shell did not reach prompt {phrase!r}: {seen[-300:]!r}")
CREATED_COMMENT = b"EarthDesk Cloud Image Created Tue Nov 14 22:13:20 UTC 2023"


def jpeg(comment=None, *, width=2, height=1):
    """A complete 2x1 baseline grayscale JPEG with one constant DCT block."""
    if comment is None:
        comment = CREATED_COMMENT
    def segment(marker, payload):
        return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload
    tables = (b"\x00" + b"\x01" + b"\x00" * 15 + b"\x00"
              + b"\x10" + b"\x01" + b"\x00" * 15 + b"\x00")
    blocks = ((width + 7) // 8) * ((height + 7) // 8)
    bits = blocks * 2
    entropy = bytes(bits // 8) + (bytes([(1 << (8 - bits % 8)) - 1]) if bits % 8 else b"")
    return (b"\xff\xd8" + (segment(0xFE, comment) if comment else b"")
            + segment(0xDB, b"\x00" + b"\x01" * 64)
            + segment(0xC0, b"\x08" + struct.pack(">HHB", height, width, 1) + b"\x01\x11\x00")
            + segment(0xC4, tables)
            + segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
            + entropy + b"\xff\xd9")


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, url, headers, timeout, max_bytes):
        self.calls.append((url, dict(headers)))
        if not self.responses:
            raise AssertionError("Unexpected transport call")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def image_response(comment=None, **headers):
    return Response(200, {"Content-Type": "image/jpeg", **headers}, jpeg(comment))


class Sandbox(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "sandbox"
        self.root.mkdir()
        self.fs = RootFS(self.root)

    def config(self, extra="", *, custom=True):
        text = ("CloudProvider=custom\nCloudURL=https://cloud.example.invalid/map.jpg\n"
                if custom else "") + extra
        (self.root / "config.ini").write_text(text)
        return load(self.fs, "config.ini")

    def read_state(self, settings):
        import json
        return json.loads(self.fs.read(settings.state))
