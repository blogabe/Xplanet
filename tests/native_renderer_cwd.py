"""Explicit finite native-render check; never changes a desktop or real config.

Run with PYTHONPATH=scripts:. python3 -B -m tests.native_renderer_cwd /path/to/xplanet
This is separate from the offline suite, which uses stub renderers.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
import zlib

from .support import copy_launcher


def solid_png(color):
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))
    width, height = 16, 8
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + bytes(color) * width) * height))
            + chunk(b"IEND", b""))


def verify(renderer):
    if not renderer.is_absolute() or not renderer.is_file() or not os.access(renderer, os.X_OK):
        raise ValueError("renderer must be an absolute executable file")
    with tempfile.TemporaryDirectory(prefix="xplanet-native-cwd-", dir="/tmp") as temporary:
        base = Path(temporary).resolve()
        root = base / "selected checkout"
        caller = base / "other checkout"
        for directory in (root / "scripts", root / "config", root / "images", caller,
                          base / "home", base / "scratch", base / "cache"):
            directory.mkdir(parents=True)
        wrapper = root / "scripts/xplanet.sh"
        copy_launcher(wrapper)
        # Pin time for labels/ephemerides without changing cwd or resource args.
        fixed_renderer = root / "scripts/fixed-date-renderer"
        fixed_renderer.write_text("#!/bin/sh\nexec " + shlex.quote(str(renderer))
                                  + ' -date 20261107.000000 "$@"\n')
        fixed_renderer.chmod(0o700)
        config = root / "config/xp.conf"
        config.write_text("[default]\nshade=100\n[earth]\nmap=cwd-collision.png\n")
        (root / "config/xp.def").write_text(
            "XPLANET_BIN=" + shlex.quote(str(fixed_renderer)) + "\n"
            "XPLANET_HOME=" + shlex.quote(str(root)) + "\n"
            "XPLANET_CONFIG=" + shlex.quote(str(root / "config")) + "\n"
            "XPLANET_PROJECTION=rectangular\nXPLANET_LONGITUDE=0\n"
            "XPLANET_GEOMETRY=160x80\n")
        selected = root / "images/cwd-collision.png"
        selected.write_bytes(solid_png((230, 30, 20)))
        collision = caller / "cwd-collision.png"
        collision.write_bytes(solid_png((20, 30, 230)))
        inputs = {path: path.read_bytes() for path in
                  (config, root / "config/xp.def", selected, collision)}
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(base / "home"),
                       "TMPDIR": str(base / "scratch"), "XDG_CACHE_HOME": str(base / "cache"),
                       "LC_ALL": "C"}

        def run(arguments, cwd):
            result = subprocess.run(arguments, cwd=cwd, env=environment,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(f"native render failed ({result.returncode}): {result.stderr}")

        # Show that this binary really exhibits cwd-first lookup, so matching
        # wrapper output is evidence of the fix rather than an inert fixture.
        controls = []
        for label, cwd in (("selected", root), ("collision", caller)):
            output = base / (label + ".png")
            run([str(fixed_renderer), "-body", "earth", "-searchdir", str(root),
                 "-config", str(config), "-projection", "rectangular", "-longitude", "0",
                 "-labelpos", "+10-45", "-date_format", "%D at %r", "-color", "green2",
                 "-geometry", "160x80", "-output", str(output),
                 "-tmpdir", str(base / "scratch"), "-num_times", "1"], cwd)
            controls.append(output.read_bytes())
        if controls[0] == controls[1]:
            raise AssertionError("native control did not distinguish the colliding maps")

        for command, filename in (("preview", "earth-manual.png"), ("render", "earth-render.png")):
            output = root / "output/preview" / filename
            run([str(wrapper), command], root)
            expected = output.read_bytes()
            run([str(wrapper), command], caller)
            actual = output.read_bytes()
            if actual != expected:
                raise AssertionError(command + " used the caller's colliding resource")
            if command == "render" and actual != controls[0]:
                raise AssertionError("render does not match the selected-map native control")
            print(command + ": selected checkout map from both cwd values; sha256="
                  + hashlib.sha256(actual).hexdigest())
        for path, original in inputs.items():
            if path.read_bytes() != original:
                raise AssertionError("input changed: " + str(path))
        print("Native controls distinguish collisions; all fixture inputs unchanged.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("renderer", type=Path)
    args = parser.parse_args()
    verify(args.renderer)


if __name__ == "__main__":
    main()
