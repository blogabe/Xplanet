"""JPEG structural checks, not a full entropy/pixel decoder."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from .errors import ImageError


@dataclass(frozen=True)
class JPEGInfo:
    width: int
    height: int


def validate_jpeg(data, expected_width=0):
    if len(data) < 16 or data[:2] != b"\xff\xd8":
        raise ImageError("Cloud response is not a supported JPEG")
    position, dimensions, scans, ended = 2, None, 0, False
    quantization, huffman, entropy_bytes = False, False, 0
    while position < len(data):
        if data[position] != 0xFF:
            raise ImageError("Invalid JPEG marker structure")
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise ImageError("Truncated JPEG marker")
        marker = data[position]
        position += 1
        if marker == 0xD9:
            ended = True
            break
        if marker in {0x00, 0xD8} or 0xD0 <= marker <= 0xD7:
            raise ImageError("Unexpected JPEG marker")
        if marker == 0x01:
            continue
        if position + 2 > len(data):
            raise ImageError("Truncated JPEG segment")
        length = int.from_bytes(data[position:position + 2], "big")
        end = position + length
        if length < 2 or end > len(data):
            raise ImageError("Truncated JPEG segment")
        payload = data[position + 2:end]
        if marker == 0xDB:
            quantization = bool(payload)
        if marker == 0xC4:
            huffman = bool(payload)
        if marker in {0xC0, 0xC2}:
            if len(payload) < 6 or payload[0] != 8:
                raise ImageError("Unsupported JPEG frame")
            height = int.from_bytes(payload[1:3], "big")
            width = int.from_bytes(payload[3:5], "big")
            components = payload[5]
            if not width or not height or not 1 <= components <= 4 or length != 8 + 3 * components:
                raise ImageError("Invalid JPEG dimensions or frame")
            dimensions = JPEGInfo(width, height)
        elif marker in {0xC1, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            raise ImageError("Unsupported JPEG encoding")
        if marker == 0xDA:
            if dimensions is None or not payload or length != 6 + 2 * payload[0]:
                raise ImageError("Invalid JPEG scan header")
            scans += 1
            position = end
            # Entropy data contains escaped FF bytes and standalone restart markers.
            while position < len(data):
                if data[position] != 0xFF:
                    entropy_bytes += 1
                    position += 1
                    continue
                start = position
                while position < len(data) and data[position] == 0xFF:
                    position += 1
                if position >= len(data):
                    raise ImageError("Truncated JPEG scan")
                code = data[position]
                if code == 0x00 or 0xD0 <= code <= 0xD7:
                    entropy_bytes += int(code == 0x00)
                    position += 1
                    continue
                position = start
                break
        else:
            position = end
    if (not ended or dimensions is None or scans == 0 or position != len(data)
            or not quantization or not huffman or not entropy_bytes):
        raise ImageError("Incomplete JPEG image or unexpected trailing data")
    if expected_width and dimensions.width != expected_width:
        raise ImageError("Cloud JPEG width does not match configuration")
    return dimensions

# The current cloud JPEG explicitly declares its production time in a COM
# segment. HTTP Last-Modified is a separate server-resource timestamp.
CLOUD_CREATED = re.compile(
    r"EarthDesk Cloud Image Created "
    r"(Sun|Mon|Tue|Wed|Thu|Fri|Sat) "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) +"
    r"(\d{1,2}) (\d{2}):(\d{2}):(\d{2}) (?:UTC|GMT) (\d{4})"
)
CLOUD_MONTHS = {name: index for index, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
     "Sep", "Oct", "Nov", "Dec"), 1)}
CLOUD_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def cloud_creation_time(data):
    """Return an explicit UTC creation time from a JPEG comment, or None."""
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    position, found = 2, None
    while position < len(data):
        if data[position] != 0xFF:
            return None
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            return None
        marker = data[position]
        position += 1
        if marker in {0xD9, 0xDA}:
            return found
        if marker == 0x01:
            continue
        if marker in {0x00, 0xD8} or 0xD0 <= marker <= 0xD7:
            return None
        if position + 2 > len(data):
            return None
        length = int.from_bytes(data[position:position + 2], "big")
        end = position + length
        if length < 2 or end > len(data):
            return None
        if marker == 0xFE:
            try:
                comment = data[position + 2:end].decode("ascii").strip("\x00 \r\n\t")
            except UnicodeError:
                comment = ""
            if comment.startswith("EarthDesk Cloud Image Created"):
                match = CLOUD_CREATED.fullmatch(comment)
                if match is None:
                    return None
                weekday, month, day, hour, minute, second, year = match.groups()
                try:
                    stamp = datetime(int(year), CLOUD_MONTHS[month], int(day),
                                     int(hour), int(minute), int(second),
                                     tzinfo=timezone.utc)
                except ValueError:
                    return None
                if CLOUD_WEEKDAYS[stamp.weekday()] != weekday:
                    return None
                value = stamp.timestamp()
                if found is not None and found != value:
                    return None
                found = value
        position = end
    return None
