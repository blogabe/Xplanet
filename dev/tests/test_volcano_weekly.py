"""Synthetic contracts plus a reduced fixture derived from the saved GVP page."""
from datetime import datetime, timezone
from pathlib import Path
import json

from totalmarker.errors import FeedError
from totalmarker.features.volcano import run
from totalmarker.http import Fetcher, Response
from totalmarker.labels import legacy_time
from totalmarker.volcano_weekly import (WEEKLY_URL, join_coordinates,
    load_coordinate_catalogue, parse_weekly_html)
from .support import Sandbox, ScriptedTransport

NOW = datetime(2026, 10, 19, 9, tzinfo=timezone.utc).timestamp()


def weekly_html(*, missing_detail=False, bad_citation=False, empty_narrative=False,
                extra_id=None, period="8 October-14 October 2026"):
    reports = [
        (262000, "Krakatau", "Indonesia", "New Eruptive Activity"),
        (282080, "Aira", "Japan", "Continuing Eruptive Activity"),
        (263250, "Merapi", "Indonesia", "Unrest"),
        (251020, "Manam", "Papua New Guinea", "Unknown Activity"),
    ]
    summary = "".join(f'<a href="#vn_{ident}">{name}</a>' for ident, name, _, _ in reports)
    if extra_id is not None:
        summary += f'<a href="#vn_{extra_id}">Missing Coordinate</a>'
        reports.append((extra_id, "Missing Coordinate", "Nowhere", "Unrest"))
    detail = ""
    for ident, name, country, category in reports:
        if missing_detail and ident == 251020:
            continue
        cited = "20261007" if bad_citation and ident == 262000 else "20261008"
        narrative = "" if empty_narrative and ident == 282080 else (
            f"The weekly report describes observed activity for {name} and its monitoring context.")
        detail += (f'<tr id="vn_{ident}"><td><h5>{name} ({country}) | {period} | {category}'
                   f'<span class="varCiteLink"><a href="/citation?gvpvar=GVP.WVAR{cited}-{ident}">'
                   'Cite this Report</a></span></h5></td></tr>'
                   f'<tr><td>map</td><td><p>{narrative}</p></td></tr>')
    return (f'<html><body><h3>Smithsonian / USGS Weekly Volcanic Activity Report '
            f'for the week of {period}</h3><table>{summary}</table><table>{detail}'
            '</table></body></html>').encode()


class WeeklyVolcanoTests(Sandbox):
    def test_curated_actual_page_structure_has_all_27_joinable_reports(self):
        folder = Path(__file__).parent / 'fixtures'
        manifest = json.loads((folder / 'gvp_weekly_20261019_manifest.json').read_bytes())
        page = parse_weekly_html((folder / 'gvp_weekly_20261019_structural.html').read_bytes())
        self.assertEqual((page.period_start.isoformat(), page.period_end.isoformat()),
                         (manifest['period_start'], manifest['period_end']))
        self.assertEqual([{'id': item.id, 'name': item.name, 'country': item.country,
                           'category': item.category} for item in page.reports],
                         manifest['reports'])
        self.assertEqual(len(join_coordinates(page, load_coordinate_catalogue())), 27)
        self.assertEqual(sum(item.category == 'New Eruptive Activity'
                             for item in page.reports), 4)
        self.assertEqual(sum(item.category == 'Continuing Eruptive Activity'
                             for item in page.reports), 23)

    def test_static_catalogue_provenance_and_coordinate_order(self):
        catalogue = load_coordinate_catalogue()
        self.assertEqual(len(catalogue), 1440)
        self.assertEqual(catalogue[282080], (31.5772, 130.6589))
        self.assertEqual(catalogue[262000], (-6.1009, 105.4233))
        source = json.loads((Path(__file__).parents[2] /
                             'scripts/totalmarker/data/gdacs_volcano_coordinates_20261019.json').read_bytes())
        self.assertIn('coordinate-only', source['source'])
        self.assertEqual(source['source_date'], '2026-10-19')

    def test_all_categories_names_period_and_unknown_publication_time(self):
        page = parse_weekly_html(weekly_html())
        self.assertEqual((page.period_start.isoformat(), page.period_end.isoformat()),
                         ('2026-10-08', '2026-10-14'))
        self.assertEqual([item.category for item in page.reports],
                         ['New Eruptive Activity', 'Continuing Eruptive Activity',
                          'Unrest', 'Unknown Activity'])
        events = join_coordinates(page, load_coordinate_catalogue())
        self.assertEqual([item.name for item in events],
                         ['Krakatau', 'Aira', 'Merapi', 'Manam'])
        self.assertEqual((events[1].lat, events[1].lon), (31.5772, 130.6589))
        self.assertIsNone(events[1].source_sent_at)
        self.assertEqual(page.coverage_end_at,
                         datetime(2026, 10, 15, tzinfo=timezone.utc).timestamp())

    def test_malformed_incomplete_or_unjoined_reports_fail(self):
        for raw in [b'', b'<html>blocked</html>', weekly_html(missing_detail=True),
                    weekly_html(bad_citation=True), weekly_html(empty_narrative=True),
                    weekly_html(period='8 October-13 October 2026')]:
            with self.subTest(raw=raw[:50]), self.assertRaises(FeedError):
                parse_weekly_html(raw)
        page = parse_weekly_html(weekly_html(extra_id=999999))
        with self.assertRaisesRegex(FeedError, 'lacks a static coordinate'):
            join_coordinates(page, load_coordinate_catalogue())

    def test_weekly_cache_and_304_recheck_saved_report_expiry(self):
        settings = self.config('VolcanoProvider=weekly_html\n'
                               'VolcanoCheckIntervalSeconds=3600000\n')
        good = Response(200, {'content-type': 'text/html'}, weekly_html())
        first = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(good)), now=NOW)
        self.assertEqual(first.outcome, 'changed')
        marker = self.fs.read(settings.volcano.marker)
        coverage_end = first.coverage_end_at
        self.assertIsNotNone(coverage_end)
        expired = coverage_end + 14 * 86400 + 1
        cached_transport = ScriptedTransport()
        cached = run(self.fs, settings, fetcher=Fetcher(cached_transport), now=expired)
        self.assertEqual(cached.outcome, 'failed')
        self.assertEqual(cached_transport.calls, [])
        self.assertEqual(cached.successful_at, NOW)
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        self.assertEqual(self.read_state(settings)['products']['volcano']['fetched_at'], NOW)
        polling = self.config('VolcanoProvider=weekly_html\nVolcanoCheckIntervalSeconds=0\n')
        not_modified = ScriptedTransport(Response(304, {}))
        stale = run(self.fs, polling, fetcher=Fetcher(not_modified), now=expired + 1)
        self.assertEqual(stale.outcome, 'failed')
        self.assertEqual(len(not_modified.calls), 1)
        self.assertEqual(stale.successful_at, NOW)
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        self.assertEqual(self.read_state(settings)['products']['volcano']['fetched_at'], NOW)
        stale_body = run(self.fs, polling, fetcher=Fetcher(ScriptedTransport(good)),
                         now=expired + 2)
        self.assertEqual(stale_body.outcome, 'failed')
        self.assertEqual(stale_body.successful_at, NOW)

    def test_weekly_provider_change_unchanged_stale_failure_retains_last_good(self):
        settings = self.config('VolcanoProvider=weekly_html\nVolcanoCheckIntervalSeconds=0\n')
        old = '-53 -12 "Cloud Map Last Updated UNKNOWN" color=Red image=none position=pixel\n'
        self.fs.write(settings.labels, old.encode())
        good = Response(200, {'content-type': 'text/html'}, weekly_html())
        transport = ScriptedTransport(good)
        first = run(self.fs, settings, fetcher=Fetcher(transport), now=NOW)
        self.assertEqual((first.outcome, first.count, first.provider),
                         ('changed', 4, 'weekly_html'))
        self.assertEqual(transport.calls[0][0], WEEKLY_URL)
        self.assertIsNone(first.source_report_at)
        self.assertEqual(first.report_period_end, '2026-10-14')
        marker = self.fs.read(settings.volcano.marker)
        label = self.fs.read(settings.labels).decode()
        self.assertIn('"Aira"', marker.decode())
        self.assertIn(f'-68 -13 "Volcano Infomation Last Updated {legacy_time(NOW)}"', label)
        self.assertIn('color=Green', label.splitlines()[1])
        second = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(good)), now=NOW + 60)
        self.assertEqual(second.outcome, 'unchanged')
        self.assertEqual((second.installed_at, second.successful_at), (NOW, NOW + 60))
        label_after_second = self.fs.read(settings.labels).decode()
        self.assertIn(legacy_time(NOW + 60), label_after_second)
        bad = Response(200, {'content-type': 'text/html'}, weekly_html(missing_detail=True))
        failed = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(bad)), now=NOW + 120)
        self.assertEqual(failed.outcome, 'failed')
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        self.assertEqual(self.fs.read(settings.labels).decode(), label_after_second)
        missing = Response(200, {'content-type': 'text/html'},
                           weekly_html(extra_id=999999))
        failed_join = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(missing)),
                          now=NOW + 150)
        self.assertEqual(failed_join.outcome, 'failed')
        self.assertIn('lacks a static coordinate', failed_join.message)
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        denied = run(self.fs, settings,
                     fetcher=Fetcher(ScriptedTransport(Response(
                         403, {"Content-Type": "text/html", "CF-Ray": "abc123-SFO",
                               "Set-Cookie": "DUMMY_COOKIE"},
                         b"<h1>Access denied</h1> DUMMY_TOKEN", "Forbidden"))),
                     now=NOW + 160)
        self.assertEqual(denied.outcome, 'failed')
        self.assertIn('HTTP 403', denied.message)
        self.assertIn('cf-ray=abc123-SFO', denied.message)
        self.assertIn('excerpt=Access denied', denied.message)
        log = self.fs.read(settings.log).decode()
        self.assertIn('HTTP 403', log)
        self.assertIn('cf-ray=abc123-SFO', log)
        self.assertNotIn('DUMMY', log)
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        self.assertEqual(self.fs.read(settings.labels).decode(), label_after_second)
        stale = run(self.fs, settings, fetcher=Fetcher(ScriptedTransport(good)),
                    now=NOW + 21 * 86400)
        self.assertEqual(stale.outcome, 'failed')
        self.assertEqual(self.fs.read(settings.volcano.marker), marker)
        state = self.read_state(settings)['products']['volcano']
        self.assertEqual(state['report_period_start'], '2026-10-08')
        self.assertEqual(state['report_period_end'], '2026-10-14')
        self.assertIsNone(state['source_report_at'])

    def test_cap_provider_remains_default_and_weekly_provider_is_explicit(self):
        self.assertEqual(self.config().volcano.provider, 'cap')
        self.assertEqual(self.config('VolcanoProvider=weekly_html\n').volcano.provider,
                         'weekly_html')
        (self.root / 'weekly.toml').write_text(
            '[cloud]\nprovider = "custom"\n'
            'url = "https://cloud.example.invalid/map.jpg"\n'
            '[volcano]\nprovider = "weekly_html"\n'
            'url = "https://volcano.example.invalid/retained-cap.xml"\n')
        from totalmarker.config import load
        selected = load(self.fs, 'weekly.toml')
        self.assertEqual(selected.volcano.provider, 'weekly_html')
        self.assertEqual(selected.volcano.url,
                         'https://volcano.example.invalid/retained-cap.xml')
        from totalmarker.errors import ConfigError
        with self.assertRaises(ConfigError):
            self.config('VolcanoProvider=unknown\n')
