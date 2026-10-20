"""JTWC significant-weather advisories: active current invests only.

An invest's bulletin issue is used as its position time proxy. Previous
coordinates in prose are never promoted to a timed history or forecast arc.
Only a complete explicit dissipated stand-down can remove a listed invest.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re

from .errors import FeedError
from .storm_model import Storm, TrackPoint

MONTH = {name: number for number, name in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
ISSUE = re.compile(r"(?m)\b(?:REISSUED|ISSUED)/([0-9]{2})([0-9]{2})([0-9]{2})Z-"
                   r"([0-9]{2})([0-9]{2})([0-9]{2})Z([A-Z]{3})(20[0-9]{2})//[ \t]*\r?$")
SUBJECT_ISSUE = re.compile(
    r"(?m)^SUBJ/SIGNIFICANT TROPICAL WEATHER ADVISORY FOR THE "
    r"(INDIAN OCEAN|WESTERN AND SOUTH\s+PACIFIC OCEANS)/"
    r"([0-9]{2})([0-9]{2})([0-9]{2})Z-[ \t]*(?:\r?\n[ \t]*)?"
    r"([0-9]{2})([0-9]{2})([0-9]{2})Z([A-Z]{3})(20[0-9]{2})//[ \t]*\r?$")
ISSUE_CUE = re.compile(r"\b(?:REISSUED|ISSUED)(?=/|[ \t]+[0-9]{6}Z-)")
SUBJECT_CUE = re.compile(r"(?m)^SUBJ/")
REISSUE_SUBJECT = re.compile(
    r"(?m)^SUBJ/SIGNIFICANT TROPICAL WEATHER ADVISORY FOR THE "
    r"(INDIAN OCEAN|WESTERN AND SOUTH\s+PACIFIC OCEANS)\s+"
    r"(?:REISSUED|ISSUED)/")
AREA = re.compile(r"(?m)^([12])\.\s+(NORTH INDIAN OCEAN AREA|SOUTH INDIAN OCEAN AREA|"
                  r"WESTERN NORTH PACIFIC AREA|SOUTH PACIFIC AREA)\b[^\n]*:")
SUMMARY = re.compile(r"(?m)^\s*([ABC])\.\s+(TROPICAL CYCLONE SUMMARY|"
                     r"TROPICAL DISTURBANCE SUMMARY|SUBTROPICAL SYSTEM SUMMARY):")
BLOCK = re.compile(r"(?m)^\s*\(([0-9]+)\)\s+")
INVEST = re.compile(r"\bINVEST\s+([0-9]{2}[A-Z])\b")
CURRENT = re.compile(r"\b(?:IS NOW LOCATED NEAR|HAS PERSISTED NEAR)\s+"
                     r"([0-9]{1,2}(?:\.[0-9]+)?)([NS])\s+"
                     r"([0-9]{1,3}(?:\.[0-9]+)?)([EW])\b")
DISSIPATED = re.compile(
    r"THE AREA OF CONVECTION \(INVEST ([0-9]{2}[A-Z])\) PREVIOUSLY LOCATED NEAR "
    r"([0-9]{1,2}(?:\.[0-9]+)?)([NS]) ([0-9]{1,3}(?:\.[0-9]+)?)([EW]) "
    r"HAS DISSIPATED AND IS NO LONGER SUSPECT FOR THE DEVELOPMENT OF A "
    r"SIGNIFICANT TROPICAL CYCLONE IN THE NEXT 24 HOURS\."
)
PROMOTED = re.compile(
    r"THE AREA OF CONVECTION \(INVEST ([0-9]{2}[A-Z])\) PREVIOUSLY LOCATED NEAR "
    r"([0-9]{1,2}(?:\.[0-9]+)?)([NS]) ([0-9]{1,3}(?:\.[0-9]+)?)([EW]) "
    r"IS NOW THE SUBJECT OF A TROPICAL CYCLONE WARNING\. SEE PARA\. "
    r"([12])\.A\.\(([0-9]+)\) FOR FURTHER DETAILS\."
)
WARNED = re.compile(r"\b(?:TYPHOON|CYCLONE|DEPRESSION|STORM)\s+([0-9]{2}[A-Z])\b")
AREAS = {
    "abio": (("NORTH INDIAN OCEAN AREA", "AB", "IO", "jtwc_indian"),
             ("SOUTH INDIAN OCEAN AREA", "S", "SH", "jtwc_south")),
    "abpw": (("WESTERN NORTH PACIFIC AREA", "W", "WP", "jtwc_west"),
             ("SOUTH PACIFIC AREA", "P", "SH", "jtwc_south")),
}


@dataclass(frozen=True)
class AdvisoryArea:
    name: str
    group: str
    cyclone_none: bool
    warned_codes: tuple[str, ...]
    invests: tuple[Storm, ...]


@dataclass(frozen=True)
class Advisory:
    issue_at: float
    valid_until_at: float
    areas: tuple[AdvisoryArea, ...]

    @property
    def invests(self):
        return tuple(invest for area in self.areas for invest in area.invests)


def _issue_interval(text, kind):
    explicit = list(ISSUE.finditer(text))
    subject = list(SUBJECT_ISSUE.finditer(text))
    issue_cues = list(ISSUE_CUE.finditer(text))
    subject_cues = list(SUBJECT_CUE.finditer(text))
    if len(subject_cues) > 1:
        raise FeedError("Storm JTWC advisory lacks a dated issue interval")
    if subject:
        if len(subject) != 1 or issue_cues or len(subject_cues) != 1:
            raise FeedError("Storm JTWC advisory lacks a dated issue interval")
        region, *parts = subject[0].groups()
    else:
        if len(issue_cues) != 1 or len(explicit) != 1:
            raise FeedError("Storm JTWC advisory lacks a dated issue interval")
        if subject_cues:
            heading = REISSUE_SUBJECT.search(text)
            if heading is None or heading.start() != subject_cues[0].start():
                raise FeedError("Storm JTWC advisory lacks a dated issue interval")
            region = heading[1]
        else:
            region = None  # Header-only issue intervals have no subject region.
        parts = explicit[0].groups()
    if region is not None:
        expected_region = ("INDIAN OCEAN" if kind == "abio" else
                           "WESTERN AND SOUTH PACIFIC OCEANS")
        if " ".join(region.split()) != expected_region:
            raise FeedError("Storm JTWC advisory subject disagrees with region")
    day, hour, minute, end_day, end_hour, end_minute, month, year = parts
    try:
        until = datetime(int(year), MONTH[month], int(end_day), int(end_hour),
                         int(end_minute), tzinfo=timezone.utc)
    except (KeyError, ValueError):
        raise FeedError("Storm JTWC advisory validity interval is invalid") from None
    previous_month = until.month - 1 or 12
    previous_year = until.year - (until.month == 1)
    starts = []
    for candidate_year, candidate_month in ((until.year, until.month),
                                            (previous_year, previous_month)):
        try:
            start = datetime(candidate_year, candidate_month, int(day), int(hour),
                             int(minute), tzinfo=timezone.utc)
        except ValueError:
            continue
        if timedelta(0) < until - start <= timedelta(hours=24):
            starts.append(start)
    if len(starts) != 1:
        raise FeedError("Storm JTWC advisory validity interval is invalid")
    header = re.search(r"(?m)^" + kind.upper() + r"10\s+PGTW\s+([0-9]{6})\s*$", text)
    if not header or header[1] != day + hour + minute:
        raise FeedError("Storm JTWC advisory header disagrees with issue time")
    return starts[0].timestamp(), until.timestamp()


def _current_position(text):
    matches = list(CURRENT.finditer(text))
    if len(matches) != 1:
        raise FeedError("Storm JTWC invest lacks one explicit current position")
    lat, ns, lon, ew = matches[0].groups()
    lat = float(lat) * (-1 if ns == "S" else 1)
    lon = float(lon) * (-1 if ew == "W" else 1)
    if not all(map(math.isfinite, (lat, lon))) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise FeedError("Storm JTWC invest position is out of range")
    return lat, lon


def _dissipated(paragraph, code):
    """Recognize only a complete explicit stand-down, never reuse its old fix."""
    if not re.search(r"\b(?:DISSIPATED|NO LONGER SUSPECT)\b", paragraph):
        return False
    match = DISSIPATED.fullmatch(" ".join(paragraph.split()))
    if not match or match[1] != code:
        raise FeedError("Storm JTWC dissipated invest status is ambiguous")
    lat = float(match[2]) * (-1 if match[3] == "S" else 1)
    lon = float(match[4]) * (-1 if match[5] == "W" else 1)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise FeedError("Storm JTWC previous invest position is out of range")
    return True


def _promoted_warning(paragraph, code, area_number, cyclone, warned_codes):
    """Accept only an explicit pointer from a retired invest to one warning."""
    prose = " ".join(paragraph.split())
    if "IS NOW THE SUBJECT OF A TROPICAL CYCLONE WARNING" not in prose:
        return None
    match = PROMOTED.fullmatch(prose)
    if not match or match[1] != code or int(match[6]) != area_number:
        raise FeedError("Storm JTWC promoted invest reference is ambiguous")
    lat = float(match[2]) * (-1 if match[3] == "S" else 1)
    lon = float(match[4]) * (-1 if match[5] == "W" else 1)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise FeedError("Storm JTWC previous invest position is out of range")
    blocks = list(BLOCK.finditer(cyclone))
    if [int(item[1]) for item in blocks] != list(range(1, len(blocks) + 1)):
        raise FeedError("Storm JTWC promoted invest reference is ambiguous")
    number = int(match[7])
    if not 1 <= number <= len(blocks):
        raise FeedError("Storm JTWC promoted invest reference is ambiguous")
    end = blocks[number].start() if number < len(blocks) else len(cyclone)
    referenced = WARNED.findall(cyclone[blocks[number - 1].end():end])
    if len(referenced) != 1 or referenced[0] not in warned_codes:
        raise FeedError("Storm JTWC promoted invest reference is ambiguous")
    return referenced[0]


def _section_parts(body):
    matches = list(SUMMARY.finditer(body))
    if len(matches) != 3 or [m[1] for m in matches] != ["A", "B", "C"] or [
            m[2] for m in matches] != ["TROPICAL CYCLONE SUMMARY",
                                     "TROPICAL DISTURBANCE SUMMARY",
                                     "SUBTROPICAL SYSTEM SUMMARY"]:
        raise FeedError("Storm JTWC advisory lacks complete cyclone and disturbance sections")
    return (body[matches[0].end():matches[1].start()],
            body[matches[1].end():matches[2].start()],
            body[matches[2].end():])


def parse_advisory(raw, kind):
    if kind not in AREAS:
        raise FeedError("Storm JTWC advisory region is unsupported")
    try:
        text = raw.decode("ascii")
    except UnicodeError:
        raise FeedError("Storm JTWC advisory is not ASCII") from None
    if not text or len(text) > 256 * 1024:
        raise FeedError("Storm JTWC advisory is empty or too large")
    issue_at, valid_until_at = _issue_interval(text, kind)
    area_matches = list(AREA.finditer(text))
    expected = AREAS[kind]
    if len(area_matches) != 2 or [(m[1], m[2]) for m in area_matches] != [
            ("1", expected[0][0]), ("2", expected[1][0])]:
        raise FeedError("Storm JTWC advisory lacks both expected basin areas")
    result = []
    seen_invest_codes = set()
    for index, match in enumerate(area_matches):
        end = area_matches[index + 1].start() if index == 0 else len(text)
        body = text[match.end():end]
        cyclone, disturbance, subtropical = _section_parts(body)
        # The last basin can be followed by a numbered justification footer.
        # Subtropical records have no adapter yet: require explicit empty
        # coverage rather than silently treating a populated C section as none.
        subtropical = re.split(r"(?m)^3\.\s+JUSTIFICATION FOR REISSUE:",
                               subtropical, maxsplit=1)[0].strip()
        subtropical = re.sub(r"(?m)^NNNN\s*$", "", subtropical).strip()
        subtropical = subtropical.removesuffix("//").strip()
        if not re.fullmatch(r"NONE\.?,?", subtropical):
            raise FeedError("Storm JTWC subtropical summary is unsupported or ambiguous")
        cyclone = cyclone.strip()
        if not cyclone:
            raise FeedError("Storm JTWC cyclone summary is empty")
        cyclone_none = bool(re.fullmatch(r"NONE\.?,?", cyclone))
        warned_codes = tuple(WARNED.findall(cyclone)) if not cyclone_none else ()
        if not cyclone_none and not warned_codes:
            raise FeedError("Storm JTWC cyclone summary is ambiguous")
        if len(warned_codes) != len(set(warned_codes)):
            raise FeedError("Storm JTWC cyclone summary repeats a warning")
        area_name, letters, basin, group = expected[index]
        for code in warned_codes:
            if code[-1] not in letters:
                raise FeedError("Storm JTWC warning code disagrees with basin")
        disturbance = disturbance.strip()
        invests = []
        promoted_warnings = set()
        if not re.fullmatch(r"NONE\.?,?", disturbance):
            blocks = list(BLOCK.finditer(disturbance))
            if not blocks or [int(m[1]) for m in blocks] != list(range(1, len(blocks) + 1)):
                raise FeedError("Storm JTWC disturbance summary is ambiguous")
            for i, item in enumerate(blocks):
                end_block = blocks[i + 1].start() if i + 1 < len(blocks) else len(disturbance)
                paragraph = disturbance[item.end():end_block]
                if re.fullmatch(r"NO OTHER SUSPECT AREAS\.?,?", paragraph.strip()):
                    continue
                codes = INVEST.findall(paragraph)
                if len(codes) != 1 or codes[0][-1] not in letters:
                    raise FeedError("Storm JTWC disturbance lacks one basin-valid invest code")
                code = codes[0]
                if code in seen_invest_codes:
                    raise FeedError("Storm JTWC advisory repeats an invest code")
                seen_invest_codes.add(code)
                if _dissipated(paragraph, code):
                    continue
                promoted = _promoted_warning(paragraph, code, index + 1,
                                             cyclone, warned_codes)
                if promoted is not None:
                    if promoted in promoted_warnings:
                        raise FeedError("Storm JTWC promoted invests repeat a warning")
                    promoted_warnings.add(promoted)
                    continue
                lat, lon = _current_position(paragraph)
                year = datetime.fromtimestamp(issue_at, timezone.utc).year
                if basin == "SH" and datetime.fromtimestamp(issue_at, timezone.utc).month >= 7:
                    year += 1
                invests.append(Storm(basin + code[:2] + str(year), "Invest " + code, "DEP",
                                     TrackPoint(issue_at, lat, lon), None, (), None, (),
                                     "not_issued"))
        if len({storm.id for storm in invests}) != len(invests):
            raise FeedError("Storm JTWC advisory repeats an invest")
        result.append(AdvisoryArea(area_name, group, cyclone_none, warned_codes,
                                   tuple(invests)))
    return Advisory(issue_at, valid_until_at, tuple(result))
