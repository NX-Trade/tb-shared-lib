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
