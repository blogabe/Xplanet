"""NASA/GSFC central solar eclipse path markers, arcs and notices."""
import copy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import math
from html.parser import HTMLParser
import json
import re
import time
from urllib.parse import urljoin, urlsplit

from ..errors import DownloadError, FeedError, StorageError
from ..http import Fetcher
from ..labels import refresh_all
from ..state import PairPublisher, load_state, recover_pending


TITLE = re.compile(
    r"Path\s+of(?:\s+the)?\s+(Total|Annular|Hybrid)\s+Solar\s+Eclipse\s+of\s+"
    r"(20[0-9]{2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+([0-9]{2})")
URL = re.compile(
    r"/SEpath/SEpath[0-9]{4}/SE(20[0-9]{2})"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)([0-9]{2})([TAH])path\.html")
ROW = re.compile(r"^\s*(Limits|[0-9]{2}:[0-9]{2})\s+(.+)$")
COORD = re.compile(
    r"\s*(?:(\d{1,2})\s+(\d{2}\.\d)([NS])\s+"
    r"(\d{1,3})\s+(\d{2}\.\d)([EW])|(-)\s+(-))")
MONTHS = {month: index for index, month in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
TYPE_CODE = {"Total": "T", "Annular": "A", "Hybrid": "H"}
INDEX_URL = "https://eclipse.gsfc.nasa.gov/SEpath/SEpath.html"
INDEX_LIMIT = 2 * 1024 * 1024


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "pre", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


class _IndexLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if isinstance(href, str):
                self.hrefs.append(href)


def parse_index(raw):
    """Read central-path links from the official NASA index, without crawling."""
    if len(raw) > INDEX_LIMIT:
        raise FeedError("NASA eclipse index exceeds the parser size limit")
    try:
        html = raw.decode("utf-8")
    except UnicodeError:
        raise FeedError("NASA eclipse index is not valid UTF-8") from None
    parser = _IndexLinks()
    parser.feed(html)
    events = {}
    for href in parser.hrefs:
        try:
            url = urljoin(INDEX_URL, href)
            parsed = urlsplit(url)
            match = URL.fullmatch(parsed.path)
            if (parsed.scheme != "https" or parsed.hostname != "eclipse.gsfc.nasa.gov"
                    or parsed.port not in {None, 443} or parsed.username is not None
                    or parsed.password is not None or parsed.query or parsed.fragment
                    or match is None):
                continue
        except ValueError:
            continue
        year, month, day, _kind = match.groups()
        try:
            event_date = datetime(int(year), MONTHS[month], int(day),
                                  tzinfo=timezone.utc).date()
        except ValueError:
            continue
        events[url] = event_date
    if not events:
        raise FeedError("NASA eclipse index has no supported central-path links")
    return tuple(sorted(((event_date, url) for url, event_date in events.items()),
                        key=lambda item: (item[0], item[1])))


@dataclass(frozen=True)
class PathPoint:
    time_at: float | None
    north: tuple[float, float] | None
    south: tuple[float, float] | None
    center: tuple[float, float]


@dataclass(frozen=True)
class EclipsePath:
    kind: str
    date: str
    points: tuple[PathPoint, ...]
    start_at: float
    end_at: float


@dataclass(frozen=True)
class Result:
    outcome: str
    message: str
    installed_at: float | None
    successful_at: float | None
    start_at: float | None
    end_at: float | None
    count: int | None


def _coordinate(text, position):
    match = COORD.match(text, position)
    if match is None:
        raise FeedError("NASA central path row has an invalid coordinate")
    if match[7]:
        return None, match.end()
    lat_deg, lat_min, lat_hemi, lon_deg, lon_min, lon_hemi = match.groups()[:6]
    lat_degrees, lon_degrees = int(lat_deg), int(lon_deg)
    lat_minutes, lon_minutes = float(lat_min), float(lon_min)
    if (lat_minutes >= 60 or lon_minutes >= 60 or lat_degrees > 90
            or lon_degrees > 180 or (lat_degrees == 90 and lat_minutes != 0)
            or (lon_degrees == 180 and lon_minutes != 0)):
        raise FeedError("NASA central path coordinate is outside Earth")
    lat = lat_degrees + lat_minutes / 60
    lon = lon_degrees + lon_minutes / 60
    if (lat > 90 or lon > 180):
        raise FeedError("NASA central path coordinate is outside Earth")
    return ((-lat if lat_hemi == "S" else lat),
            (-lon if lon_hemi == "W" else lon)), match.end()


def parse_path(raw, url):
    try:
        html = raw.decode("utf-8")
    except UnicodeError:
        raise FeedError("NASA central path is not valid UTF-8") from None
    if len(html) > 8 * 1024 * 1024:
        raise FeedError("NASA central path exceeds the parser size limit")
    document = _Text()
    document.feed(html)
    text = "".join(document.parts)
    titles = TITLE.findall(text)
    path_match = URL.fullmatch(urlsplit(url).path)
    if not titles or not path_match:
        raise FeedError("NASA central solar eclipse identity is missing")
    kind, year, month, day = titles[0]
    if any((found_year, found_month, found_day, TYPE_CODE[found_kind]) !=
           path_match.groups() for found_kind, found_year, found_month, found_day in titles):
        raise FeedError("NASA central path identity differs from the requested event")
    try:
        event_date = datetime(int(year), MONTHS[month], int(day), tzinfo=timezone.utc)
    except ValueError:
        raise FeedError("NASA central path date is invalid") from None
    points, timed, limits = [], [], 0
    rollover = 0
    previous_hour = None
    for line in text.splitlines():
        match = ROW.match(line)
        if match is None:
            continue
        label, rest = match.groups()
        position, coords = 0, []
        for _ in range(3):
            coordinate, position = _coordinate(rest, position)
            coords.append(coordinate)
        if coords[2] is None:
            raise FeedError("NASA central line is missing")
        if label == "Limits":
            limits += 1
            at = None
        else:
            hour, minute = map(int, label.split(":"))
            if hour > 23 or minute > 59:
                raise FeedError("NASA central path time is invalid")
            if previous_hour is not None and hour < previous_hour:
                rollover += 1
            previous_hour = hour
            at = (event_date + timedelta(days=rollover, hours=hour,
                                          minutes=minute)).timestamp()
            if timed and at - timed[-1] != 120:
                raise FeedError("NASA central path times are not consecutive 120-second steps")
            timed.append(at)
        points.append(PathPoint(at, *coords))
        if len(points) > 1000:
            raise FeedError("NASA central path has too many rows")
    if len(timed) < 2 or limits != 2 or not points or points[0].time_at is not None or points[-1].time_at is not None:
        raise FeedError("NASA central path table is incomplete")
    return EclipsePath(kind, event_date.date().isoformat(), tuple(points),
                       timed[0], timed[-1])


def _coordinate_text(point):
    return f"{point[0]:.4f} {point[1]:.4f}"


def render(path, options, now, active):
    header = f"# Eclipse Predictions by Fred Espenak, NASA's GSFC; {path.kind} {path.date} UTC\n"
    if not active:
        return header.encode(), header.encode()
    timed = [point for point in path.points if point.time_at is not None]
    markers = [header]
    selected = {timed[0], timed[-1]}
    selected.update(point for point in timed if datetime.fromtimestamp(
        point.time_at, timezone.utc).minute % 20 == 0)
    for point in timed:
        if point in selected:
            stamp = datetime.fromtimestamp(point.time_at, timezone.utc).strftime("%H:%M")
            markers.append(f'{_coordinate_text(point.center)} "{stamp} UTC" '
                           f'color={options.edge_color} align=above symbolsize=4\n')
    if options.notice_enabled:
        markers.append(_notice_line(path.kind, path.start_at, path.end_at, now,
                                    options.notice_color))
        markers.append(_notice_context(options.notice_color))
    arcs = [header]
    for name, color in (("north", options.edge_color), ("south", options.edge_color),
                        ("center", options.center_color)):
        arcs.append(f"# {name} path\n")
        previous = None
        for row in path.points:
            current = getattr(row, name)
            if current is not None and previous is not None:
                arcs.append(f"{_coordinate_text(previous)} {_coordinate_text(current)} "
                            f"color={color} spacing=0.2\n")
            previous = current
    return "".join(markers).encode("ascii"), "".join(arcs).encode("ascii")


def _notice_line(kind, start_at, end_at, now, color):
    stamp = datetime.fromtimestamp(start_at, timezone.utc).strftime("%Y-%m-%d %H:%M")
    if now < start_at:
        hours, minutes = divmod(math.ceil((start_at - now) / 60), 60)
        message = (f"{kind} Solar Eclipse central-path samples begin in "
                   f"{hours}h {minutes}m ({stamp} UTC)")
    elif now <= end_at:
        message = f"{kind} Solar Eclipse central-path sampling underway (began {stamp} UTC)"
    else:
        finished = datetime.fromtimestamp(end_at, timezone.utc).strftime("%Y-%m-%d %H:%M")
        message = f"{kind} Solar Eclipse central-path sampling ended {finished} UTC"
    return f'-55 1 "{message}" color={color} image=none position=pixel\n'


def _notice_context(color):
    return (f'-45 1 "NASA predicted central path and limits shown" '
            f'color={color} image=none position=pixel\n')


def _refresh_notice(raw, kind, start_at, end_at, now, color):
    old = [line for line in raw.splitlines(keepends=True) if line.startswith(b'-55 1 "')]
    if len(old) != 1:
        return None
    return raw.replace(old[0], _notice_line(kind, start_at, end_at, now, color).encode("ascii"), 1)


def _source_key(fs, options, *, parser_version=2, legacy_notice=False):
    style = asdict(options)
    if legacy_notice:
        style.pop("notice_enabled")
    for key in ("interval", "timeout", "max_bytes", "journal"):
        style.pop(key)
    for name in ("marker", "arc"):
        style[name] = str(fs.resolve(getattr(options, name), write=True).relative_to(fs.root))
    style["parser_version"] = parser_version
    return hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()


def _publisher(fs, settings):
    return PairPublisher(fs, settings, "eclipse", settings.eclipse.marker,
                         settings.eclipse.arc, "marker_sha256", "arc_sha256")


def _fetch_selected_path(client, options, now):
    if options.path_url:
        urls = (options.path_url,)
    else:
        index = client.fetch(INDEX_URL, timeout=options.timeout,
                             max_bytes=min(INDEX_LIMIT, options.max_bytes))
        if index.status != 200:
            raise FeedError("NASA did not return a central eclipse index")
        cutoff = datetime.fromtimestamp(now, timezone.utc).date() - timedelta(days=1)
        candidates = [url for event_date, url in parse_index(index.body)
                      if event_date >= cutoff]
        if not candidates:
            raise FeedError("NASA eclipse index has no upcoming central event")
        # At most yesterday's or today's completed event plus its successor.
        urls = candidates[:2]
    for url in urls:
        response = client.fetch(url, timeout=options.timeout,
                                max_bytes=options.max_bytes)
        if response.status != 200:
            raise FeedError("NASA did not return a central path table")
        path = parse_path(response.body, url)
        if options.path_url or path.end_at + 3600 >= now:
            return path
    raise FeedError("NASA index candidates have no current or upcoming central path")


def _inactive_outputs(record):
    kind, event_date = record.get("kind"), record.get("event_date")
    if kind in TYPE_CODE and event_date:
        header = f"# Eclipse Predictions by Fred Espenak, NASA's GSFC; {kind} {event_date} UTC\n"
    else:
        header = "# Eclipse Predictions by Fred Espenak, NASA's GSFC; expired central path\n"
    return header.encode("ascii"), header.encode("ascii")


def run(fs, settings, *, fetcher=None, now=None):
    options = settings.eclipse
    if not options.enabled:
        return Result("disabled", "Eclipse is disabled in configuration",
                      None, None, None, None, None)
    now = time.time() if now is None else now
    with fs.lock(settings.lock):
        recover_pending(fs, settings)
        publisher = _publisher(fs, settings)
        state = load_state(fs, settings.state)
        record = state["products"].setdefault("eclipse", {})
        raw_label = fs.read(settings.labels, 2 * 1024 * 1024)
        try:
            old_label = raw_label.decode("utf-8") if raw_label is not None else ""
        except UnicodeError:
            raise StorageError("Existing labels are not valid UTF-8") from None
        record["checked_at"] = now
        existing_marker = fs.read(options.marker, PairPublisher.LIMIT)
        existing_arc = fs.read(options.arc, PairPublisher.LIMIT)
        valid_existing = (
            existing_marker is not None and existing_arc is not None
            and hashlib.sha256(existing_marker).hexdigest() == record.get("marker_sha256")
            and hashlib.sha256(existing_arc).hexdigest() == record.get("arc_sha256"))
        key = _source_key(fs, options)
        notice_only_key = _source_key(fs, replace(
            options, notice_enabled=not options.notice_enabled))
        old_key = _source_key(fs, options, legacy_notice=True)
        old_v1_key = _source_key(fs, options, parser_version=1, legacy_notice=True)
        notice_toggle_keys = {notice_only_key}
        if not options.notice_enabled:
            # Before the notice switch existed, notices were always enabled.
            notice_toggle_keys.update((old_key, old_v1_key))
        compatible_key = record.get("source_key") in {
            key, _source_key(fs, options, parser_version=1), old_key, old_v1_key}
        start_at, end_at = record.get("start_at"), record.get("end_at")
        active_from_state = (start_at is not None and end_at is not None
                             and start_at - options.notify_hours * 3600 <= now <= end_at + 3600)
        known_expired = end_at is not None and now > end_at + 3600
        offline_expiry = (valid_existing and known_expired
                          and record.get("active") is True)
        elapsed = now - record.get("fetched_at", -1e20)
        cached = (valid_existing and record.get("source_key") == key
                  and record.get("active") == active_from_state
                  and 0 <= elapsed < options.interval)
        # A fixed event remains expired; re-fetching it can never discover a
        # successor. Index mode resumes its bounded daily discovery instead.
        if (options.path_url and valid_existing and compatible_key and known_expired
                and record.get("active") is False):
            cached = True
        outcome, message, marker, arc = "unchanged", "Cached NASA eclipse path retained", None, None
        local_notice_refresh = False
        if offline_expiry:
            marker, arc = _inactive_outputs(record)
            record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
            record["arc_sha256"] = hashlib.sha256(arc).hexdigest()
            record["body_sha256"] = hashlib.sha256(marker + b"\0" + arc).hexdigest()
            record["installed_at"] = now
            record["active"] = False
            outcome, message = "changed", "Expired eclipse path hidden from saved event times"
        elif (valid_existing and record.get("source_key") in notice_toggle_keys
              and record.get("active") is True and active_from_state
              and isinstance(start_at, (int, float)) and isinstance(end_at, (int, float))
              and record.get("kind") in TYPE_CODE):
            if options.notice_enabled:
                marker = (existing_marker +
                          _notice_line(record["kind"], start_at, end_at, now,
                                       options.notice_color).encode("ascii") +
                          _notice_context(options.notice_color).encode("ascii"))
            else:
                marker = b"".join(line for line in existing_marker.splitlines(keepends=True)
                                  if not line.startswith((b'-55 1 "', b'-45 1 "')))
            arc = existing_arc
            record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
            record["arc_sha256"] = hashlib.sha256(arc).hexdigest()
            record["body_sha256"] = hashlib.sha256(marker + b"\0" + arc).hexdigest()
            record["installed_at"] = now
            record["source_key"] = key
            outcome, message = "changed", "Eclipse notice visibility updated from saved path"
            local_notice_refresh = True
        elif (cached and active_from_state and options.notice_enabled
              and isinstance(start_at, (int, float)) and isinstance(end_at, (int, float))
              and record.get("kind") in TYPE_CODE):
            revised = _refresh_notice(existing_marker, record["kind"], start_at, end_at,
                                      now, options.notice_color)
            if revised is not None and revised != existing_marker:
                marker, arc = revised, existing_arc
                record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
                record["arc_sha256"] = hashlib.sha256(arc).hexdigest()
                record["body_sha256"] = hashlib.sha256(marker + b"\0" + arc).hexdigest()
                record["installed_at"] = now
                outcome, message = "changed", "Eclipse countdown refreshed from saved event time"
                local_notice_refresh = True
        elif not cached:
            before = copy.deepcopy(record)
            try:
                client = fetcher if fetcher is not None else Fetcher()
                path = _fetch_selected_path(client, options, now)
                active = path.start_at - options.notify_hours * 3600 <= now <= path.end_at + 3600
                new_marker, new_arc = render(path, options, now, active)
                body_hash = hashlib.sha256(new_marker + b"\0" + new_arc).hexdigest()
                if not valid_existing or record.get("body_sha256") != body_hash:
                    marker, arc = new_marker, new_arc
                    if max(len(marker), len(arc)) > PairPublisher.LIMIT:
                        raise FeedError("Eclipse output exceeds the publication size limit")
                    record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
                    record["arc_sha256"] = hashlib.sha256(arc).hexdigest()
                    record["body_sha256"] = body_hash
                    record["installed_at"] = now
                    outcome, message = "changed", "NASA central eclipse path published"
                else:
                    message = "Identical NASA eclipse outputs retained"
                record["source_key"] = key
                record["fetched_at"] = now
                record["start_at"] = path.start_at
                record["end_at"] = path.end_at
                record["kind"] = path.kind
                record["event_date"] = path.date
                record["active"] = active
                record["count"] = len(path.points)
            except (DownloadError, FeedError) as error:
                outcome, message, marker, arc = "failed", str(error), None, None
                record.clear()
                record.update(before)
                if (valid_existing and compatible_key and record.get("active") is True
                        and active_from_state and options.notice_enabled
                        and isinstance(start_at, (int, float))
                        and isinstance(end_at, (int, float))
                        and record.get("kind") in TYPE_CODE):
                    revised = _refresh_notice(existing_marker, record["kind"],
                                              start_at, end_at, now,
                                              options.notice_color)
                    if revised is not None and revised != existing_marker:
                        marker, arc = revised, existing_arc
                        record["marker_sha256"] = hashlib.sha256(marker).hexdigest()
                        record["arc_sha256"] = hashlib.sha256(arc).hexdigest()
                        record["body_sha256"] = hashlib.sha256(marker + b"\0" + arc).hexdigest()
                        record["installed_at"] = now
        if (outcome != "failed" and not offline_expiry and not local_notice_refresh and not
                (record.get("active") is False and record.get("end_at") is not None
                 and now > record["end_at"] + 3600)
                and (marker is not None or valid_existing)):
            record["successful_at"] = now
        record["last_outcome"] = outcome
        label = (refresh_all(old_label, state, settings, now)
                 if settings.labels_enabled else None)
        if label == old_label:
            label = None
        publisher.publish(state, label, first=marker, second=arc)
        if settings.log:
            event = {"time": now, "feature": "eclipse", "outcome": outcome,
                     "message": message, "installed_at": record.get("installed_at"),
                     "successful_at": record.get("successful_at"),
                     "start_at": record.get("start_at"), "end_at": record.get("end_at"),
                     "count": record.get("count")}
            try:
                fs.append(settings.log, (json.dumps(event) + "\n").encode())
            except StorageError:
                message += "; diagnostic log unavailable"
        return Result(outcome, message, record.get("installed_at"),
                      record.get("successful_at"), record.get("start_at"),
                      record.get("end_at"), record.get("count"))
