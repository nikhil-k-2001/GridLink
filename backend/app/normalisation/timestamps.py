"""Timestamp normalisation. All stored timestamps are timezone-aware UTC interval starts."""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd

ISO_DURATION_MINUTES = {"PT15M": 15, "PT30M": 30, "PT60M": 60, "PT1H": 60, "P1D": 1440}


class TimestampError(ValueError):
    pass


def duration_to_minutes(duration: str) -> int:
    try:
        return ISO_DURATION_MINUTES[duration]
    except KeyError as exc:
        raise TimestampError(f"Unsupported resolution '{duration}'") from exc


def to_utc(value: str | datetime, source_tz: str | None = None, fmt: str | None = None) -> datetime:
    """Convert a provider timestamp to UTC.

    - Aware timestamps (ISO with offset / 'Z') are converted directly.
    - Naive timestamps require `source_tz`; we never assume UTC silently.
    - Ambiguous local times (DST fall-back) raise: callers with sequence context must resolve them
      (see `localise_series`).
    """
    if isinstance(value, datetime):
        dt = value
    else:
        text = value.strip()
        if not text:
            raise TimestampError("Empty timestamp")
        try:
            dt = datetime.strptime(text, fmt) if fmt else datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TimestampError(f"Unparseable timestamp '{value}'") from exc

    if dt.tzinfo is None:
        if not source_tz:
            raise TimestampError(f"Naive timestamp '{value}' without a declared source timezone")
        tz = ZoneInfo(source_tz)
        first = dt.replace(tzinfo=tz, fold=0)
        second = dt.replace(tzinfo=tz, fold=1)
        # Non-existent local times (spring-forward gap) do not survive a UTC round trip.
        if first.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != dt:
            raise TimestampError(f"Non-existent local time '{value}' in {source_tz} (DST gap)")
        if first.utcoffset() != second.utcoffset():
            raise TimestampError(f"Ambiguous local time '{value}' in {source_tz} (DST transition)")
        dt = first
    return dt.astimezone(UTC)


def localise_series(naive: pd.Series, source_tz: str) -> pd.Series:
    """Localise an ordered series of naive local timestamps, inferring DST fall-back duplicates
    from their order (the first 02:00 is summer time, the second is winter time)."""
    return naive.dt.tz_localize(source_tz, ambiguous="infer", nonexistent="raise").dt.tz_convert("UTC")
