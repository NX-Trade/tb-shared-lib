"""Common Utils."""

import logging
from datetime import datetime, timedelta

from .enums import MarketTimingEnum

logger = logging.getLogger(__name__)


def indexed_data(index: str, data: list[dict]) -> dict:
    """Return a dict keyed by the formatted index string."""
    return {index.format(**datum): datum for datum in data}


def separate_by_index(index: str, cache: list[dict], live: list[dict]) -> tuple:
    """Separate live data into records to POST (new) and PUT (existing).

    Compares live data against cached data using the given index template
    to determine which records need to be created vs updated.

    Args:
        index: A format string template used to derive the key (e.g. "{symbol}")
        cache: List of existing/cached records as dicts
        live: List of incoming live records as dicts

    Returns:
        Tuple of (post_data, put_data) where post_data are new records
        and put_data are records that already exist.
    """
    cache_indexed = indexed_data(index, cache)
    live_indexed = indexed_data(index, live)

    live_keys = set(live_indexed.keys())
    cache_keys = set(cache_indexed.keys())

    post_keys = live_keys.difference(cache_keys)
    put_keys = live_keys.intersection(cache_keys)

    post_data = [live_indexed[key] for key in post_keys]
    put_data = [live_indexed[key] for key in put_keys]
    return post_data, put_data


def filter_fno_securities(data: list[dict]) -> tuple:
    """Filter securities into FNO and non-FNO buckets.

    Args:
        data: List of security dicts with 'security' and 'is_fno' keys

    Returns:
        Tuple of (fno_list, non_fno_list) — lists of security identifiers
    """
    fno = list({item["security"] for item in data if item["is_fno"]})
    non_fno = list({item["security"] for item in data if not item["is_fno"]})
    return fno, non_fno


def get_next_thursday(dt=None) -> str:
    """Return the date of the next Thursday from the given date.

    Args:
        dt: The reference date (defaults to today)

    Returns:
        Date string in '%d-%b-%Y' format (e.g. '27-Feb-2026')
    """
    day_dict = {
        "monday": 3,
        "tuesday": 2,
        "wednesday": 1,
        "thursday": 0,
        "friday": 6,
        "saturday": 5,
        "sunday": 4,
    }
    dt = dt or datetime.today()
    expected_days = day_dict.get(dt.strftime("%A").lower())
    return (dt + timedelta(days=expected_days)).strftime("%d-%b-%Y")


def validate_quantity(number, valid_value=0) -> int:
    """Validate that a quantity is above the minimum valid value.

    Args:
        number: The quantity to validate
        valid_value: The minimum acceptable value (exclusive)

    Returns:
        The original number if valid, else 0
    """
    if not number or number <= valid_value:
        logger.warning("Value: %s must be greater than %s.", number, valid_value)
        return 0
    return number


def is_trading_hours_open() -> bool:
    """Return True if current time is within trading hours."""
    return bool(
        MarketTimingEnum.PRE_OPEN.value
        < datetime.now().time()
        < MarketTimingEnum.CLOSE.value
    )
