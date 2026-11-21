"""Opt-in, offline, finite ISS and NASA central-path pixel checks.

PYTHONPATH=scripts:. python3 -B -m tests.native_renderer_overlays /absolute/xplanet
Uses the existing historical public ISS example and attributed NASA capture.
No live requests, desktop operations, installed config, or extra dependencies.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import zlib

from totalmarker.config import load
from totalmarker.features import eclipse, norad
from totalmarker.http import Fetcher, Response
from totalmarker.paths import RootFS
from .native_renderer_cwd import solid_png
from .support import ScriptedTransport
from .test_norad import SAMPLE, EPOCH
from .test_eclipse_nasa_capture import ANNULAR_URL, FIXTURES


def pixels(path):
    """Decode native 8-bit RGB/RGBA noninterlaced PNG without Pillow."""
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    at, packed = 8, b''
    while at < len(raw):
        size = struct.unpack('>I', raw[at:at + 4])[0]
        kind, data = raw[at + 4:at + 8], raw[at + 8:at + 8 + size]
        if kind == b'IHDR':
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            assert (depth, compression, filtering, interlace) == (8, 0, 0, 0)
            assert color in (2, 6)
            channels = 3 if color == 2 else 4
        elif kind == b'IDAT':
            packed += data
        at += size + 12
    raw = zlib.decompress(packed)
    stride = width * channels
    assert len(raw) == (stride + 1) * height
    previous, result = bytearray(stride), []
    for y in range(height):
        start = y * (stride + 1)
        kind, row = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        assert kind in range(5)
        for i in range(stride):
            a, b = (row[i - channels] if i >= channels else 0), previous[i]
            c = previous[i - channels] if i >= channels else 0
            p = a + b - c
            distances = [abs(p - a), abs(p - b), abs(p - c)]
            paeth = (a, b, c)[distances.index(min(distances))]
            row[i] = (row[i] + (0, a, b, (a + b) // 2, paeth)[kind]) % 256
        result.extend(tuple(row[i:i + 3]) for i in range(0, stride, channels))
        previous = row
    return width, height, result


def verify(renderer):
    if not renderer.is_absolute() or not renderer.is_file() or not os.access(renderer, os.X_OK):
        raise ValueError('renderer must be an absolute executable file')
    with tempfile.TemporaryDirectory(prefix='xplanet-native-overlays-', dir='/tmp') as temporary:
        root = Path(temporary).resolve()
        for name in ('home', 'scratch', 'images', 'satellites'):
            (root / name).mkdir()
        (root / 'images/map.png').write_bytes(solid_png((80, 80, 80)))
        (root / 'config.toml').write_text('[cloud]\nprovider="custom"\nurl="https://unused.invalid/map"\n[norad]\nenabled=true\ncatalog_ids="25544"\ncolor="Magenta"\n[eclipse]\nenabled=true\n')
        fs = RootFS(root)
        settings = load(fs, 'config.toml')
        transport = ScriptedTransport(Response(200, {}, SAMPLE))
        outcome = norad.run(fs, settings, fetcher=Fetcher(transport), now=EPOCH)
        assert outcome.outcome == 'changed' and outcome.count == 1
        assert len(transport.calls) == 1
        assert fs.read(settings.norad.satellite + '.tle').splitlines()[1:] == SAMPLE.splitlines()[1:]
        path = eclipse.parse_path((FIXTURES / '2027-02-06-annular.html').read_bytes(), ANNULAR_URL)
        options = replace(settings.eclipse, center_color='Cyan', edge_color='Red', notice_enabled=False)
        marker, arc = eclipse.render(path, options, path.start_at, True)
        (root / 'eclipse.marker').write_bytes(marker)
        (root / 'eclipse.arc').write_bytes(arc)
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(root / 'home'), 'TMPDIR': str(root / 'scratch'), 'LC_ALL': 'C'}

        def render(label, date, overlays=''):
            config = root / (label + '.conf')
            config.write_text('[default]\nshade=100\n[earth]\nmap=map.png\n' + overlays)
            output = root / (label + '.png')
            command = [str(renderer), '-body', 'earth', '-projection', 'rectangular', '-longitude', '0',
                       '-geometry', '720x360', '-date', date, '-searchdir', str(root), '-config', str(config),
                       '-output', str(output), '-tmpdir', str(root / 'scratch'), '-num_times', '1']
            run = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
            assert run.returncode == 0, run.stderr
            assert not run.stderr.strip(), run.stderr
            width, height, data = pixels(output)
            assert (width, height) == (720, 360)
            return data

        date = datetime.fromtimestamp(EPOCH, timezone.utc).strftime('%Y%m%d.%H%M%S')
        baseline = render('iss-off', date)
        visible = render('iss-on', date, 'satellite_file=' + str(fs.resolve(settings.norad.satellite)) + '\n')
        magenta = lambda p: p[0] > 180 and p[1] < 80 and p[2] > 180
        assert not any(map(magenta, baseline))
        count = sum(map(magenta, visible))
        assert count > 30, f'ISS overlay absent: {count} magenta pixels'
        # Disabling selector must exactly restore the original frame.
        assert render('iss-off-again', date) == baseline
        print(f'ISS 25544 at {date}: {count} distinctive magenta pixels; off/on/off passed')

        date = datetime.fromtimestamp(path.start_at, timezone.utc).strftime('%Y%m%d.%H%M%S')
        baseline = render('eclipse-off', date)
        visible = render('eclipse-on', date, f'arc_file={root}/eclipse.arc\nmarker_file={root}/eclipse.marker\n')
        cyan = lambda p: p[0] < 80 and p[1] > 180 and p[2] > 180
        red = lambda p: p[0] > 180 and p[1] < 80 and p[2] < 80
        assert not any(cyan(p) or red(p) for p in baseline)
        assert sum(map(cyan, visible)) > 50 and sum(map(red, visible)) > 50
        # A central-path sample must land near its geographic pixel, not merely
        # produce unrelated colored annotation somewhere in the frame.
        point = path.points[len(path.points) // 2].center
        lat, lon = point
        x, y = round((lon + 180) * 2), round((90 - lat) * 2)
        arcs_only = render('eclipse-arcs', date, f'arc_file={root}/eclipse.arc\n')
        assert arcs_only != visible  # time-label markers add visible pixels
        assert any(cyan(arcs_only[yy * 720 + xx]) for yy in range(y - 4, y + 5)
                   for xx in range(x - 4, x + 5)), (point, x, y)
        marker, arc = eclipse.render(path, options, path.end_at + 86400, False)
        (root / 'eclipse.marker').write_bytes(marker)
        (root / 'eclipse.arc').write_bytes(arc)
        assert render('eclipse-inactive', date, f'arc_file={root}/eclipse.arc\nmarker_file={root}/eclipse.marker\n') == baseline
        print(f'NASA annular central path {path.date}: center and limits visible at expected location; inactive equals baseline')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('renderer', type=Path)
    verify(parser.parse_args().renderer)
