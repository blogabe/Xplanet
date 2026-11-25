"""Determine whether guided setup can offer volcano refresh and scheduling."""
import os
import stat
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

CAP = "https://volcano.si.edu/news/WeeklyVolcanoCAP.xml"
MAX_CONFIG = 1024 * 1024


def read_config(filename):
    path = Path(filename)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ValueError
            data = file.read(MAX_CONFIG + 1)
        if len(data) > MAX_CONFIG:
            raise ValueError
        return data.decode("utf-8")
    finally:
        os.close(directory)


def source(data):
    document = tomllib.loads(data.removeprefix("\ufeff"))
    section = document.get("volcano", {})
    legacy = document.get("legacy", {})
    if not isinstance(section, dict) or not isinstance(legacy, dict):
        return "unconfigured"

    def setting(name, default=None):
        # The producer accepts native, flat, and [legacy] keys. Refuse duplicates.
        canonical = "volcano" + name
        values = ([section[name]] if name in section else [])
        for table in (document, legacy):
            values.extend(v for k, v in table.items() if k.lower() == canonical)
        if len(values) > 1:
            raise ValueError
        return values[0] if values else default

    enabled = setting("enabled", True)
    if enabled is not True and not (isinstance(enabled, str) and enabled.lower() == "on"):
        return "unconfigured"
    provider = setting("provider", "cap")
    raw = setting("url")
    if not isinstance(provider, str) or raw is not None and not isinstance(raw, str):
        return "unconfigured"
    provider = provider.lower()
    if provider == "auto":
        return "ready" if raw in (None, "", CAP) else "unconfigured"
    if not raw:
        return "ready" if provider == "weekly_html" else "unconfigured"
    if any(ord(c) <= 32 or ord(c) == 127 for c in raw):
        return "unconfigured"
    url = urlsplit(raw)
    hostname = (url.hostname or "").rstrip(".")
    if (url.scheme != "https" or not hostname or url.username is not None
            or url.password is not None or url.query or url.fragment):
        return "unconfigured"
    _ = url.port
    if provider == "weekly_html":
        return "ready"
    if provider == "cap":
        if hostname != "invalid" and not hostname.endswith(".invalid"):
            return "ready"
    return "unconfigured"


def main():
    mode, filename = sys.argv[1:]
    if mode != "status":
        raise ValueError
    print(source(read_config(filename)))


if __name__ == "__main__":
    try:
        main()
    except (AttributeError, KeyError, OSError, ValueError):
        sys.exit(1)
