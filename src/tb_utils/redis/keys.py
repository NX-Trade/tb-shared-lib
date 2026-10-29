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


def get_fno_ban_meta_key() -> str:
    """Which trading day the ban list under ``get_fno_ban_list_key`` was synced for."""
    return "market_data:fno_ban_list:meta"


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
    """Active Upstox OAuth2 access token in Redis.

    The platform-wide key, written as an alias alongside the per-account one
    below. Readers that have no account context still use it; prefer
    ``get_broker_token_key`` wherever the account is known.
    """
    return "market:upstox:access_token"


def get_broker_token_key(broker_type: str, client_code: str) -> str:
    """Daily OAuth access token for one broker and client account.

    A token belongs to the account that authenticated, not to the platform,
    so two accounts on the same broker must not share a slot — the second
    login would otherwise overwrite the first and both would act as one.
    """
    return f"broker:{broker_type.lower()}:access_token:{client_code.upper()}"


def get_breeze_session_key(account_id: int) -> str:
    """Today's ICICI Breeze ``api_session`` for one client account.

    Set daily after the browser login; TTL runs to ~06:00 IST.
    """
    return f"broker:breeze:session:{account_id}"


def get_option_chain_key(symbol: str) -> str:
    """Live option chain cache in Redis. TTL = 6 hours (21,600s)."""
    return f"market_data:option_chain:{symbol.upper()}"


def get_fresh_chain_key(symbol: str) -> str:
    """The on-demand option-chain snapshot for one underlying, fetched for a trade decision.

    Short-lived and separate from ``get_option_chain_key`` on purpose: that cache is refreshed every
    15 minutes and lives 6 hours, which is fine for dashboards and wrong for pricing an order.
    """
    return f"market_data:fresh_chain:{symbol.strip().upper()}"


def get_lot_size_key(symbol: str) -> str:
    """Market lot size cache in Redis. TTL = 1 day (86,400s)."""
    return f"market_data:lot_size:{symbol.upper()}"


def get_gemini_active_key_key() -> str:
    """Index (0 or 1) of the Gemini API key currently in use; flips on a 429."""
    return "gemini:active_key_index"


def get_gemini_daily_counter_key(kind: str, day: str) -> str:
    """Per-day Gemini counter: ``kind`` is ``calls`` or ``cost_inr``, ``day`` is YYYY-MM-DD."""
    return f"gemini:{kind}:{day}"


def get_gemini_cooldown_key() -> str:
    """Set with a TTL when every Gemini key is out of quota; callers pause until it expires."""
    return "gemini:quota_cooldown"


def get_gemini_alert_key(kind: str) -> str:
    """Debounce key so a Gemini key failover or degradation alerts once an hour, not once a call."""
    return f"gemini:alert:{kind}"


def get_upstox_chain_lock_key(tag: str) -> str:
    """Lock held while one Upstox option-chain collection run is in flight, so two never overlap."""
    return f"upstox:chain_lock:{tag}"


def get_trading_halted_key() -> str:
    """Flag set in Redis when live trading is halted/panic initiated."""
    return "TRADING_HALTED"


def get_circuit_breaker_alert_key(kind: str) -> str:
    """Debounce key for circuit-breaker trip alerts, one per trip kind.

    The breaker is evaluated every 15 s by tb-trade-engine's Celery beat; once it
    has tripped it would otherwise send a Telegram alert and write a SystemLog
    row on every tick. Setting this key with a TTL suppresses repeats.
    """
    return f"execution:circuit_breaker:alerted:{kind}"


def get_paper_order_key(broker_order_id: str) -> str:
    """Resting (unfilled) paper-broker order state. TTL = 7 days.

    Written by tb-trade-engine's PaperBrokerAdapter so LIMIT/STOP orders that are
    not immediately marketable persist across worker restarts and are evaluated
    against the live spot on every status poll instead of being fabricated.
    """
    return f"paper:order:{broker_order_id}"


def get_live_intraday_switch_key() -> str:
    """Redis key controlling the live intraday execution switch (values: 'true'/'false')."""
    return "execution:live_intraday_switch"


def get_stc_dynamic_exit_key(symbol: str, side: str) -> str:
    """Flag set when STC's dynamic trend-exit condition (EMA21 cross / EFI sign
    flip) fires for a symbol+side. Written by the 5-min STC scan task
    (evaluate_stc_dynamic_exit), read by the 15s position monitor. Short TTL —
    the scan re-evaluates and re-sets it every cycle, so it never outlives the
    bar it was computed from.
    """
    return f"execution:stc_dynamic_exit:{symbol}:{side}"
