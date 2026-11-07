from pathlib import Path
import os
import select
import shutil
import struct
import sys
import tempfile
import time
import unittest

from totalmarker.config import load
from totalmarker.http import Fetcher, Response
from totalmarker.paths import RootFS

PROJECT = Path(__file__).resolve().parents[1]


def copy_launcher(destination):
    """Copy the checkout CLI and its private macOS workflows into a sandbox."""
    shutil.copy2(PROJECT / "scripts/xplanet.sh", destination)
    shutil.copytree(PROJECT / "scripts/lib", destination.parent / "lib", dirs_exist_ok=True)


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


class SandboxFixture:
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name).resolve()
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


def prepare_fixture(owner, fixture_class):
    """Build a plain fixture whose resources belong to the calling test."""
    fixture=fixture_class()
    fixture.addCleanup=owner.addCleanup
    fixture.setUp()
    return fixture


class Sandbox(SandboxFixture, unittest.TestCase):
    pass


def stub_desktop_launchctl(scripts, binaries):
    """A fixture launchd owns only fixture processes; never invokes host launchctl."""
    runtime=binaries/'lifecycle-runtime';runtime.mkdir(mode=0o700,exist_ok=True)
    getconf=binaries/'getconf';getconf.write_text('#!/bin/sh\nprintf "%s\\n" '+__import__('shlex').quote(str(runtime.resolve()))+'\n');getconf.chmod(0o700)
    path = binaries / 'launchctl'
    path.write_text('#!' + sys.executable + '\n' + r'''import json, os, plistlib, subprocess, sys
from pathlib import Path
args=sys.argv[1:]
state=Path(__file__).with_suffix('.json')
doc=json.loads(state.read_text()) if state.exists() else None
if os.environ.get('MOCK_LAUNCHCTL_TRACE'):
    with open(os.environ['MOCK_LAUNCHCTL_TRACE'],'a') as stream: stream.write(' '.join(args)+'\n')
if args[0] in ('list','print'):
    if doc and args[0]=='print':
        print('path = '+doc['_path'])
        print('program = '+doc['ProgramArguments'][0])
        print('working directory = '+doc['WorkingDirectory'])
        print('arguments = {')
        print('\n'.join(doc['ProgramArguments']))
        print('}')
    raise SystemExit(0 if doc else 113)
if args[0]=='bootstrap':
    if doc: raise SystemExit(5)
    doc=plistlib.loads(Path(args[2]).read_bytes())
    doc['_path']=args[2]
    state.write_text(json.dumps(doc)); raise SystemExit(0)
if args[0]=='bootout':
    if os.environ.get('MOCK_BOOTOUT_FAIL')=='1': raise SystemExit(5)
    state.unlink(missing_ok=True); raise SystemExit(0)
if args[0]=='kickstart':
    if not doc: raise SystemExit(3)
    tablefile=os.environ.get('MOCK_PROCESS_TABLE')
    table=json.loads(Path(tablefile).read_text()) if tablefile else {}
    if not doc.get('_running') or (tablefile and '909' not in table):
        subprocess.run(doc['ProgramArguments'], check=False)
        doc['_running']=True; state.write_text(json.dumps(doc))
        if tablefile:
            table['909']='desktop'; Path(tablefile).write_text(json.dumps(table))
    raise SystemExit(0)
raise SystemExit(4)
''')
    path.chmod(0o700)

def stub_launchctl(path):
    """Registered-job dictionaries and load state live only beside this stub."""
    path.write_text('#!' + sys.executable + '\n' + r'''import json, os, plistlib, sys
from pathlib import Path
args = sys.argv[1:]
if os.environ.get('TM_LAUNCHCTL_CALLS'):
    with open(os.environ['TM_LAUNCHCTL_CALLS'], 'a') as stream: stream.write(' '.join(args) + '\n')
state_file = Path(__file__).with_suffix('.json')
state = json.loads(state_file.read_text()) if state_file.exists() else {}
if args[:2] == ['load', '-w']:
    doc = plistlib.loads(Path(args[2]).read_bytes())
    state[doc['Label']] = doc
    state_file.write_text(json.dumps(state))
    raise SystemExit(0)
if args[0] in ('list', 'print'):
    label = args[1].rsplit('/', 1)[-1]
    if label == os.environ.get('TM_LIST_FAIL_LABEL') or label not in state: raise SystemExit(3)
    if args[0] == 'list':raise SystemExit('setup must inspect explicit GUI-domain status')
    print('service = ' + label)
    raise SystemExit(0)
raise SystemExit(4)
''')
    path.chmod(0o700)
