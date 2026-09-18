"""Date and time utilities for Indian financial markets (NSE/BSE).

Provides canonical timezone objects (IST, UTC), standard date conversion functions,
and trading day determination to ensure consistency across tb-collector, tb-signal-bot,
and tb-backend.

Adheres to:
    - IST = UTC+05:30 as the market reference timezone.
    - SARGable timestamp range queries ([start_utc, end_utc)) replacing non-SARGable func.date().
"""

from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import and_

# Canonical timezones
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
UTC = UTC

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%Y/%m/%d",
    "%d/%m/%Y",
)


def now_ist() -> datetime:
    """Return the current timezone-aware datetime in IST."""
    return datetime.now(IST)


def today_ist() -> date:
    """Return the current calendar date in IST."""
    return datetime.now(IST).date()


def to_ist(dt: datetime | date | str) -> datetime:
    """Convert a datetime, date, or date string to timezone-aware IST datetime.

    If dt is a naive datetime, assumes UTC and converts to IST.
    If dt is a date, returns midnight at start of that date in IST.
    If dt is a string, attempts ISO and standard date format parsing.
    """
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(IST)

    if isinstance(dt, date):
        return datetime.combine(dt, time.min, tzinfo=IST)

    if isinstance(dt, str):
        s = dt.strip()
        # Try ISO first (e.g. 2026-09-17T10:00:00Z or 2026-09-17)
        try:
            parsed = datetime.fromisoformat(s)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(IST)
        except ValueError:
            pass

        # Try standard date formats
        for fmt in _DATE_FORMATS:
            try:
                parsed_dt = datetime.strptime(s, fmt)
                return parsed_dt.replace(tzinfo=IST)
            except ValueError:
                continue

        raise ValueError(f"Unable to parse string to IST datetime: {dt!r}")

    raise TypeError(f"Expected datetime, date, or str, got {type(dt).__name__}")


def to_utc(dt: datetime | date | str) -> datetime:
    """Convert a datetime, date, or date string to timezone-aware UTC datetime.

    If dt is a naive datetime, assumes IST and converts to UTC.
    If dt is a date, returns midnight at start of that date in IST converted to UTC.
    If dt is a string, parses to IST first then converts to UTC.
    """
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(UTC)

    if isinstance(dt, date):
        return datetime.combine(dt, time.min, tzinfo=IST).astimezone(UTC)

    if isinstance(dt, str):
        ist_dt = to_ist(dt)
        return ist_dt.astimezone(UTC)

    raise TypeError(f"Expected datetime, date, or str, got {type(dt).__name__}")


def trading_day(ts: Optional[datetime | date | str] = None) -> date:
    """Return the canonical IST trading day for a given timestamp, date, or string.

    Args:
        ts: Timestamp, date, string, or None. If None, returns today's date in IST.

    Returns:
        date: The calendar date in Indian Standard Time (IST).
    """
    if ts is None:
        return today_ist()

    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.astimezone(IST).date()

    if isinstance(ts, date):
        return ts

    if isinstance(ts, str):
        return to_ist(ts).date()

    raise TypeError(f"Expected None, datetime, date, or str, got {type(ts).__name__}")


def ist_day_bounds_utc(
    trade_date: Optional[datetime | date | str] = None,
) -> tuple[datetime, datetime]:
    """Return the half-open UTC datetime interval [start_utc, end_utc) for an IST day.

    For a given trade_date (e.g., 2026-09-17):
        - start_utc = 2026-09-17 00:00:00 IST -> 2026-09-16 18:30:00 UTC
        - end_utc   = 2026-09-18 00:00:00 IST -> 2026-09-17 18:30:00 UTC

    This interval is SARGable on indexed UTC/timestamptz columns and provides exact
    date-filtering semantics without relying on non-standard func.date() casts.
    """
    t_date = trading_day(trade_date)
    start_ist = datetime.combine(t_date, time.min, tzinfo=IST)
    end_ist = start_ist + timedelta(days=1)
    return start_ist.astimezone(UTC), end_ist.astimezone(UTC)


def sql_ist_day_range(column, trade_date: Optional[datetime | date | str] = None):
    """Return a SQLAlchemy binary expression filtering a timestamp column by IST date.

    Produces:
        and_(column >= start_utc, column < end_utc)

    Example:
        db.query(TradingSignal).filter(sql_ist_day_range(TradingSignal.created_at, as_of))
    """
    start_utc, end_utc = ist_day_bounds_utc(trade_date)
    return and_(column >= start_utc, column < end_utc)
