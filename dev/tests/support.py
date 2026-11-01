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

PROJECT = Path(__file__).resolve().parents[2]
TEMP = PROJECT / "dev" / "tests" / ".tmp"


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

def stub_display_process(scripts):
    """Stub desktop process control in shell tests; no native host inspection.

    Real lifecycle policy is covered with an injected API in test_display_process.
    These fixtures exercise shell routing, map catch-up and rebuild orchestration.
    """
    shutil.copy2(PROJECT / 'scripts/run-totalmarker', scripts / 'run-totalmarker')
    helper = scripts / 'lib/xplanet/display_process.py'
    helper.write_text(r'''import json, os, subprocess, sys
from pathlib import Path
root, mode = Path(sys.argv[1]), sys.argv[2]
argv = sys.argv[3:]
is_update = 'TM_RUNNING_PIDS' in os.environ
state = Path(os.environ.get('TM_RUNNING_PIDS') or os.environ.get('MOCK_PROCESS_TABLE') or str(root / '.state/mockprocess.json'))
state.parent.mkdir(parents=True, exist_ok=True)
table = json.loads(state.read_text()) if state.exists() else {}
if os.environ.get('MOCK_PGREP_ERROR') == '1' or os.environ.get('TM_PGREP_FAIL') == '1':
    print('could not inspect desktop process identity', file=sys.stderr)
    raise SystemExit(2)
if isinstance(table, list):
    desktop = json.loads(os.environ.get('TM_DESKTOP_PIDS', json.dumps(table)))
else:
    desktop = [pid for pid, kind in table.items() if kind not in ('preview', 'other')]
if mode == 'status':
    if desktop: print('\n'.join(map(str, desktop)))
    raise SystemExit(0)
if desktop and mode == 'start':
    if sys.stdout.isatty(): print('Xplanet display already running; use restart to replace it.')
    raise SystemExit(0)
if mode == 'restart':
    denied = os.environ.get('TM_KILL_FAIL') == '1' or os.environ.get('MOCK_KILL_EXIT', '0') != '0'
    if denied:
        print('could not stop desktop', file=sys.stderr); raise SystemExit(2)
    if os.environ.get('MOCK_STAY_RUNNING') == '1':
        print('Xplanet desktop is still running after stop', file=sys.stderr); raise SystemExit(2)
    for pid in desktop:
        trace = os.environ.get('TM_EVENT_TRACE') or os.environ.get('MOCK_KILL_TRACE')
        if trace:
            with open(trace, 'a') as stream: stream.write(('TERM ' if is_update else '-TERM ') + str(pid) + '\n')
        if isinstance(table, list): table.remove(pid)
        else: table.pop(str(pid), None)
    state.write_text(json.dumps(table))
result = subprocess.run(argv, check=False).returncode
if not result:
    if not is_update:
        table['909'] = 'desktop'
        state.write_text(json.dumps(table))
    if sys.stdout.isatty(): print('Xplanet display running.' if mode == 'restart' else 'Xplanet display started.')
raise SystemExit(result)
''')

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
if args[0] == 'list':
    label = args[1]
    if label == os.environ.get('TM_LIST_FAIL_LABEL') or label not in state: raise SystemExit(3)
    doc = state[label]
    # launchctl list LABEL emits an OpenStep-style dictionary, not XML/JSON.
    q = json.dumps
    values = ['"Label" = ' + q(doc['Label']) + ';',
              '"Program" = ' + q(doc['ProgramArguments'][0]) + ';',
              '"ProgramArguments" = (' + '; '.join(q(v) for v in doc['ProgramArguments']) + ';);',
              '"WorkingDirectory" = ' + q(doc['WorkingDirectory']) + ';',
              '"PID" = 123;', '"LastExitStatus" = 0;']
    env = doc.get('EnvironmentVariables', {})
    if env:
        values.append('"EnvironmentVariables" = {' + ''.join(q(k) + ' = ' + q(v) + ';' for k, v in env.items()) + '};')
    if os.environ.get('TM_LIST_OMIT_SETTINGS') == '1':
        values = [value for value in values if not value.startswith(('"WorkingDirectory"', '"EnvironmentVariables"'))]
    print('{' + ''.join(values) + '};')
    raise SystemExit(0)
raise SystemExit(4)
''')
    path.chmod(0o700)
