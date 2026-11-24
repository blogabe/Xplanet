"""Calendar primitives shared by JTWC products, not their timing policies."""

from datetime import datetime, timedelta, timezone


def nearest_report_time(
    day: int, hour: int, minute: int, reference_at: float,
) -> datetime | None:
    """Resolve a monthless UTC stamp around the bulletin's reference month."""
    month_start = datetime.fromtimestamp(reference_at, timezone.utc).replace(day=1)
    candidates = []
    for month in (month_start - timedelta(days=1), month_start,
                  month_start + timedelta(days=32)):
        try:
            candidates.append(datetime(month.year, month.month, day, hour, minute,
                                       tzinfo=timezone.utc))
        except ValueError:
            continue
    return min(candidates, key=lambda value: abs(value.timestamp() - reference_at),
               default=None)


def storm_season(fix: datetime, basin: str) -> int:
    return fix.year + (basin == "SH" and fix.month >= 7)
