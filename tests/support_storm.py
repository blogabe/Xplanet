"""Plain offline storm fixtures shared by source, publication and runtime tests."""
from datetime import datetime, timezone
import json
from pathlib import Path

from totalmarker.errors import FeedError
from totalmarker.http import Response
from totalmarker.storm_sources import NHC_ATCF, NHC_INDEX, JTWC_RSS

FIXTURES = Path(__file__).parent / "fixtures" / "storm"
NOW = datetime(2026, 10, 19, 9, tzinfo=timezone.utc).timestamp()
LIVE_NOW = datetime(2026, 10, 19, 15, tzinfo=timezone.utc).timestamp()
JTWC = "https://www.metoc.navy.mil/jtwc/products/"
LIVE_ABIO = FIXTURES / "jtwc-abio-20261019-1230.txt"


class MappedFetcher:
    def __init__(self):
        files = {
            NHC_INDEX: "nhc-current.json",
            JTWC_RSS: "jtwc-rss.xml",
            NHC_ATCF + "btk/bep212026.dat": "nhc-best.txt",
            NHC_ATCF + "aid_public/aep212026.dat.gz": "nhc-aid-selected.gz",
            JTWC + "wp2926web.txt": "jtwc-wp-warning.txt",
            JTWC + "wp2926.kmz": "jtwc-wp-track.kmz",
            JTWC + "sh0127web.txt": "jtwc-sh-warning.txt",
            JTWC + "sh0127.kmz": "jtwc-sh-track.kmz",
            JTWC + "abioweb.txt": "jtwc-abio-20261019.txt",
            JTWC + "abpwweb.txt": "jtwc-abpw-20261019.txt",
        }
        self.payloads = {url: (FIXTURES / name).read_bytes() for url, name in files.items()}
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.payloads:
            raise FeedError("Storm test source missing")
        return Response(200, {"date": "Mon, 19 Oct 2026 09:00:00 GMT"},
                        self.payloads[url])


def empty_rss():
    return ("<rss><channel>" + "".join(
        f"<item><title>{title}</title><pubDate>Mon, 19 Oct 26 09:00:00 +0000</pubDate>"
        "<description>No active tropical systems</description></item>"
        for title in ("Current Northwest Pacific/North Indian Ocean* Tropical Systems",
                      "Current Southern Hemisphere Tropical Systems")) +
            '<item><title>Current Significant Tropical Weather Advisories</title>'
            '<description><![CDATA[<a href="' + JTWC + 'abpwweb.txt">ABPW10</a>'
            '<a href="' + JTWC + 'abioweb.txt">ABIO10</a>]]></description></item>' +
            "</channel></rss>").encode()


def empty_advisory(kind):
    areas = (("NORTH INDIAN OCEAN AREA", "SOUTH INDIAN OCEAN AREA") if kind == "abio"
             else ("WESTERN NORTH PACIFIC AREA", "SOUTH PACIFIC AREA"))
    return (f"{kind.upper()}10 PGTW 190900\nISSUED/190900Z-200600ZOCT2026//\n" +
            "".join(f"{i}. {area}:\n   A. TROPICAL CYCLONE SUMMARY: NONE.\n"
                    "   B. TROPICAL DISTURBANCE SUMMARY: NONE.\n"
                    "   C. SUBTROPICAL SYSTEM SUMMARY: NONE.\n"
                    for i, area in enumerate(areas, 1))).encode()


def formation_fetcher():
    fetcher = MappedFetcher()
    for url, name in (
        (JTWC_RSS, "jtwc-rss.xml"),
        (JTWC + "wp2926web.txt", "wp292026-warning.txt"),
        (JTWC + "sh9327web.txt", "sh932027-warning.txt"),
        (JTWC + "abpwweb.txt", "jtwc-abpw-advisory.txt"),
        (JTWC + "abioweb.txt", "jtwc-abio-advisory.txt"),
    ):
        fetcher.payloads[url] = (FIXTURES / "live-20261020" / name).read_bytes()
    return fetcher


class ReceiptPacket:
    """Mutable responses from a captured sources.json packet; never fetch live data."""

    def __init__(self, directory):
        self.records = json.loads((directory / 'sources.json').read_text())['responses']
        self.payloads = {r['url']: (directory / r['file']).read_bytes() for r in self.records}
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        record = next(r for r in self.records if r['url'] == url)
        return Response(200, {'date': record['date']}, self.payloads[url])
