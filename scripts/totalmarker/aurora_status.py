"""Read the saved OVATION forecast metadata without fetching or rendering."""
import json
import re

DIR = ".state/totalmarker/aurora"
OVERLAY = DIR + "/overlay.png"
RECORD = DIR + "/status.json"
MAX_FEED = 2 * 1024 * 1024


def read_record(fs):
    raw = fs.read(RECORD, 8192)
    if raw is None:
        return {}
    try:
        item = json.loads(raw)
        if (not isinstance(item, dict) or item.get("schema") != 1
                or any(type(item.get(key)) is not int for key in ("observed_at", "forecast_at", "expires_at"))
                or type(item.get("fetched_at")) is not int
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("overlay_sha256")))):
            raise ValueError
        return item
    except (ValueError, TypeError):
        return {}
