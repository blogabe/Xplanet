"""Legacy local-time product labels; preserve unrelated records verbatim."""
from datetime import datetime
import hashlib
import re
import time

from .aurora_status import MAX_FEED, OVERLAY, read_record
from .diagnostics import success_at
from .errors import StorageError

LABEL_LIMIT = 2 * 1024 * 1024


def read_labels(fs, path):
    """Read display labels, treating absence as empty and preserving valid bytes."""
    raw = fs.read(path, LABEL_LIMIT)
    try:
        return raw.decode("utf-8") if raw is not None else ""
    except UnicodeError:
        raise StorageError("Existing labels are not valid UTF-8") from None


PREFIX = "Cloud Map Last Updated"
VOLCANO_PREFIX = "Volcano Information Last Updated"
QUAKE_PREFIX = "Earthquake Information Last Updated"
STORM_PREFIX = "Storm Information Last Updated"
NORAD_PREFIX = "NORAD Information Last Updated"
AURORA_PREFIX = "Aurora Forecast Valid Until"
LEGACY_PREFIXES = {
    VOLCANO_PREFIX: "Volcano Infomation Last Updated",
    QUAKE_PREFIX: "Earthquake Infomation Last Updated",
    STORM_PREFIX: "Storm Infomation Last Updated",
    NORAD_PREFIX: "NORAD Infomation Last Updated",
}
# Broad legacy names count as occupied product rows when placing a new label.
STACK_ROW_PREFIXES = (PREFIX, AURORA_PREFIX, "Earthquake", "Storm", "Volcano", "NORAD")
ROW = re.compile(r'^(?P<head>\s*-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\s+")'
                 r'(?P<text>[^"\r\n]*)(?P<tail>"[^\r\n]*)(?P<nl>\r?\n)?$')
STAMP = re.compile(r"(?:Sun|Mon|Tues?|Wed|Thurs?|Fri|Sat) (\d{1,2}) "
                   r"(Jan|Feb|March|April|May|June|July|Aug|Sept|Oct|Nov|Dec) "
                   r"(\d{4}),(\d{2}):(\d{2}):(\d{2})$")
MONTHS = ["Jan", "Feb", "March", "April", "May", "June", "July", "Aug",
          "Sept", "Oct", "Nov", "Dec"]
WEEKDAYS = ["Mon", "Tues", "Wed", "Thurs", "Fri", "Sat", "Sun"]


def legacy_time(timestamp):
    stamp = time.localtime(timestamp)
    return (f"{WEEKDAYS[stamp.tm_wday]} {stamp.tm_mday} {MONTHS[stamp.tm_mon - 1]} "
            f"{stamp.tm_year},{stamp.tm_hour:02d}:{stamp.tm_min:02d}:{stamp.tm_sec:02d}")


def matches_product(text, prefix):
    return (text.startswith(prefix + " ")
            or text.startswith(LEGACY_PREFIXES.get(prefix, prefix) + " "))


def product_timestamp(text, prefix):
    for line in text.splitlines():
        row = ROW.match(line)
        if row and matches_product(row["text"], prefix):
            stamp = STAMP.search(row["text"])
            if stamp:
                day, month, year, hour, minute, second = stamp.groups()
                try:
                    datetime(int(year), MONTHS.index(month) + 1, int(day),
                             int(hour), int(minute), int(second))
                    return time.mktime((int(year), MONTHS.index(month) + 1, int(day),
                                        int(hour), int(minute), int(second), 0, 0, -1))
                except (ValueError, OverflowError):
                    return None
    return None


def cloud_timestamp(text):
    return product_timestamp(text, PREFIX)


def volcano_timestamp(text):
    return product_timestamp(text, VOLCANO_PREFIX)


def quake_timestamp(text):
    return product_timestamp(text, QUAKE_PREFIX)


def storm_timestamp(text):
    return product_timestamp(text, STORM_PREFIX)


def color_for(source_created_at, now, warning, colors):
    if source_created_at is None or source_created_at > now:
        return colors[2]
    age = now - source_created_at
    return colors[2] if age > 2 * warning else colors[1] if age > warning else colors[0]


def render_product(existing, prefix, timestamp, now, warning, colors, *,
                   append=True, second_coordinate=-13):
    if timestamp is not None and timestamp > now:
        timestamp = None
    color = color_for(timestamp, now, warning, colors)
    text = prefix + " " + (legacy_time(timestamp) if timestamp is not None else "UNKNOWN")
    lines, found, count, occupied = [], False, 0, set()
    for line in existing.splitlines(keepends=True):
        row = ROW.match(line)
        if row:
            occupied.add(float(row["head"].split()[0]))
            if row["text"].startswith(STACK_ROW_PREFIXES):
                count += 1
            if matches_product(row["text"], prefix):
                if found:
                    # Preserve unusual duplicate legacy records rather than deleting them.
                    lines.append(line)
                    continue
                found = True
                tail = row["tail"]
                if re.search(r"(?<!\S)color=\S+", tail):
                    tail = re.sub(r"(?<!\S)color=\S+", "color=" + color, tail, count=1)
                else:
                    tail += " color=" + color
                lines.append(row["head"] + text + tail + (row["nl"] or ""))
                continue
        lines.append(line)
    if not found and append:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        coordinate = -(53 + 15 * count)
        while coordinate in occupied:
            coordinate -= 15
        lines.append(f'{coordinate} {second_coordinate} "{text}" '
                     f'color={color} image=none position=pixel\n')
    return "".join(lines)


def render_cloud(existing, source_created_at, now, warning, colors, *, append=True):
    return render_product(existing, PREFIX, source_created_at, now, warning,
                          colors, append=append, second_coordinate=-13)


def render_volcano(existing, successful_at, now, warning, colors, *, append=True):
    return render_product(existing, VOLCANO_PREFIX, successful_at, now, warning,
                          colors, append=append, second_coordinate=-13)


def render_quake(existing, successful_at, now, warning, colors, *, append=True):
    return render_product(existing, QUAKE_PREFIX, successful_at, now, warning,
                          colors, append=append, second_coordinate=-13)


def render_storm(existing, successful_at, now, warning, colors, *, append=True):
    return render_product(existing, STORM_PREFIX, successful_at, now, warning,
                          colors, append=append, second_coordinate=-13)


def render_norad(existing, successful_at, now, warning, colors, *, append=True):
    return render_product(existing, NORAD_PREFIX, successful_at, now, warning,
                          colors, append=append, second_coordinate=-13)


def _aurora_label(fs, settings, now):
    try:
        record = read_record(fs)
        if record:
            overlay = fs.read(OVERLAY, MAX_FEED)
            expires = record["expires_at"]
            if (overlay is not None and hashlib.sha256(overlay).hexdigest() == record["overlay_sha256"]
                    and 0 <= record["observed_at"] <= now + 300
                    and record["observed_at"] <= expires < 253402300799):
                return legacy_time(expires), settings.colors[0 if now < expires else 1]
    except (StorageError, OverflowError, OSError, ValueError):
        pass
    return "UNKNOWN", settings.colors[2]


def _aurora_position(lines, cloud):
    """Reserve the next stock row without relocating custom markers."""
    anchor = ROW.match(lines[cloud])
    first, column = anchor["head"].split()[:2]
    target = float(first) - 15
    slots = {}
    for i, line in enumerate(lines):
        row = ROW.match(line)
        if row:
            slots.setdefault(float(row["head"].split()[0]), []).append((i, row))
    displaced = []
    end = target
    while end in slots:
        slot = slots[end]
        occupant = slot[0][1]
        if (len(slot) != 1 or column != "-13" or end > -53 or (end + 53) % 15
                or occupant["head"].split()[1] != column
                or not occupant["tail"].rstrip().endswith("position=pixel")
                or not any(matches_product(occupant["text"], prefix) for prefix in
                           (QUAKE_PREFIX, STORM_PREFIX, VOLCANO_PREFIX, NORAD_PREFIX))):
            # A custom position may be deliberate; leave that stack untouched.
            while end in slots:
                end -= 15
            return end, column
        displaced.append(slot[0])
        end -= 15
    for i, row in displaced:
        head = re.sub(r"-?\d+(?:\.\d+)?", f'{float(row["head"].split()[0])-15:g}',
                      row["head"], count=1)
        lines[i] = head + row["text"] + row["tail"] + (row["nl"] or "")
    return target, column


def refresh_aurora(fs, existing, settings, now, *, append=False):
    lines = existing.splitlines(keepends=True)
    own = [i for i, line in enumerate(lines)
           if (row := ROW.match(line)) and matches_product(row["text"], AURORA_PREFIX)]
    if not settings.aurora.enabled:
        return "".join(line for i, line in enumerate(lines) if i not in own)
    if not own and not append:
        return existing
    stamp, color = _aurora_label(fs, settings, now)
    text = f"{AURORA_PREFIX} {stamp}"
    cloud = next((i for i, line in enumerate(lines)
                  if (row := ROW.match(line)) and matches_product(row["text"], PREFIX)
                  and abs(float(row["head"].split()[0])) <= 2**31), None)
    if own:
        row = ROW.match(lines[own[0]])
        # Keep known coordinates unless a cloud row was subsequently added below.
        cloud_pos = float(ROW.match(lines[cloud])["head"].split()[0]) if cloud is not None else None
        if cloud_pos is None or float(row["head"].split()[0]) < cloud_pos:
            tail, replaced = re.subn(r"(?<!\S)color=\S+", "color=" + color, row["tail"], count=1)
            if not replaced:
                tail += " color=" + color
            lines[own[0]] = row["head"] + text + tail + (row["nl"] or "")
            return "".join(lines)
        for i in reversed(own):
            lines.pop(i)
            cloud -= i < cloud
    if cloud is None:
        used = {float(row["head"].split()[0]) for line in lines if (row := ROW.match(line))}
        pos, column = -53, "-13"
        while pos in used:
            pos -= 15
        index = len(lines)
    else:
        pos, column = _aurora_position(lines, cloud)
        index = cloud + 1
    if index and not lines[index - 1].endswith("\n"):
        lines[index - 1] += "\n"
    lines.insert(index, f'{pos:g} {column} "{text}" color={color} image=none position=pixel\n')
    return "".join(lines)


def marker_timestamp(record):
    return success_at(record)


def refresh_all(existing, state, settings, now, *, fs, append_product=None):
    """Re-age configured rows without changing their saved update timestamps."""
    products = state["products"]
    rows = (
        ("clouds", render_cloud, products.get("clouds", {}).get("source_created_at"),
         settings.warning),
        ("quake", render_quake, marker_timestamp(products.get("quake", {})),
         settings.quake.warning),
        ("storm", render_storm, marker_timestamp(products.get("storm", {})),
         settings.storm.warning),
        ("volcano", render_volcano, marker_timestamp(products.get("volcano", {})),
         settings.volcano.warning),
    )
    if settings.norad.enabled:
        rows += (("norad", render_norad,
                  marker_timestamp(products.get("norad", {})), settings.norad.warning),)
    for product, render, timestamp, warning in rows:
        existing = render(existing, timestamp, now, warning, settings.colors,
                          append=product == append_product)
    return refresh_aurora(fs, existing, settings, now)
