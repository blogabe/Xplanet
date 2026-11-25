"""Inspect the volcano section or render an explicit choice in a fresh example."""
import os
import re
import stat
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

CAP = "https://volcano.si.edu/news/WeeklyVolcanoCAP.xml"
# Keep the skip sentinel aligned with VolcanoOptions.enabled.
PLACEHOLDER = "https://volcano.example.invalid/WeeklyVolcanoCAP.xml"
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

    provider = setting("provider", "cap")
    raw = setting("url")
    if not isinstance(provider, str) or raw is not None and not isinstance(raw, str):
        return "unconfigured"
    provider = provider.lower()
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


def template_region(data):
    # Offer guided choices only for the shipped source, not a customized example.
    if source(data) != "ready":
        raise ValueError
    start = re.search(r"(?m)^\[volcano\][ \t]*\r?$", data).end()
    end = re.search(r"(?m)^\[", data[start:])
    stop = start + end.start() if end else len(data)
    part = data[start:stop]
    provider = re.findall(r'(?m)^provider = "weekly_html"\r?$', part)
    # Accept the previous stock template too. Never replace the commented URL.
    url_lines = re.findall(rf'(?m)^(url = "(?:{re.escape(CAP)})?")\r?$', part)
    if len(provider) != 1 or len(url_lines) != 1:
        raise ValueError
    return start, stop, url_lines[0]


def choose(data, choice):
    start, stop, url_line = template_region(data)
    if choice == "weekly_html":
        return data

    def replace_setting(section, old, new):
        return re.sub(rf"(?m)^{re.escape(old)}(?=\r?$)", new, section, count=1)

    part = replace_setting(data[start:stop], 'provider = "weekly_html"', 'provider = "cap"')
    if choice not in {"cap", "skip"}:
        raise ValueError
    url = CAP if choice == "cap" else PLACEHOLDER
    part = replace_setting(part, url_line, f'url = "{url}"')
    result = data[:start] + part + data[stop:]
    if source(result) != ("unconfigured" if choice == "skip" else "ready"):
        raise ValueError
    return result


def main():
    mode, filename, *args = sys.argv[1:]
    data = read_config(filename)
    if mode == "status" and not args:
        print(source(data))
    elif mode == "selectable" and not args:
        template_region(data)
    elif mode == "render" and len(args) == 1:
        sys.stdout.buffer.write(choose(data, args[0]).encode("utf-8"))
    else:
        raise ValueError


if __name__ == "__main__":
    try:
        main()
    except (AttributeError, KeyError, OSError, ValueError):
        sys.exit(1)
