"""Quoted Xplanet marker labels: its parser does not implement backslash escapes."""

import re

from .errors import FeedError

# Xplanet 1.3.1 reads marker and arc rows into a 512-byte C buffer.
# Reserve a byte for the newline as well as the terminating NUL.
MAX_MARKER_LINE_BYTES = 510


def quoted_label(value):
    # Normalize provider text before quoting; a quote must never terminate a label.
    text=''.join(char if char.isprintable() else ' ' for char in str(value))
    return '"'+text.replace('"', "'").replace('\\', '/')+'"'


def rgb_color_key(value):
    """Canonicalize the RGB color key; transparency is not an opacity scalar."""
    if not isinstance(value, str):
        raise ValueError("RGB color key must be text")
    value = value.strip()
    if not value:
        return ""
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1].strip()
    if not re.fullmatch(r"[0-9]{1,3}[ \t]*,[ \t]*[0-9]{1,3}[ \t]*,[ \t]*[0-9]{1,3}", value):
        raise ValueError("RGB color key requires three integer components")
    components = tuple(int(component) for component in value.split(","))
    if any(component > 255 for component in components):
        raise ValueError("RGB color key components must be between 0 and 255")
    return "{" + ",".join(map(str, components)) + "}"


def transparency_option(value):
    try:
        key = rgb_color_key(value)
    except ValueError:
        raise FeedError("Marker transparency requires an RGB color key such as {0,0,0}; "
                        "scalar opacity values are unsupported") from None
    return " transparent=" + key if key else ""


def encode_marker_lines(lines):
    """Refuse an unsafe row before it can hide every later row in the engine."""
    for line in lines:
        if ("\n" in line or "\r" in line
                or len(line.encode("utf-8")) > MAX_MARKER_LINE_BYTES):
            raise FeedError("Marker line exceeds Xplanet's safe 510-byte limit; "
                            "reduce detail text or image/style options")
    return ("\n".join(lines) + "\n").encode("utf-8")
