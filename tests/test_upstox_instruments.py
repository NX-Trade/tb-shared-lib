"""Unit tests for Upstox instrument resolver and master cache."""

import datetime as dt
from unittest.mock import MagicMock

import pytest

from tb_utils.broker.upstox_instruments import (
    build_upstox_lookup,
    reset_upstox_circuit_breaker,
    resolve_upstox_instrument_key,
)


@pytest.fixture
def sample_master_items():
    """Sample Upstox master feed items representing equity, index, options, and futures."""
    # 2026-09-29 15:30:00 IST -> epoch ms
    expiry_dt = dt.datetime(
        2026, 9, 29, 15, 30, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))
    )
    expiry_ms = int(expiry_dt.timestamp() * 1000)

    return [
        {
            "segment": "NSE_EQ",
            "name": "RELIANCE INDUSTRIES LIMITED",
            "trading_symbol": "RELIANCE",
            "isin": "INE002A01018",
            "instrument_key": "NSE_EQ|INE002A01018",
        },
        {
            "segment": "NSE_INDEX",
            "name": "Nifty 50",
            "trading_symbol": "NIFTY 50",
            "instrument_key": "NSE_INDEX|Nifty 50",
        },
        {
            "segment": "NSE_FO",
            "underlying_symbol": "ADANIPORTS",
            "instrument_type": "CE",
            "strike_price": 1800.0,
            "expiry": expiry_ms,
            "trading_symbol": "ADANIPORTS 1800 CE 29 SEP 26",
            "instrument_key": "NSE_FO|81397",
        },
        {
            "segment": "NSE_FO",
            "underlying_symbol": "BAJAJ-AUTO",
            "instrument_type": "PE",
            "strike_price": 11300.0,
            "expiry": expiry_ms,
            "trading_symbol": "BAJAJ-AUTO 11300 PE 29 SEP 26",
            "instrument_key": "NSE_FO|56480",
        },
        {
            "segment": "NSE_FO",
            "underlying_symbol": "ADANIPORTS",
            "instrument_type": "FUT",
            "strike_price": None,
            "expiry": expiry_ms,
            "trading_symbol": "ADANIPORTS FUT 29 SEP 26",
            "instrument_key": "NSE_FO|68419",
        },
    ]


def test_build_upstox_lookup(sample_master_items):
    lookup = build_upstox_lookup(sample_master_items)

    # Equity & Index
    assert lookup["RELIANCE"] == "NSE_EQ|INE002A01018"
    assert lookup["INE002A01018"] == "NSE_EQ|INE002A01018"
    assert lookup["NIFTY 50"] == "NSE_INDEX|Nifty 50"
    assert lookup["NIFTY50"] == "NSE_INDEX|Nifty 50"

    # Options (compact NSE symbols)
    assert lookup["ADANIPORTS26SEP1800CE"] == "NSE_FO|81397"
    assert lookup["ADANIPORTS26SEP291800CE"] == "NSE_FO|81397"
    assert lookup["ADANIPORTS 1800 CE 29 SEP 26"] == "NSE_FO|81397"

    # Hyphenated stock option
    assert lookup["BAJAJ-AUTO26SEP11300PE"] == "NSE_FO|56480"
    assert lookup["BAJAJAUTO26SEP11300PE"] == "NSE_FO|56480"
    assert lookup["BAJAJ-AUTO 11300 PE 29 SEP 26"] == "NSE_FO|56480"

    # Futures
    assert lookup["ADANIPORTS26SEPFUT"] == "NSE_FO|68419"


def test_resolve_already_formatted_key():
    assert resolve_upstox_instrument_key("NSE_EQ|INE002A01018") == "NSE_EQ|INE002A01018"
    assert resolve_upstox_instrument_key("NSE_FO|81397") == "NSE_FO|81397"
    assert resolve_upstox_instrument_key("NSE_INDEX|Nifty 50") == "NSE_INDEX|Nifty 50"


def test_resolve_from_redis():
    mock_redis = MagicMock()
    mock_redis.hget.return_value = b"NSE_FO|81397"

    key = resolve_upstox_instrument_key("ADANIPORTS26SEP1800CE", redis_client=mock_redis)
    assert key == "NSE_FO|81397"
    mock_redis.hget.assert_called_with("market:upstox:instruments", "ADANIPORTS26SEP1800CE")


def test_resolve_from_db():
    mock_row = MagicMock()
    mock_row.isin = "INE742F01042"
    mock_row.is_index = 0

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_row

    key = resolve_upstox_instrument_key("ADANIPORTS", db=mock_db)
    assert key == "NSE_EQ|INE742F01042"


def test_resolve_derivative_safety_guard_never_returns_nse_eq():
    """Crucial safety test: an unresolvable option contract MUST NOT return NSE_EQ|..."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    mock_redis = MagicMock()
    mock_redis.hget.return_value = None
    mock_redis.hlen.return_value = 50000  # not empty, so no cold fetch

    key = resolve_upstox_instrument_key(
        "NONEXISTENT26SEP99999CE",
        redis_client=mock_redis,
        db=mock_db,
    )
    # Must return None, NEVER "NSE_EQ|NONEXISTENT26SEP99999CE"
    assert key is None


def test_reset_upstox_circuit_breaker():
    mock_redis = MagicMock()
    res = reset_upstox_circuit_breaker(mock_redis, endpoint_class="order")
    assert res is True
    mock_redis.hset.assert_called_once_with(
        "http:breaker:UPSTOX:order",
        mapping={"state": 1, "failures": 0},
    )
