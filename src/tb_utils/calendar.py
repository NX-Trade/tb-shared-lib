"""Market calendar utilities for nx-trade.

Provides canonical functions ``is_trading_holiday()`` and
``get_trading_holidays_for_year()`` used across tb-collector, tb-execution,
and tb-signal-bot to skip execution on weekends and NSE trading holidays.

Cache strategy
--------------
Holidays for a given year are fetched once from the ``trading_holiday`` DB
table and stored in Redis under ``market_data:trading_holidays:{year}`` with a
25-hour TTL.

Fail-safe behaviour
-------------------
If both Redis and the DB are unavailable, the function returns ``False`` so the
task runs anyway — a spurious fetch attempt is safer than a silent data gap.
"""

# stdlib
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

# third-party
import redis

# internal
from tb_utils.config.db_session import get_session_factory
from tb_utils.models.corporate_event import TradingHoliday
from tb_utils.redis.keys import get_trading_holidays_key

logger = logging.getLogger(__name__)

# IST offset
_IST = timezone(timedelta(hours=5, minutes=30))

# Redis TTL: 25 hours ensures the cache refreshes at least once per day even
# if beat fires at slightly different wall-clock times.
_CACHE_TTL_SECONDS = 25 * 3600

# Cached client instance
_redis_client: Optional[redis.Redis] = None


def _get_redis_client() -> Optional[redis.Redis]:
    """Return a Redis client, creating one lazily from environment variables."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = (
        os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "redis://localhost:6379/0"
    )
    try:
        _redis_client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        return _redis_client
    except Exception:
        logger.exception("Failed to connect to Redis for calendar lookup.")
        return None


def _today_ist() -> date:
    """Return today's date in IST."""
    return datetime.now(_IST).date()


def _fetch_holidays_from_db(year: int) -> set[date]:
    """Query the trading_holiday table and return a set of holiday dates for *year*."""
    session = get_session_factory()()
    try:
        rows = (
            session.query(TradingHoliday.holiday_date)
            .filter(
                TradingHoliday.holiday_date >= date(year, 1, 1),
                TradingHoliday.holiday_date < date(year + 1, 1, 1),
            )
            .all()
        )
        return {
            row.holiday_date.date() if isinstance(row.holiday_date, datetime) else row.holiday_date
            for row in rows
        }
    finally:
        session.close()


def get_trading_holidays_for_year(year: int) -> set[date]:
    """Return a set of NSE trading holiday dates for *year*.

    Tries Redis first; falls back to the DB on a cache miss and populates the
    cache for subsequent calls. Returns an empty set if both sources fail so
    the caller can degrade gracefully.
    """
    redis_key = get_trading_holidays_key(year)
    client = _get_redis_client()

    # ── 1. Try Redis cache ──────────────────────────────────────────────────
    if client is not None:
        try:
            raw = client.get(redis_key)
            if raw:
                date_strings = json.loads(raw)
                holidays = {date.fromisoformat(d) for d in date_strings}
                logger.debug(
                    "Trading holidays for %d loaded from Redis cache (%d dates).",
                    year,
                    len(holidays),
                )
                return holidays
        except Exception:
            logger.exception(
                "Failed to read trading holidays from Redis for year %d. Falling back to DB.",
                year,
            )

    # ── 2. Fall back to DB ──────────────────────────────────────────────────
    try:
        holidays = _fetch_holidays_from_db(year)
        logger.info("Fetched %d trading holidays for %d from DB.", len(holidays), year)
    except Exception:
        logger.exception(
            "Failed to fetch trading holidays from DB for year %d. Returning empty set.",
            year,
        )
        return set()

    # ── 3. Populate Redis cache ─────────────────────────────────────────────
    if client is not None:
        try:
            payload = json.dumps([d.isoformat() for d in holidays])
            client.setex(redis_key, _CACHE_TTL_SECONDS, payload)
            logger.debug(
                "Trading holidays for %d cached in Redis (TTL=%ds).",
                year,
                _CACHE_TTL_SECONDS,
            )
        except Exception:
            logger.exception("Failed to cache trading holidays in Redis for year %d.", year)

    return holidays


def is_trading_holiday(check_date: Optional[date] = None) -> bool:
    """Return True if *check_date* is a weekend or an NSE trading holiday.

    Args:
        check_date: The date to evaluate. Defaults to today in IST.

    Returns:
        True  → task should be skipped (holiday or weekend).
        False → task should proceed (normal trading day, or fail-safe if error).
    """
    if check_date is None:
        check_date = _today_ist()

    # ── Weekends (Monday=0 … Sunday=6) ──────────────────────────────────────
    if check_date.weekday() >= 5:
        logger.info(
            "is_trading_holiday: %s is a %s — skipping.",
            check_date,
            check_date.strftime("%A"),
        )
        return True

    # ── Trading holidays ────────────────────────────────────────────────────
    try:
        holidays = get_trading_holidays_for_year(check_date.year)
        if check_date in holidays:
            logger.info(
                "is_trading_holiday: %s is a trading holiday — skipping.",
                check_date,
            )
            return True
    except Exception:
        logger.exception(
            "Unexpected error in is_trading_holiday for %s. Defaulting to False.",
            check_date,
        )
        return False

    return False
