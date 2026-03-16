"""Redis Key formats for market data caching."""


def get_contracts_key(symbol: str) -> str:
    return f"market_data:contracts:{symbol}"


def get_derived_metrics_key(symbol: str) -> str:
    return f"market_data:derived:{symbol}"


def get_market_breadth_key(exchange: str) -> str:
    return f"market_data:breadth:{exchange}"


def get_instrument_spot_key(symbol: str) -> str:
    return f"market_data:spot:{symbol}"
