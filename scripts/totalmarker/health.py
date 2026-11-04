"""Read-only health summaries; live validators run in disposable output roots."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time

from .diagnostics import observation
from .errors import StorageError, TotalMarkerError
from .features import clouds, eclipse, norad, quake, storm, volcano
from .http import Fetcher
from .labels import color_for
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
    present, verified, errors = [], [], []
    for path, key in _outputs(settings, product):
        try:
            raw = fs.read(path, settings.max_bytes if product == 'clouds' else 32 * 1024 * 1024)
        except StorageError as error:
            # A read limit or one broken output must not hide the other products.
            # Metadata establishes presence without reading unbounded contents.
            try:
                exists = fs.file_stat(path) is not None
            except StorageError:
                exists = False
            present.append(exists)
            verified.append(False)
            errors.append(str(error))
        else:
            present.append(raw is not None)
            verified.append(raw is not None and hashlib.sha256(raw).hexdigest() == record.get(key))
    summary = {'present': all(present), 'verified': all(verified),
               'retained': all(present) and record.get('last_outcome') == 'failed'}
    if errors:
        summary['error'] = '; '.join(dict.fromkeys(errors))
    return summary


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


def cloud_freshness(created, warning, now):
    """Shared saved-cloud age policy, without access checks or filesystem reads."""
    if created is None:
        return 'unknown'
    return ('stale' if color_for(created, now, warning,
                                ('current', 'aging', 'stale')) == 'stale' else 'current')


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
        return cloud_freshness(record.get('source_created_at'), settings.warning, now)
    if product == 'storm' and record.get('source_valid_until_at') is not None:
        return 'current' if now <= record['source_valid_until_at'] else 'stale'
    # Other products expose their own source times below. Do not invent a new
    # feed-age policy: successful parsing alone does not prove current coverage.
    return 'unknown'


def observational_freshness(product,record,now):
    """Read-only shared age policy for frozen Earth observational snapshots."""
    if product not in ('quake','storm','volcano'):raise ValueError('Unsupported observational product')
    return _freshness(product,record,None,now)


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
        facts = observation(record)
        enabled = product not in {'norad', 'eclipse', 'santa'} or getattr(settings, product).enabled
        row = {'product': product, 'sources': sources, 'status': 'unknown' if enabled else 'disabled',
               'access': 'not_checked', 'content': 'unknown', 'freshness': 'unknown',
               'last_check_at': facts['checked_at'], 'last_attempt_at': facts['attempted_at'],
               'last_success_at': facts['successful_at'],
               'last_publication_at': facts['published_at'],
               'last_outcome': facts['last_outcome'], 'source_at': facts['source_at'],
               'coverage': facts['coverage'],
               'last_error': facts['last_error'] or errors.get(product), 'count': record.get('count'),
               'output': _output_summary(fs, settings, product, record)}
        if enabled:
            row['freshness'] = _freshness(product, record, settings, now)
            if not live and row['last_outcome'] == 'failed':
                row['status'] = 'refresh_failed'
            if row['freshness'] == 'stale':
                row['status'] = 'stale'
                row['output']['retained'] = row['output']['present']
            if product == 'santa':
                row.update(status='unsupported', message='Santa has no live provider')
            elif live:
                try:
                    _live(fs, settings, product, row, record, now, fetcher_factory)
                except TotalMarkerError as error:
                    row.update(status='error', message=str(error))
                except Exception:
                    row.update(status='error', message='Unexpected probe setup failure')
        # Inspect journal presence only: health must never replay or alter one.
        journal = settings.journal if product == 'clouds' else getattr(settings, product).journal
        try:
            pending = fs.file_stat(journal) is not None
        except StorageError as error:
            row.update(status='error', recovery_error=str(error))
        else:
            if pending:
                row.update(status='error', recovery_error=(
                    'Pending publication requires recovery with its original configuration; '
                    'preserve the journal and inspect normal command errors'))
        if row['output'].get('error'):
            row['status'] = 'error'
        rows.append(row)
    return {'mode': 'live' if live else 'saved', 'checked_at': now,
            'warning': warning, 'products': rows}


def exit_status(report):
    if any(row['status'] == 'error' for row in report['products']):
        return 2
    return int(any(row['status'] in {'access_failed', 'invalid_content', 'stale', 'refresh_failed'}
                   for row in report['products']))


_TITLES = {'clouds': 'Clouds', 'quake': 'Earthquakes', 'storm': 'Storms',
           'volcano': 'Volcanoes', 'norad': 'Satellites', 'eclipse': 'Eclipses',
           'santa': 'Santa'}


def _stamp(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 'unknown'
    try:
        return datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%d %H:%MZ')
    except (OverflowError, ValueError, OSError):
        return 'unknown'


def _success_age(value, now):
    if value is None:
        return 'no successful refresh recorded'
    age = now - value
    if age < 0:
        return 'last success ' + _stamp(value)
    if age < 60:
        age_text = 'just now'
    elif age < 3600:
        age_text = f'{int(age // 60)}m ago'
    elif age < 86400:
        age_text = f'{int(age // 3600)}h ago'
    else:
        age_text = f'{int(age // 86400)}d ago'
    return 'last success ' + age_text


def _brief(message):
    # HTTP diagnostics append headers after a semicolon. Keep them in verbose
    # output, along with the complete provider message and recorded timestamps.
    text = ' '.join((message or '').splitlines()[:1]).split(';', 1)[0].strip()
    return text if len(text) <= 110 else text[:107] + '...'


def _current_error(row):
    error = row['last_error']
    success = row['last_success_at']
    return (error is not None and isinstance(error.get('at'), (int, float))
            and (success is None or error['at'] >= success)
            and row['last_outcome'] == 'failed')


def _summary(row, live):
    status, freshness = row['status'], row['freshness']
    if row['output'].get('error'):
        return 'saved output unreadable', _brief(row['output']['error'])
    if row.get('recovery_error'):
        return 'publication recovery required', _brief(row['recovery_error'])
    if status == 'error' and not live:
        return 'saved status unavailable', _brief(row.get('message'))
    if status == 'unsupported':
        return 'not supported', _brief(row.get('message'))
    if live:
        if status == 'access_failed':
            return 'access failed', _brief(row.get('message'))
        if status in {'invalid_content', 'error'}:
            return ('invalid content' if status == 'invalid_content' else 'probe failed',
                    _brief(row.get('message')))
        if status == 'stale':
            if row['product'] == 'volcano' and row['access'] == 'ok':
                return 'reachable; report parsed; coverage stale', ''
            return 'stale data', _brief(row.get('message'))
        if row['content'] == 'valid':
            detail = ('no events' if status == 'no_events' else
                      'current' if freshness == 'current' else 'freshness not assessed')
            return 'validation passed; ' + detail, ''
        return 'not probed', _brief(row.get('message'))
    detail = _brief(row['last_error']['message']) if _current_error(row) else ''
    if freshness == 'stale':
        return ('coverage stale' if row['product'] == 'volcano' else 'saved data stale'), detail
    if row['last_outcome'] == 'failed':
        return 'refresh failed', detail
    if not row['output']['present']:
        return 'no saved output', ''
    if not row['output']['verified']:
        return 'saved output unverified', ''
    return ('saved output current' if freshness == 'current' else
            'saved output; freshness not assessed'), ''


def _report_tone(row, live):
    if row['status'] in {'error', 'access_failed', 'invalid_content', 'refresh_failed'}:
        return 'error'
    if not live and row['last_outcome'] == 'failed':
        return 'error'
    if row['status'] == 'stale' or row['freshness'] == 'stale':
        return 'warning'
    if not row['output']['present'] or not row['output']['verified']:
        return 'warning'
    if row['freshness'] == 'current':
        return 'good'
    return 'unknown'  # Freshness not assessed is not a failure.


def _report_color(row, live):
    return {'error':'\033[31m','warning':'\033[33m','good':'\033[32m'}.get(_report_tone(row,live),'')

def format_report(report, *, verbose=False, color=False):
    live = report['mode'] == 'live'
    lines = [('TotalMarker live check (normal output unchanged)' if live else
              'TotalMarker saved status (no network check)')]
    disabled = []
    for row in report['products']:
        title = _TITLES[row['product']]
        if row['status'] == 'disabled':
            disabled.append(title)
            continue
        summary, detail = _summary(row, live)
        style = _report_color(row, live) if color else ''
        if style:
            title = style + title + '\033[0m'
        line = f"{title}: {summary}; {_success_age(row['last_success_at'], report['checked_at'])}"
        if detail:
            line += ' — ' + detail
        if row['output']['retained'] and (live or row['last_outcome'] == 'failed' or row['status'] == 'stale'):
            line += '; prior output retained'
        lines.append(line)
    if disabled:
        disabled_line = 'Disabled: ' + ', '.join(disabled)
        lines.append('\033[2m' + disabled_line + '\033[0m' if color else disabled_line)
    if report['warning']:
        lines.append(report['warning'])
    if verbose:
        lines.append('\nDetails:')
        for row in report['products']:
            if row['status'] == 'disabled':
                continue
            lines.append(f"{_TITLES[row['product']]}: status {row['status']}; access {row['access']}; "
                         f"content {row['content']}; freshness {row['freshness']}")
            lines.append('  source: ' + (', '.join(row['sources']) or 'none'))
            lines.append(f"  saved check {_stamp(row['last_check_at'])}; attempt {_stamp(row['last_attempt_at'])}; "
                         f"success {_stamp(row['last_success_at'])}; publication {_stamp(row.get('last_publication_at'))}; "
                         f"source date {_stamp(row['source_at'])}")
            for label, coverage in [('saved coverage', row['coverage']),
                                    ('probe coverage', row.get('probe_coverage', {}))]:
                if coverage.get('report_period_start'):
                    lines.append(f"  {label}: {coverage['report_period_start']} through {coverage['report_period_end']}")
            if row.get('probe_source_at') is not None:
                lines.append('  probe source date: ' + _stamp(row['probe_source_at']))
            if row['output'].get('error'):
                lines.append('  saved output error: ' + row['output']['error'])
            if row.get('recovery_error'):
                lines.append('  publication recovery: ' + row['recovery_error'])
            if row.get('message'):
                lines.append('  probe result: ' + row['message'])
            if row['last_outcome']:
                lines.append('  saved result: ' + row['last_outcome'])
            error = row['last_error']
            if error:
                note = ('; before last success' if error.get('at') is not None
                        and row['last_success_at'] is not None
                        and error['at'] < row['last_success_at'] else '')
                lines.append(f"  recorded error {_stamp(error.get('at'))}{note}: {error['message']}")
    return '\n'.join(lines)


def format_dashboard(report):
    """Bounded plain records for management's explicit saved-health action.

    Status semantics stay here. No terminal controls cross this presentation boundary; the caller must not evaluate the records.
    """
    if report['mode'] != 'saved':
        raise ValueError('Dashboard records require saved health.')
    def plain(value):
        return ''.join(c if c.isprintable() else ' ' for c in str(value))[:240]
    lines=['snapshot\t'+_stamp(report['checked_at'])]
    for row in report['products']:
        title=_TITLES[row['product']]
        if row['status']=='disabled':tone,summary,detail='disabled','disabled',''
        else:
            tone=_report_tone(row,False)
            summary,detail=_summary(row,False)
            summary+='; '+_success_age(row['last_success_at'],report['checked_at'])
            if row['output']['retained']:summary+='; prior output retained'
        lines.append(tone+'\t'+title+'\t'+plain(summary)+'\t'+plain(detail))
    if report['warning']:lines.append('note\t'+plain(report['warning']))
    return '\n'.join(lines)
