"""Manual, conservative cleanup of positively identified macOS wallpaper copies."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import stat
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

CACHE = (
    "Library/Containers/com.apple.wallpaper.agent/Data/Library/Caches/"
    "com.apple.wallpaper.caches/extension-com.apple.wallpaper.extension.image"
)
GALLERY = (
    "Library/Containers/com.apple.wallpaper.extension.image/Data/Library/"
    "Preferences/com.apple.wallpaper.extension.image.plist"
)
PNG_CACHE = str(Path(GALLERY).parent.parent / "Caches")
INDEX = "Library/Application Support/com.apple.wallpaper/Store/Index.plist"
IMAGE_PROVIDER = "com.apple.wallpaper.choice.image"
NAME = re.compile(r"([a-f0-9]{64})-[0-9]+-[0-9]+-[0-9]+-[a-f0-9]{16}\.bmp")
PNG_NAME = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\.png")
TOKEN = r"Xplanet\.[a-zA-Z0-9]{6}"
MIN_AGE = 24 * 60 * 60
OPEN_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def digest(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def directory(home, relative):
    """Open without following any symlink below the resolved home."""
    fd = os.open(home, OPEN_DIR)
    try:
        for part in Path(relative).parts:
            child = os.open(part, OPEN_DIR, dir_fd=fd)
            os.close(fd)
            fd = child
            if os.fstat(fd).st_uid != os.getuid():
                raise ValueError("wallpaper directory is not owned by the current user")
        yield fd
    finally:
        os.close(fd)


def read_plist(home, relative):
    path = Path(relative)
    with directory(home, path.parent) as parent:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(path.name, flags, dir_fd=parent), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("wallpaper index is not a user-owned regular file")
            data = stream.read(32 * 1024 * 1024 + 1)
            if len(data) > 32 * 1024 * 1024:
                raise ValueError("wallpaper index is too large to inspect safely")
    return plistlib.loads(data), digest(data)


def path_value(value):
    if not isinstance(value, str):
        return None
    if value.startswith("file://"):
        url = urlsplit(value)
        if url.netloc or url.query or url.fragment:
            return None
        value = unquote(url.path, errors="strict")
    if not value.startswith("/") or any(ord(ch) < 32 for ch in value):
        return None
    if str(Path(value)) != value or ".." in Path(value).parts:
        return None
    return value


def relative_url(value):
    return path_value(value.get("relative") if isinstance(value, dict) else value)


def gallery_rows(gallery):
    records = gallery.get("ChoiceRequests.ImageFiles")
    if records is None:
        records = gallery.get("ChoiceRequests", {}).get("ImageFiles", [])
    if isinstance(records, dict):
        records = list(records.values())
    if not isinstance(records, list):
        raise ValueError("unrecognized wallpaper gallery")
    for record in records:
        if isinstance(record, bytes):
            record = plistlib.loads(record)
        if not isinstance(record, dict):
            raise ValueError("unrecognized wallpaper gallery entry")
        original = relative_url(record.get("originalURL"))
        if original is None:
            raise ValueError("cannot verify the original image in a gallery entry")
        copy = record.get("copyURL")
        cached = relative_url(copy)
        if copy is not None and cached is None:
            raise ValueError("cannot verify the cached image in a gallery entry")
        yield original, cached


def active_paths(index):
    """Inspect every display/Space choice, rejecting unfamiliar configurations."""
    if not isinstance(index, dict) or not {"SystemDefault", "Spaces", "Displays"} <= index.keys():
        raise ValueError("unrecognized live wallpaper index")
    protected = set()
    seen_choices = False

    def inspect(node):
        nonlocal seen_choices
        if isinstance(node, list):
            for item in node:
                inspect(item)
        elif isinstance(node, dict):
            if "Choices" in node:
                choices = node["Choices"]
                if not isinstance(choices, list):
                    raise ValueError("unrecognized wallpaper choices")
                for choice in choices:
                    seen_choices = True
                    if not isinstance(choice, dict) or choice.get("Files") != []:
                        raise ValueError("unrecognized live wallpaper choice")
                    provider = choice.get("Provider")
                    if provider == "default":
                        continue
                    if provider != IMAGE_PROVIDER:
                        raise ValueError("unrecognized live wallpaper provider")
                    config = plistlib.loads(choice["Configuration"])
                    url = config.get("url")
                    path = relative_url(url)
                    if config.get("type") != "imageFile" or path is None:
                        raise ValueError("cannot resolve a live wallpaper path")
                    protected.add(os.path.realpath(path))
            for key, value in node.items():
                if key != "Choices":
                    inspect(value)

    inspect(index)
    if not seen_choices:
        raise ValueError("no live wallpaper choices were available to verify")
    return protected


def staged(path, roots):
    p = Path(path)
    return (
        p.parent in roots and re.fullmatch(TOKEN + r"\.png", p.name)
        or p.parent.parent in roots
        and re.fullmatch(TOKEN, p.parent.name)
        and p.name == "wallpaper.png"
    )


def identity(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink]


def owned_file(info):
    return stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1


def inventory(home, roots, now):
    index, index_hash = read_plist(home, INDEX)
    protected = active_paths(index)
    gallery, gallery_hash = read_plist(home, GALLERY)
    bmp_hashes = set()
    png_rows = {}
    cache_root = home / PNG_CACHE
    for source, cached in gallery_rows(gallery):
        cache_name = None
        if cached:
            cached_path = Path(cached)
            if cached_path.parent == cache_root and PNG_NAME.fullmatch(cached_path.name):
                cache_name = cached_path.name.casefold()
        eligible = (staged(source, roots) and os.path.realpath(source) not in protected
                    and not os.path.lexists(source)
                    and (cached is None or os.path.realpath(cached) not in protected))
        if eligible:
            bmp_hashes.add(digest(os.fsencode(source)))
        if cache_name:
            png_rows.setdefault(cache_name, []).append(bool(eligible))
    png_names = {name for name, rows in png_rows.items() if rows == [True]}
    candidates = []
    cache = {}
    for store, relative in (("BMP", CACHE), ("PNG", PNG_CACHE)):
        with directory(home, relative) as fd:
            for name in sorted(os.listdir(fd)):
                match = NAME.fullmatch(name) if store == "BMP" else None
                if store == "BMP" and (not match or match[1] not in bmp_hashes):
                    continue
                if store == "PNG" and name.casefold() not in png_names:
                    continue
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if owned_file(info) and max(info.st_mtime, info.st_ctime) <= now - MIN_AGE:
                    candidates.append([store, name, identity(info), info.st_blocks * 512])
            box = os.fstat(fd)
            cache[store] = [box.st_dev, box.st_ino]
    return {"cache": cache, "index": index_hash,
            "gallery": gallery_hash, "candidates": candidates}


def apply(home, roots, plan):
    fresh = inventory(home, roots, time.time())
    if fresh != plan:
        raise ValueError("wallpaper state or candidates changed; run cleanup again")
    removed = 0
    with directory(home, CACHE) as bmp_fd, directory(home, PNG_CACHE) as png_fd:
        fds = {"BMP": bmp_fd, "PNG": png_fd}
        for store, fd in fds.items():
            info = os.fstat(fd)
            if [info.st_dev, info.st_ino] != plan["cache"][store]:
                raise ValueError("wallpaper cache directory changed")
        for store, name, expected, _ in plan["candidates"]:
            fd = fds[store]
            try:
                if identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != expected:
                    raise ValueError("cache file changed; stopping cleanup")
                os.unlink(name, dir_fd=fd)
                removed += 1
            except (OSError, ValueError) as exc:
                raise ValueError(f"removed {removed} cache file(s) before cleanup stopped: {exc}") from exc
    print(f"Removed {removed} old Xplanet wallpaper cache file(s).", file=sys.stderr)


def wallpaper_health(home):
    def count(relative, suffix):
        with directory(home, relative) as fd:
            files = allocated = 0
            for name in os.listdir(fd):
                if not name.endswith(suffix):
                    continue
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    # macOS can evict a file during an observational scan.
                    continue
                if stat.S_ISREG(info.st_mode):
                    files += 1
                    allocated += info.st_blocks * 512
        return f"{files} file(s), {allocated / 1024**2:,.1f} MiB on disk"

    def gallery_count():
        gallery, _ = read_plist(home, GALLERY)
        return f"{len(list(gallery_rows(gallery)))} custom entry/entries"

    available = False
    for name, inspect in (
        ("Wallpaper → Your Photos", gallery_count),
        ("Wallpaper PNG cache", lambda: count(PNG_CACHE, ".png")),
        ("Wallpaper BMP cache", lambda: count(CACHE, ".bmp")),
    ):
        try:
            value = inspect()
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            print(f"{name}: unavailable ({exc})")
        else:
            print(f"{name}: {value}")
            available = True
    return 0 if available else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preview", "prepare", "apply", "health"))
    parser.add_argument("plan", nargs="?", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin" or os.getuid() == 0:
        parser.error("cleanup is for the logged-in macOS user; do not use sudo")
    home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
    if args.mode == "health":
        return wallpaper_health(home)
    tmp = subprocess.check_output(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True).strip().rstrip("/")
    runtime = Path(tmp)
    if not runtime.is_absolute() or not runtime.resolve(strict=True).is_relative_to("/private/var/folders"):
        raise ValueError("cannot verify the current user's macOS temporary directory")
    physical = runtime.resolve()
    roots = {runtime, physical, Path(str(physical).removeprefix("/private")),
             Path("/tmp"), Path("/private/tmp")}
    if args.mode != "preview" and not (sys.stdin.isatty() and sys.stderr.isatty()):
        parser.error("cleanup requires an interactive Terminal; use --dry-run for a report")
    if args.mode == "apply":
        apply(home, roots, json.loads(args.plan.read_text()))
        return 0
    plan = inventory(home, roots, time.time())
    candidates = plan["candidates"]
    size = sum(item[3] for item in candidates) / 1024**2
    bmps = sum(item[0] == "BMP" for item in candidates)
    print(f"{bmps} old Xplanet BMP(s) and {len(candidates) - bmps} PNG copy/copies;"
          f" {size:,.1f} MiB on disk.", file=sys.stderr)
    print("Apple's gallery, active wallpapers and originals are not removed.",
          file=sys.stderr)
    if args.mode == "preview":
        return 0
    if not candidates:
        return 3
    print("Type CLEANUP to delete these cache files: ", end="", file=sys.stderr, flush=True)
    if sys.stdin.readline().rstrip("\r\n") != "CLEANUP":
        print("Cleanup cancelled. Nothing changed.", file=sys.stderr)
        return 4
    args.plan.write_text(json.dumps(plan), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError) as error:
        print(f"xplanet.sh: wallpaper cleanup stopped: {error}", file=sys.stderr)
        if isinstance(error, PermissionError):
            print("Run this from a logged-in Terminal. If macOS still denies access, stop.",
                  file=sys.stderr)
        sys.exit(1)
