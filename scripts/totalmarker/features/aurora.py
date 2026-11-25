"""Standalone NOAA OVATION overlay; optional, isolated Xplanet night-map handoff."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zlib

from ..aurora_status import DIR, OVERLAY, RECORD, MAX_FEED, read_record as _record
from ..errors import ConfigError, DownloadError, FeedError, StorageError
from ..http import Fetcher
from ..labels import LABEL_LIMIT, read_labels, refresh_aurora
from ..state import recover_pending

URL = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"
CURRENT = DIR + "/night-current"
COMPOSITE = DIR + "/night-composite.png"
LOCK = DIR + "/job.lock"
MAX_MAP = 128 * 1024 * 1024
WIDTH, HEIGHT = 1440, 720


@dataclass(frozen=True)
class Frame:
    observed: int
    valid: int
    grid: tuple

    @property
    def expires(self):
        return min(self.valid + 30 * 60, self.observed + 2 * 3600)


def parse(raw, now):
    def stamp(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
            raise ValueError
        return int(datetime.fromisoformat(value).timestamp())

    try:
        item = json.loads(raw)
        observed = stamp(item["Observation Time"])
        valid = stamp(item["Forecast Time"])
        rows = item["coordinates"]
        if item["Data Format"] != "[Longitude, Latitude, Aurora]" or not isinstance(rows, list) or len(rows) != 360 * 181:
            raise ValueError
        grid = [None] * len(rows)
        for lon, lat, strength in rows:
            if (any(type(value) is not int for value in (lon, lat, strength))
                    or not (0 <= lon < 360 and -90 <= lat <= 90 and 0 <= strength <= 100)):
                raise ValueError
            i = (90 - lat) * 360 + (lon + 180) % 360
            if grid[i] is not None:
                raise ValueError
            grid[i] = strength
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, RecursionError):
        raise FeedError("Invalid NOAA OVATION grid") from None
    frame = Frame(observed, valid, tuple(grid))
    if not (observed <= now + 300 and observed <= valid <= observed + 90 * 60
            and now < frame.expires):
        raise FeedError("NOAA OVATION forecast is stale or has inconsistent times")
    return frame


def encode(frame):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload)))

    grid = list(frame.grid)
    for index in (0, 180 * 360):
        grid[index:index+360] = [sum(grid[index:index+360])/360] * 360
    x = [((i + .5) * 360 / WIDTH) for i in range(WIDTH)]
    columns = [(int(v), (int(v) + 1) % 360, v - int(v)) for v in x]
    horizontal = [[grid[j*360+i]*(1-f) + grid[j*360+k]*f for i, k, f in columns]
                  for j in range(181)]
    rgba = bytearray((WIDTH * 4 + 1) * HEIGHT)
    for j in range(HEIGHT):
        y = (j + .5) * 180 / HEIGHT
        lo, f = int(y), y % 1
        for i, (a, b) in enumerate(zip(horizontal[lo], horizontal[lo+1])):
            strength = a * (1-f) + b*f
            alpha = round(118 * min(1, max(0, (strength-5)/16)) ** 1.15)
            if alpha:
                offset = j * (WIDTH*4+1) + 1 + 4*i
                rgba[offset:offset+4] = bytes((75, 240, 155, alpha))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 6, 0, 0, 0))
            + chunk(b"tEXt", f"Source\0NOAA SWPC OVATION; observation={frame.observed}; forecast={frame.valid}; expires={frame.expires}".encode("ascii"))
            + chunk(b"IDAT", zlib.compress(rgba, level=6)) + chunk(b"IEND", b""))


def _base(fs, configured):
    if not configured:
        return None, None
    resolved = fs.resolve(configured)
    if resolved.relative_to(fs.root).parts[0].casefold() not in {"images", "maps"}:
        raise ConfigError("Aurora base must be an original night map under images/ or maps/")
    info = fs.file_stat(resolved)
    if info is None or info.st_size > MAX_MAP:
        raise ConfigError("Aurora base night map is missing or too large")
    key = [str(resolved.relative_to(fs.root)), info.st_dev, info.st_ino,
           info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    return resolved, key


def _select(fs, target):
    # The renderer path is ours; never write through it or replace a regular file.
    with fs.parent(DIR + "/anchor", create=True, write=True, follow_symlinks=False) as (fd, _):
        name = Path(CURRENT).name
        try:
            mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
            if not stat.S_ISLNK(mode):
                raise StorageError("Aurora render path exists and is not a symlink")
            if os.readlink(name, dir_fd=fd) == target:
                return
        except FileNotFoundError:
            pass
        temp = ".aurora-" + uuid.uuid4().hex
        try:
            os.symlink(target, temp, dir_fd=fd)
            os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass


def _compose(base, overlay):
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory(prefix="xplanet-aurora-") as tmp:
            directory = Path(tmp)
            src, mask, dst = (directory / name for name in ("base", "overlay.png", "composite.png"))
            src.write_bytes(base)
            mask.write_bytes(overlay)
            helper = Path(__file__).with_name("aurora-composite.swift")
            try:
                subprocess.run(["/usr/bin/swift", str(helper), str(src), str(mask), str(dst)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=True, timeout=60)
                if dst.stat().st_size > MAX_MAP:
                    raise ValueError
                return dst.read_bytes()
            except (OSError, ValueError, subprocess.SubprocessError):
                raise FeedError("Could not composite the night map using macOS image tools") from None
    # Headless overlay production needs only the standard library.
    # Compositing on Linux is optional and uses the chosen interpreter's Pillow.
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(base)) as source, Image.open(BytesIO(overlay)) as mask:
            if source.width * source.height > 100_000_000:
                raise ValueError
            dest = BytesIO()
            Image.alpha_composite(source.convert("RGBA"),
                                  mask.resize(source.size, Image.Resampling.LANCZOS)
                                  ).convert("RGB").save(dest, format="PNG")
        if dest.tell() > MAX_MAP:
            raise ValueError
        return dest.getvalue()
    except ImportError:
        raise FeedError("Linux night-map compositing needs Pillow; use --overlay-only without it") from None
    except (OSError, ValueError, Image.DecompressionBombError):
        raise FeedError("Could not composite the Linux night map") from None


def _run(fs, settings, *, overlay_only=False, prepare=False, fetcher=None, now=None, compositor=_compose):
    options = settings.aurora
    now = time.time() if now is None else now
    base_name = "" if overlay_only else options.base_night_map
    if prepare and not base_name:
        raise ConfigError("Aurora --prepare needs a base_night_map")
    if not options.enabled and not base_name:
        return {"outcome": "disabled", "message": "Aurora is disabled"}
    with fs.lock(LOCK):
        base, identity = _base(fs, base_name)
        record = _record(fs)
        fresh = bool(record and record["observed_at"] <= now + 300 and now < record["expires_at"])
        overlay = fs.read(OVERLAY, MAX_FEED) if fresh else None
        fresh = bool(overlay and hashlib.sha256(overlay).hexdigest() == record["overlay_sha256"])
        # Track the actual target, but link fallback to the user's original
        # selector (not its resolved target), so normal symlink swaps still work.
        if base is not None:
            fallback = str(fs.root / base_name)
            valid_composite = (options.enabled and fresh and record.get("base") == identity
                               and record.get("composite_overlay") == record.get("overlay_sha256")
                               and fs.resolve(COMPOSITE, write=True, follow_symlinks=False).is_file())
            _select(fs, str(fs.root / COMPOSITE) if valid_composite else fallback)
        if not options.enabled:
            return {"outcome": "disabled", "message": "Aurora disabled; base night map selected"}
        if prepare:
            return {"outcome": "ready", "message": "Aurora night-map link prepared"}
        try:
            changed = False
            if not fresh or not 0 <= now - record.get("fetched_at", 0) < 240:
                reply = (fetcher if fetcher is not None else Fetcher()).fetch(URL, timeout=15, max_bytes=MAX_FEED)
                if reply.status != 200:
                    raise DownloadError("NOAA OVATION did not return HTTP 200")
                frame = parse(reply.body, now)
                if record and (frame.observed < record["observed_at"] or frame.valid < record["forecast_at"]):
                    raise FeedError("NOAA OVATION forecast went backward")
                mask = encode(frame)
                digest = hashlib.sha256(mask).hexdigest()
                if digest != record.get("overlay_sha256") or not fresh:
                    fs.write(OVERLAY, mask, follow_symlinks=False)
                    changed = True
                record.update(schema=1, observed_at=frame.observed, forecast_at=frame.valid,
                              expires_at=frame.expires, overlay_sha256=digest, fetched_at=int(now))
                overlay = mask
            if base is not None:
                if (record.get("base") != identity
                        or record.get("composite_overlay") != record["overlay_sha256"]
                        or not fs.resolve(COMPOSITE, write=True, follow_symlinks=False).is_file()):
                    _select(fs, fallback)
                    base_bytes = fs.read(base, MAX_MAP)
                    if base_bytes is None:
                        raise FeedError("Aurora base map disappeared during refresh")
                    result = compositor(base_bytes, overlay)
                    if not result.startswith(b"\x89PNG\r\n\x1a\n") or len(result) > MAX_MAP:
                        raise FeedError("Aurora compositor did not produce a bounded PNG")
                    if _base(fs, base_name)[1] != identity:
                        raise FeedError("Aurora base map changed during refresh; retry")
                    fs.write(COMPOSITE, result, follow_symlinks=False)
                    changed = True
                    record.update(base=identity, composite_overlay=record["overlay_sha256"])
                # Save validity before directing a running renderer to the candidate.
                fs.write(RECORD, json.dumps(record).encode("utf-8"), follow_symlinks=False)
                _select(fs, str(fs.root / COMPOSITE))
            else:
                fs.write(RECORD, json.dumps(record).encode("utf-8"), follow_symlinks=False)
            outcome = "changed" if changed else "unchanged"
            message = "NOAA aurora forecast ready" if changed else "Unchanged NOAA aurora forecast retained"
        except (DownloadError, FeedError) as error:
            outcome, message = "failed", str(error)
        fields = {k: record[k] for k in ("observed_at", "forecast_at", "expires_at") if k in record}
        return {"outcome": outcome, "message": message, **fields}


def run(fs, settings, *, overlay_only=False, prepare=False, fetcher=None, now=None,
        compositor=_compose):
    now = time.time() if now is None else now
    result = _run(fs, settings, overlay_only=overlay_only, prepare=prepare,
                  fetcher=fetcher, now=now, compositor=compositor)
    write_label = (settings.labels_enabled and not overlay_only
                   and (not prepare or not settings.aurora.enabled))
    write_log = settings.log and not prepare and result["outcome"] != "disabled"
    if write_label or write_log:
        with fs.lock(settings.lock):
            if write_label:
                recover_pending(fs, settings)
                old = read_labels(fs, settings.labels)
                label = refresh_aurora(fs, old, settings, now, append=True)
                raw = label.encode("utf-8")
                if len(raw) > LABEL_LIMIT:
                    raise StorageError("Label output exceeds its size limit")
                if label != old:
                    fs.write(settings.labels, raw)
            if write_log:
                fs.append(settings.log, (json.dumps({"feature": "aurora", "time": now, **result})
                                         + "\n").encode("utf-8"))
    return result
