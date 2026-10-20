"""Legacy local-time product labels; preserve unrelated records verbatim."""
import re
from datetime import datetime
import time

PREFIX = "Cloud Map Last Updated"
VOLCANO_PREFIX = "Volcano Infomation Last Updated"  # Legacy spelling is visible output.
QUAKE_PREFIX = "Earthquake Infomation Last Updated"
STORM_PREFIX = "Storm Infomation Last Updated"
NORAD_PREFIX = "NORAD Infomation Last Updated"
# Broad legacy names count as occupied product rows when placing a new label.
STACK_ROW_PREFIXES = (PREFIX, "Earthquake", "Storm", "Volcano", "NORAD")
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


def product_timestamp(text, prefix):
    for line in text.splitlines():
        row = ROW.match(line)
        if row and row["text"].startswith(prefix + " "):
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
            if row["text"].startswith(prefix):
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
                          colors, append=append, second_coordinate=-12)


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


def marker_timestamp(record):
    # Older state has no successful-at field. A confirmed publication is a
    # conservative lower bound; poll and legacy-label times are not proof.
    successful_at = record.get("successful_at")
    return successful_at if successful_at is not None else record.get("installed_at")


def refresh_all(existing, state, settings, now, *, append_product=None):
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
    return existing
