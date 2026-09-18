"""Orders may only be submitted while NSE is actually open.

On 2026-09-18 entry orders went out at 15:31, 15:32 and 15:34 IST — after the
15:30 close — and the broker refused every one. Two guards were both too wide:

    MarketHoursSchedule (beat)   09:15-15:45
    dtu.is_market_hours()        09:00-16:00
    NSE continuous session       09:15-15:30

Those wider windows are deliberate for monitoring, reconciliation and equity
snapshots, which must keep running around the edges of the session. Submission
is the thing that has to stop at the close.
"""

import datetime as dt
from unittest.mock import patch

import pytest

from tb_utils.time import IST, NSE_SESSION_CLOSE, NSE_SESSION_OPEN, is_exchange_open

# Patch where it is used: time.py binds the name at import.
CAL = "tb_utils.time.is_trading_holiday"
FRIDAY = dt.date(2026, 9, 18)


def _at(hour, minute, day=FRIDAY):
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


@pytest.fixture(autouse=True)
def _trading_day():
    with patch(CAL, return_value=False):
        yield


def test_session_constants_match_nse():
    assert NSE_SESSION_OPEN == dt.time(9, 15)
    assert NSE_SESSION_CLOSE == dt.time(15, 30)


@pytest.mark.parametrize(
    "hour, minute, expected",
    [
        (9, 0, False),  # pre-open — is_market_hours() allowed this
        (9, 14, False),
        (9, 15, True),  # open
        (12, 0, True),
        (15, 30, True),  # close, inclusive
        (15, 31, False),  # the incident
        (15, 34, False),  # the incident
        (15, 44, False),  # inside the old beat window
        (15, 59, False),  # inside the old is_market_hours() window
        (16, 1, False),
    ],
)
def test_session_boundaries(hour, minute, expected):
    assert is_exchange_open(_at(hour, minute)) is expected


def test_holidays_are_closed():
    with patch(CAL, return_value=True):
        assert is_exchange_open(_at(12, 0)) is False


def test_weekend_is_closed_even_if_the_calendar_says_otherwise():
    """The weekday check is independent, so an empty holiday table cannot open a Saturday."""
    saturday = dt.date(2026, 9, 19)
    assert is_exchange_open(_at(12, 0, day=saturday)) is False


def test_naive_datetime_follows_the_library_convention():
    """to_ist() reads a naive value as UTC, so 10:00 UTC is 15:30 IST — the close."""
    assert is_exchange_open(dt.datetime(2026, 9, 18, 10, 0)) is True  # 15:30 IST
    assert is_exchange_open(dt.datetime(2026, 9, 18, 10, 1)) is False  # 15:31 IST


def test_calendar_failure_falls_back_to_the_weekday_check():
    """A Redis/DB outage must not silently open the session on a Saturday."""
    with patch(CAL, side_effect=RuntimeError("redis down")):
        assert is_exchange_open(_at(12, 0)) is True  # weekday
        assert is_exchange_open(_at(12, 0, day=dt.date(2026, 9, 19))) is False  # Saturday
