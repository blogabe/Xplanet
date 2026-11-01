"""Read-only health summaries; live validators run in disposable output roots."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time

from .errors import StorageError, TotalMarkerError
from .features import clouds, eclipse, norad, quake, storm, volcano
from .http import Fetcher
from .labels import color_for, marker_timestamp
from .paths import RootFS
from .state import load_state
from .storm_sources import JTWC_RSS, NHC_INDEX
from .volcano_weekly import WEEKLY_URL

RUNNERS = {'clouds': clouds.run, 'quake': quake.run, 'storm': storm.run,
           'volcano': volcano.run, 'norad': norad.run, 'eclipse': eclipse.run}


def _sources(settings):
    return {
        'clouds': [settings.url], 'quake': [settings.quake.url],
        'storm': [NHC_INDEX, JTWC_RSS],
        'volcano': [WEEKLY_URL if settings.volcano.provider == 'weekly_html'
                    else settings.volcano.url],
        'norad': [norad.CELESTRAK.format(id=number) for number in settings.norad.catalog_ids]
                 + [norad.CELESTRAK_GROUP.format(source=group.source)
                    for group in settings.norad.groups if group.enabled],
        'eclipse': [settings.eclipse.path_url or eclipse.INDEX_URL], 'santa': [],
    }


def _outputs(settings, product):
    if product == 'clouds':
        return [(settings.image, 'image_sha256')]
    options = getattr(settings, product)
    if product == 'norad':
        return [(options.satellite, 'satellite_sha256'), (options.satellite + '.tle', 'tle_sha256')]
    result = [(options.marker, 'marker_sha256')]
    if product in {'storm', 'eclipse'}:
        result.append((options.arc, 'arc_sha256'))
    return result


def _output_summary(fs, settings, product, record):
    present, verified = [], []
    for path, key in _outputs(settings, product):
        raw = fs.read(path, settings.max_bytes if product == 'clouds' else 32 * 1024 * 1024)
        present.append(raw is not None)
        verified.append(raw is not None and hashlib.sha256(raw).hexdigest() == record.get(key))
    return {'present': all(present), 'verified': all(verified),
            'retained': all(present) and record.get('last_outcome') == 'failed'}


def _last_errors(fs, settings):
    errors = {}
    if settings.log:
        try:
            raw = fs.read(settings.log, 8 * 1024 * 1024) or b''
        except StorageError:
            return errors, 'Event log unavailable; last error may be unknown'
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if (isinstance(event, dict) and event.get('outcome') == 'failed'
                    and isinstance(event.get('feature'), str) and event['feature'] in RUNNERS
                    and isinstance(event.get('message'), str)):
                errors[event['feature']] = {'at': event.get('time'), 'message': ' '.join(event['message'].split())[:500]}
    return errors, None


def _freshness(product, record, settings, now):
    if product == 'volcano':
        if record.get('coverage_end_at') is None:
            return 'unknown'
        try:
            volcano._validate_weekly_coverage(record['coverage_end_at'], now)
        except TotalMarkerError:
            return 'stale' if now > record['coverage_end_at'] else 'invalid'
        return 'current'
    if product == 'clouds':
        created = record.get('source_created_at')
        if created is None:
            return 'unknown'
        return ('stale' if color_for(created, now, settings.warning,
                                    ('current', 'aging', 'stale')) == 'stale' else 'current')
    if product == 'storm' and record.get('source_valid_until_at') is not None:
        return 'current' if now <= record['source_valid_until_at'] else 'stale'
    # Other products expose their own source times below. Do not invent a new
    # feed-age policy: successful parsing alone does not prove current coverage.
    return 'unknown'


class _ProbeFetcher:
    def __init__(self, client):
        self.client, self.requests = client, []

    def fetch(self, url, **kwargs):
        request = {'source': url, 'access': 'failed'}
        self.requests.append(request)
        response = self.client.fetch(url, **kwargs)
        request.update(access='ok', http_status=response.status)
        return response


def _probe_settings(settings):
    options = {}
    for name in ('quake', 'storm', 'volcano', 'norad', 'eclipse', 'santa'):
        changes = {'journal': f'.state/totalmarker/{name}-pending.json'}
        if name != 'santa':
            changes['interval'] = 0
        if name == 'norad':
            changes['satellite'] = 'satellites/norad'
        else:
            changes['marker'] = f'markers/{name}'
        if name in {'storm', 'eclipse'}:
            changes['arc'] = f'arcs/{name}'
        options[name] = replace(getattr(settings, name), **changes)
    return replace(settings, image='images/clouds.jpg', labels='markers/updatelabel',
                   state='.state/totalmarker/state.json', journal='.state/totalmarker/clouds-pending.json',
                   lock='.state/totalmarker/job.lock', log=None, interval=0,
                   labels_enabled=False, **options)


def _live(fs, settings, product, row, record, now, fetcher_factory):
    if product == 'norad':
        attempted = record.get('attempted_at', record.get('fetched_at'))
        if attempted is not None and 0 <= now - attempted < settings.norad.interval:
            row['message'] = 'Saved NORAD provider interval has not elapsed; no probe attempted'
            return
    with tempfile.TemporaryDirectory(prefix='totalmarker-health-') as directory:
        probe_fs = RootFS(Path(directory).resolve())
        probe_settings = _probe_settings(settings)
        if product == 'norad':
            icons = {style.icon for style in
                     [group.style for group in settings.norad.groups] +
                     [profile.style for profile in settings.norad.profiles] if style.icon}
            for icon in icons:
                raw = fs.read('images/' + icon)
                if raw is not None:
                    probe_fs.write('images/' + icon, raw)
        client = _ProbeFetcher(fetcher_factory())
        try:
            result = RUNNERS[product](probe_fs, probe_settings, fetcher=client, now=now)
        except TotalMarkerError as error:
            row.update(status='error', message=str(error))
        except Exception:
            row.update(status='error', message='Unexpected probe failure')
        else:
            row['message'] = (result.message if result.outcome == 'failed' else
                              'Isolated probe validated source content; normal output unchanged')
            row['content'] = 'invalid' if result.outcome == 'failed' else 'valid'
            if result.outcome == 'failed':
                failed_access = any(r['access'] == 'failed' for r in client.requests)
                row['status'] = ('access_failed' if failed_access else
                                 'stale' if 'stale' in result.message.lower() else
                                 'invalid_content' if client.requests else 'unknown')
                row['content'] = 'unknown' if failed_access or not client.requests else row['content']
                row['freshness'] = 'stale' if row['status'] == 'stale' else 'unknown'
                row['output']['retained'] = row['output']['present']
                if client.requests:
                    row['last_error'] = {'at': now, 'message': result.message}
            else:
                checked = load_state(probe_fs, probe_settings.state)['products'].get(product, {})
                row['freshness'] = _freshness(product, checked, settings, now)
                if product == 'norad' and checked.get('oldest_epoch_at') is not None:
                    row['freshness'] = 'current'  # The normal TLE validator checked its epoch.
                row['count'] = getattr(result, 'count', None)
                row['status'] = ('no_events' if row['count'] == 0 else
                                 'healthy' if row['freshness'] == 'current' else
                                 'stale' if row['freshness'] == 'stale' else 'unknown')
                row['probe_source_at'] = checked.get('source_created_at', checked.get('source_report_at',
                    checked.get('source_at', checked.get('feed_generated_at', checked.get('oldest_epoch_at')))))
                row['probe_coverage'] = {key: checked.get(key) for key in
                                        ('report_period_start', 'report_period_end', 'coverage_end_at')}
        row['requests'] = client.requests
        row['access'] = ('failed' if any(r['access'] == 'failed' for r in client.requests) else
                         'ok' if client.requests else 'not_checked')
        row['probe_attempt_at'] = now if client.requests else None


def check(fs, settings, *, live=False, now=None, fetcher_factory=Fetcher):
    now = time.time() if now is None else now
    state = load_state(fs, settings.state)
    errors, warning = _last_errors(fs, settings)
    rows = []
    for product, sources in _sources(settings).items():
        record = state['products'].get(product, {})
        enabled = product not in {'norad', 'eclipse', 'santa'} or getattr(settings, product).enabled
        row = {'product': product, 'sources': sources, 'status': 'unknown' if enabled else 'disabled',
               'access': 'not_checked', 'content': 'unknown', 'freshness': 'unknown',
               'last_check_at': record.get('checked_at'), 'last_attempt_at': record.get('attempted_at'),
               'last_success_at': (None if product == 'clouds' and record.get('timestamp_origin') == 'legacy-label'
                                   else marker_timestamp(record)),
               'last_outcome': record.get('last_outcome'),
               'source_at': record.get('source_created_at', record.get('source_report_at',
                    record.get('source_at', record.get('feed_generated_at', record.get('oldest_epoch_at'))))),
               'coverage': {key: record.get(key) for key in
                            ('report_period_start', 'report_period_end', 'coverage_end_at')},
               'last_error': errors.get(product), 'count': record.get('count'),
               'output': _output_summary(fs, settings, product, record)}
        if enabled:
            row['freshness'] = _freshness(product, record, settings, now)
            if row['freshness'] == 'stale':
                row['status'] = 'stale'
                row['output']['retained'] = row['output']['present']
            if product == 'santa':
                row.update(status='unsupported', message='Santa has no live provider')
            elif live:
                _live(fs, settings, product, row, record, now, fetcher_factory)
        rows.append(row)
    return {'mode': 'live' if live else 'saved', 'checked_at': now,
            'warning': warning, 'products': rows}


def exit_status(report):
    if any(row['status'] == 'error' for row in report['products']):
        return 2
    return int(any(row['status'] in {'access_failed', 'invalid_content', 'stale'}
                   for row in report['products']))


def format_report(report):
    def stamp(value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return 'unknown'
        try:
            return datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%d %H:%MZ')
        except (OverflowError, ValueError, OSError):
            return 'unknown'
    lines = [f"TotalMarker health ({report['mode']}; " +
             ('no network)' if report['mode'] == 'saved' else 'normal refresh state unchanged)')]
    for row in report['products']:
        lines.append(f"{row['product']}: {row['status']} | access {row['access']} | "
                     f"content {row['content']} | freshness {row['freshness']}")
        if row['status'] == 'disabled':
            continue
        lines.append('  source: ' + (', '.join(row['sources']) or 'none'))
        lines.append(f"  saved check {stamp(row['last_check_at'])}; attempt {stamp(row['last_attempt_at'])}; "
                     f"success {stamp(row['last_success_at'])}; source date {stamp(row.get('probe_source_at', row['source_at']))}")
        coverage = row.get('probe_coverage', row['coverage'])
        if coverage['report_period_start']:
            lines.append(f"  coverage {coverage['report_period_start']} through {coverage['report_period_end']}")
        if row.get('message'):
            lines.append('  ' + row['message'])
        if row['last_outcome']:
            lines.append('  saved result: ' + row['last_outcome'])
        if row['last_error'] and row['last_error']['message'] != row.get('message'):
            lines.append('  last error: ' + row['last_error']['message'])
        if row['output']['retained']:
            lines.append('  prior output retained')
    if report['warning']:
        lines.append(report['warning'])
    return '\n'.join(lines)
