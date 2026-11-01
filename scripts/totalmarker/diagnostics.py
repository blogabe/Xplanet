"""Common diagnostic facts; product validation and publication remain product-owned.

Stored records keep their existing schema. New checks add actual request attempt
and bounded last-error facts; views derive common names instead of duplicating
source timestamps or treating local checks as successful HTTP requests.
"""
import math

from .errors import StorageError

PRODUCTS = ('clouds', 'quake', 'storm', 'volcano', 'norad', 'eclipse', 'santa')


class Attempt:
    """Count actual client invocations, including ones that raise an error."""
    def __init__(self, client):
        self.client = client
        self.requests = 0

    def fetch(self, *args, **kwargs):
        self.requests += 1
        return self.client.fetch(*args, **kwargs)


def finish(record, now, outcome, message, attempt):
    """Add diagnostics to the same journaled record as the product result.

    An interrupted non-NORAD request may have no saved attempt; only NORAD's
    existing provider-cooldown rule persists its attempt before network access.
    Last error is historical and survives a later successful check.
    """
    if attempt.requests:
        record['attempted_at'] = now
    record['last_outcome'] = outcome
    if outcome == 'failed':
        record['last_error'] = {'at': now, 'message': ' '.join(message.split())[:500].rstrip()}


def success_at(record):
    # Legacy label estimates are never evidence of a successful publication.
    if record.get('timestamp_origin') == 'legacy-label':
        return None
    successful = record.get('successful_at')
    return successful if successful is not None else record.get('installed_at')


def observation(record):
    """Read common facts from new or legacy records without mutating either."""
    return {
        'checked_at': record.get('checked_at'),
        'attempted_at': record.get('attempted_at'),
        'successful_at': success_at(record),
        'published_at': (None if record.get('timestamp_origin') == 'legacy-label'
                         else record.get('installed_at')),
        'source_at': next((record[key] for key in
                           ('source_created_at', 'source_report_at', 'source_at',
                            'feed_generated_at', 'oldest_epoch_at')
                           if record.get(key) is not None), None),
        'coverage': {key: record.get(key) for key in
                     ('report_period_start', 'report_period_end', 'coverage_end_at')},
        'last_outcome': record.get('last_outcome'),
        'last_error': record.get('last_error'),
    }


def validate(record):
    """Validate additive facts before persistence and during journal recovery."""
    for key in ('attempted_at', 'successful_at'):
        value = record.get(key)
        if value is not None and (type(value) not in (int, float)
                or not math.isfinite(value) or not 0 <= value <= 32503680000):
            raise StorageError('Invalid diagnostic timestamp')
    error = record.get('last_error')
    if error is not None:
        if not isinstance(error, dict) or set(error) != {'at', 'message'}:
            raise StorageError('Invalid saved diagnostic error')
        at, message = error['at'], error['message']
        if (type(at) not in (int, float) or not math.isfinite(at)
                or not 0 <= at <= 32503680000 or not isinstance(message, str)
                or len(message) > 500 or message != ' '.join(message.split())):
            raise StorageError('Invalid saved diagnostic error')
