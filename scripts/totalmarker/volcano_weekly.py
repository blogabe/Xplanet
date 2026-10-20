"""Strict GVP weekly HTML extraction with a static GDACS coordinate join.

The HTML report selects activity. The GDACS snapshot supplies positions only;
its active/inactive flags and names never select or rename report entries.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .errors import FeedError
from .volcano_cap import Volcano

CATALOGUE = Path(__file__).parent / "data/gdacs_volcano_coordinates_20261019.json"
WEEKLY_URL = "https://volcano.si.edu/reports_weekly.cfm"
MONTHS = {month.lower(): index for index, month in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"), 1)}
RANGE = re.compile(r"(?i)(\d{1,2})\s+([A-Za-z]+)(?:\s+(20\d{2}))?\s*[-–]\s*"
                   r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})")
ID = re.compile(r"vn_([1-9][0-9]{4,8})\Z")
CITATION = re.compile(r"GVP\.WVAR(20[0-9]{6})-([1-9][0-9]{4,8})\Z")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or ())
        self.children = []
        self.parent = parent

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self, *, skip_citation=False):
        if skip_citation and "varCiteLink" in self.attrs.get("class", "").split():
            return ""
        return "".join(child.text(skip_citation=skip_citation)
                       if isinstance(child, Node) else child for child in self.children)


def _clean(text):
    return " ".join(text.split())


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"tr", "td", "th"}:
            # HTML permits implicit closes for these table elements.
            stops = {"tr": {"tr", "td", "th"}, "td": {"td", "th"},
                     "th": {"th", "td"}}[tag]
            while len(self.stack) > 1 and self.stack[-1].tag in stops:
                self.stack.pop()
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


@dataclass(frozen=True)
class WeeklyReport:
    id: int
    name: str
    country: str
    category: str
    narrative: str


@dataclass(frozen=True)
class WeeklyPage:
    period_start: date
    period_end: date
    reports: tuple[WeeklyReport, ...]

    @property
    def coverage_end_at(self):
        # The week ends at the start of the next UTC day. This is a coverage
        # cutoff, never a publication timestamp.
        return datetime.combine(self.period_end + timedelta(days=1),
                                datetime.min.time(), timezone.utc).timestamp()


def _period(text):
    match = RANGE.search(text)
    if not match:
        raise FeedError("GVP weekly reporting period is missing")
    first_day, first_month, first_year, last_day, last_month, last_year = match.groups()
    try:
        end_year = int(last_year)
        end_month = MONTHS[last_month.lower()]
        start_month = MONTHS[first_month.lower()]
        start_year = int(first_year) if first_year else end_year - (start_month > end_month)
        start = date(start_year, start_month, int(first_day))
        end = date(end_year, end_month, int(last_day))
    except (ValueError, KeyError):
        raise FeedError("GVP weekly reporting period is invalid") from None
    if (end - start).days != 6:
        raise FeedError("GVP weekly reporting period is not seven days")
    return start, end


def _cite_id_and_period(heading, expected_id, expected_start):
    references = []
    for child in heading.walk():
        if child.tag != "a":
            continue
        url = child.attrs.get("href", "")
        params = parse_qs(urlsplit(url).query)
        references.extend(params.get("gvpvar", []))
    if len(references) != 1:
        raise FeedError("GVP weekly detail lacks one citation identifier")
    match = CITATION.fullmatch(references[0])
    if not match or int(match[2]) != expected_id or match[1] != expected_start.strftime("%Y%m%d"):
        raise FeedError("GVP weekly citation disagrees with report ID or period")


def parse_weekly_html(raw):
    """Require equal summary/detail IDs, complete narratives and one week."""
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise FeedError("GVP weekly HTML is empty or too large")
    try:
        html = raw.decode("utf-8")
    except UnicodeError:
        raise FeedError("GVP weekly HTML is not UTF-8") from None
    tree = _Tree()
    try:
        tree.feed(html)
        tree.close()
    except (ValueError, RecursionError):
        raise FeedError("GVP weekly HTML is malformed") from None
    nodes = list(tree.root.walk())
    periods = []
    for node in nodes:
        if node.tag == "h3" and "for the week of" in _clean(node.text()).lower():
            periods.append(_period(node.text()))
    if len(periods) != 1:
        raise FeedError("GVP weekly HTML must have one report week")
    start, end = periods[0]
    summaries = {}
    for node in nodes:
        if node.tag != "a":
            continue
        href = node.attrs.get("href", "")
        match = ID.fullmatch(href.removeprefix("#")) if href.startswith("#") else None
        if not match:
            continue
        identifier = int(match[1])
        name = _clean(node.text())
        if identifier in summaries or not name or len(name) > 256:
            raise FeedError("GVP weekly summary has duplicate or empty names")
        summaries[identifier] = name
    if not summaries:
        raise FeedError("GVP weekly HTML has no summary report links")
    reports = {}
    for node in nodes:
        if node.tag != "tr":
            continue
        match = ID.fullmatch(node.attrs.get("id", ""))
        if not match:
            continue
        identifier = int(match[1])
        if identifier in reports:
            raise FeedError("GVP weekly HTML duplicates a detailed report")
        headings = [part for part in node.walk() if part.tag == "h5"]
        if len(headings) != 1:
            raise FeedError("GVP weekly detail lacks a unique heading")
        heading = headings[0]
        _cite_id_and_period(heading, identifier, start)
        sections = [_clean(piece) for piece in heading.text(skip_citation=True).split("|")]
        if len(sections) != 3:
            raise FeedError("GVP weekly heading lacks location, week or category")
        name_country, span, category = sections
        if _period(span) != (start, end) or not category:
            raise FeedError("GVP weekly detail has an inconsistent period or category")
        person = re.fullmatch(r"(.+?)\s*\(([^()]+)\)", name_country)
        if not person or identifier not in summaries or _clean(person[1]) != summaries[identifier]:
            raise FeedError("GVP weekly summary and detail names disagree")
        siblings = node.parent.children if node.parent is not None else []
        try:
            index = siblings.index(node)
        except ValueError:
            raise FeedError("GVP weekly detail row has no parent") from None
        following = next((piece for piece in siblings[index + 1:] if isinstance(piece, Node)), None)
        if following is None or following.tag != "tr":
            raise FeedError("GVP weekly detail lacks a narrative row")
        cells = [piece for piece in following.children
                 if isinstance(piece, Node) and piece.tag == "td"]
        if len(cells) < 2:
            raise FeedError("GVP weekly narrative row lacks its second cell")
        narrative = _clean(cells[1].text())
        if len(narrative) < 20:
            raise FeedError("GVP weekly narrative is incomplete")
        reports[identifier] = WeeklyReport(identifier, summaries[identifier],
                                           _clean(person[2]), category, narrative)
    if set(reports) != set(summaries):
        raise FeedError("GVP weekly summary/detail report IDs disagree")
    return WeeklyPage(start, end, tuple(reports[identifier] for identifier in summaries))


def load_coordinate_catalogue(path=CATALOGUE):
    try:
        source = json.loads(Path(path).read_bytes())
    except (OSError, ValueError, UnicodeError):
        raise FeedError("Static volcano coordinate catalogue is unavailable or invalid") from None
    if (not isinstance(source, dict) or source.get("schema") != 1
            or not isinstance(source.get("coordinates"), dict)):
        raise FeedError("Static volcano coordinate catalogue has an invalid schema")
    result = {}
    for key, coords in source["coordinates"].items():
        if (not isinstance(key, str) or not re.fullmatch(r"[1-9][0-9]{4,8}", key)
                or not isinstance(coords, list) or len(coords) != 2
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in coords)
                or not -90 <= coords[0] <= 90 or not -180 <= coords[1] <= 180):
            raise FeedError("Static volcano coordinate catalogue contains invalid positions")
        result[int(key)] = tuple(coords)
    if not result:
        raise FeedError("Static volcano coordinate catalogue is empty")
    return result


def join_coordinates(page, coordinates):
    events = []
    for report in page.reports:
        if report.id not in coordinates:
            raise FeedError("GVP weekly report ID lacks a static coordinate: " + str(report.id))
        lat, lon = coordinates[report.id]
        events.append(Volcano(report.name, report.country, lat, lon))
    return events
