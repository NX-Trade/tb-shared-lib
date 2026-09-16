"""Redis Key formats for market data caching."""


def get_contracts_key(symbol: str) -> str:
    return f"market_data:contracts:{symbol}"


def get_derived_metrics_key(symbol: str) -> str:
    return f"market_data:derived:{symbol}"


def get_market_breadth_key(exchange: str) -> str:
    return f"market_data:breadth:{exchange}"


def get_instrument_spot_key(symbol: str) -> str:
    return f"market_data:spot:{symbol}"


def get_fno_ban_list_key() -> str:
    return "market_data:fno_ban_list"


def get_regime_current_key() -> str:
    return "signal_bot:regime:current"


def get_regime_channel() -> str:
    return "signal_bot:regime:transitions"


def get_watchlist_key() -> str:
    return "signal_bot:watchlist:focus"


def get_macro_indicator_key(symbol: str) -> str:
    return f"market_data:macro:{symbol}"


def sentiment_rolling(symbol: str) -> str:
    return f"sentiment:rolling:{symbol}"


def get_sentiment_rolling_key(symbol: str) -> str:
    return f"sentiment:rolling:{symbol}"


def get_trading_holidays_key(year: int) -> str:
    return f"market_data:trading_holidays:{year}"


def get_instruments_master_key() -> str:
    return "market_data:instruments:master"


def get_market_data_subscription_key(symbol: str, security_type: str = "EQUITY") -> str:
    """Active demand subscription marker in Redis. TTL = 1 day."""
    return f"market_data:sub:{security_type}:{symbol}"


def get_market_data_candle_key(symbol: str, security_type: str = "EQUITY") -> str:
    """1-minute OHLCV candle cache in Redis. TTL = 2 days."""
    return f"market_data:candle:{security_type}:{symbol}"


def get_upstox_token_key() -> str:
    """Active Upstox OAuth2 access token in Redis."""
    return "market:upstox:access_token"
