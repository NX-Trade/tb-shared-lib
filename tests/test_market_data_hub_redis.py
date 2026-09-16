"""Unit tests for Market Data Hub Redis keys and SyncMarketStore methods."""

import json
from unittest.mock import MagicMock

from tb_utils.redis.keys import (
    get_market_data_candle_key,
    get_market_data_subscription_key,
    get_upstox_token_key,
)
from tb_utils.redis.sync_market_store import SyncMarketStore


def test_market_data_keys():
    """Ensure key formatting adheres to ADR conventions."""
    assert (
        get_market_data_subscription_key("HINDALCO", "EQUITY") == "market_data:sub:EQUITY:HINDALCO"
    )
    assert get_market_data_candle_key("HINDALCO", "EQUITY") == "market_data:candle:EQUITY:HINDALCO"
    assert get_upstox_token_key() == "market:upstox:access_token"


def test_subscribe_market_data():
    """Ensure subscribe_market_data formats payload and writes with TTL."""
    mock_redis = MagicMock()
    store = SyncMarketStore(mock_redis)

    store.subscribe_market_data(
        symbol="RELIANCE",
        security_type="EQUITY",
        isin="INE002A01018",
        subscriber="tb_signal_bot",
        expiry_seconds=86400,
    )

    mock_redis.setex.assert_called_once()
    args = mock_redis.setex.call_args[0]
    assert args[0] == "market_data:sub:EQUITY:RELIANCE"
    assert args[1] == 86400
    payload = json.loads(args[2])
    assert payload["symbol"] == "RELIANCE"
    assert payload["instrument_key"] == "NSE_EQ|INE002A01018"
    assert payload["subscriber"] == "tb_signal_bot"


def test_get_and_set_cached_market_candles():
    """Ensure candle cache writing and retrieval works as expected."""
    mock_redis = MagicMock()
    store = SyncMarketStore(mock_redis)

    bars = [["2026-09-09T09:15:00+05:30", 2900.0, 2910.0, 2895.0, 2905.0, 10000]]
    store.set_cached_market_candles(
        "RELIANCE", "EQUITY", bars, instrument_key="NSE_EQ|INE002A01018"
    )

    mock_redis.setex.assert_called_once()
    args = mock_redis.setex.call_args[0]
    assert args[0] == "market_data:candle:EQUITY:RELIANCE"
    assert args[1] == 172800

    # Test retrieval
    mock_redis.get.return_value = json.dumps(
        {
            "symbol": "RELIANCE",
            "security_type": "EQUITY",
            "candles": bars,
        }
    )
    cached = store.get_cached_market_candles("RELIANCE", "EQUITY")
    assert cached is not None
    assert cached["symbol"] == "RELIANCE"
    assert len(cached["candles"]) == 1


def test_upstox_access_token_storage():
    """Ensure token setter and getter interact with Redis correctly."""
    mock_redis = MagicMock()
    store = SyncMarketStore(mock_redis)

    store.set_upstox_access_token("test_token_123", expiry_seconds=3600)
    mock_redis.setex.assert_called_once_with("market:upstox:access_token", 3600, "test_token_123")

    mock_redis.get.return_value = b"test_token_123"
    retrieved = store.get_upstox_access_token()
    assert retrieved == "test_token_123"
