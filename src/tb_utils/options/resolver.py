"""Resolves a concrete, tradeable option contract for a directional signal.

Background
----------
The NSE option-chain feed does not supply Greeks -- the ``option_chain.delta``,
``gamma``, ``theta``, and ``vega`` columns are written as NULL by the collector.
Historically, scanners picked a rough ATM strike estimate and set ``entry_price``
to the *underlying spot price* -- not an actual option premium, so the resulting
signal wasn't directly tradeable as a derivative.

This module provides a unified contract resolver for services (tb-signal-bot,
tb-execution, tb-backend): given a symbol and a directional view
(BUY -> bullish -> resolve a CE, SELL -> bearish -> resolve a PE), it:

  1. Restricts to expiries with enough time-to-expiry to avoid pure
     gamma/theta noise (``MIN_DTE_DAYS``).
  2. Restricts to strikes that clear a liquidity floor (``MIN_OPEN_INTEREST`` /
     ``MIN_VOLUME``) so the resolved contract can actually be filled.
  3. Checks Redis cache first (populated every 3m by tb-collector) before
     falling back to the PostgreSQL ``option_chain`` table.
  4. Computes live Greeks per candidate with the shared Black-Scholes
     calculator (``tb_utils.greeks.calculate_greeks``).
  5. Selects the contract whose absolute delta is closest to a target
     (``TARGET_DELTA``, default 0.45).
  6. Derives a premium-based target/stop (``PREMIUM_TARGET_RATIO`` = 1.30,
     ``PREMIUM_STOP_RATIO`` = 0.80).
"""

# stdlib
import datetime as dt
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

# third-party
from sqlalchemy import text
from sqlalchemy.orm import Session

# internal
from tb_utils.greeks import calculate_greeks
from tb_utils.redis.sync_market_store import SyncMarketStore

logger = logging.getLogger("tb_utils.options.resolver")

# ── Tunables ──────────────────────────────────────────────────────────────────

MIN_DTE_DAYS: int = 2  # skip 0-1 DTE contracts (pure gamma/theta noise)
MIN_OPEN_INTEREST: int = 500  # liquidity floor
MIN_VOLUME: int = 100  # liquidity floor
TARGET_DELTA: float = 0.45  # slightly-OTM-of-ATM directional exposure
DELTA_TOLERANCE_WARN: float = 0.15  # log if best available delta is this far from target
PREMIUM_TARGET_RATIO: float = 1.30  # +30% premium take-profit (long-option economics)
PREMIUM_STOP_RATIO: float = 0.80  # -20% premium stop-loss (cut theta-bleed losers fast)
MIN_INTRADAY_OPTION_TARGET_MOVE_PCT: float = (
    2.0  # minimum 2.0% Target 1 vs Entry move to offer intraday option trade
)

OPTION_CONTRACTS_QUERY = text("""
WITH latest_snapshot AS (
    SELECT symbol, MAX(ts) AS max_ts
    FROM option_chain
    WHERE symbol = :symbol
    GROUP BY symbol
)
SELECT
    oc.expiry_date,
    oc.strike_price::float AS strike_price,
    oc.option_type,
    oc.ltp::float AS ltp,
    oc.implied_vol::float AS implied_vol,
    oc.open_interest,
    oc.volume,
    oc.underlying_value::float AS underlying_value,
    (oc.expiry_date - CURRENT_DATE) AS dte
FROM option_chain oc
JOIN latest_snapshot ls ON oc.symbol = ls.symbol AND oc.ts = ls.max_ts
WHERE oc.option_type = :option_type
  AND oc.expiry_date >= CURRENT_DATE
  AND oc.ltp > 0
  AND oc.implied_vol > 0
  AND oc.underlying_value > 0
ORDER BY oc.expiry_date ASC, oc.strike_price ASC
""")

_default_redis_store: Optional[SyncMarketStore] = None


def get_default_redis_store() -> Optional[SyncMarketStore]:
    """Retrieve singleton SyncMarketStore for option chain caching."""
    global _default_redis_store
    if _default_redis_store is None:
        try:
            import redis

            redis_url = (
                os.getenv("REDIS_URL")
                or os.getenv("CELERY_BROKER_URL")
                or "redis://localhost:6379/0"
            )
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            _default_redis_store = SyncMarketStore(client)
        except Exception as exc:
            logger.warning(
                "[get_default_redis_store] Failed to initialize default Redis client: %s", exc
            )
            return None
    return _default_redis_store


@dataclass
class _OptionCandidate:
    expiry_date: dt.date
    strike_price: float
    option_type: str
    ltp: float
    implied_vol: float
    open_interest: int
    volume: int
    underlying_value: float
    dte: int


@dataclass
class ResolvedContract:
    """A concrete, liquid option contract selected for a directional signal."""

    symbol: str
    expiry_date: dt.date
    strike_price: float
    option_type: str  # "CE" or "PE"
    entry_premium: float  # live LTP -- the actual entry price for the trade
    target_premium: float
    stop_premium: float
    delta: float
    gamma: Optional[float]
    theta: Optional[float]
    vega: Optional[float]
    implied_vol: float
    open_interest: int
    volume: int
    underlying_value: float


def _extract_candidates_from_redis(
    records: list[dict[str, Any]], option_type: str
) -> list[_OptionCandidate]:
    today = dt.date.today()
    candidates: list[_OptionCandidate] = []
    for r in records:
        if r.get("option_type") != option_type:
            continue
        exp_raw = r.get("expiry_date")
        if not exp_raw:
            continue
        if isinstance(exp_raw, dt.date):
            exp_date = exp_raw
        elif isinstance(exp_raw, str):
            try:
                exp_date = dt.date.fromisoformat(exp_raw)
            except ValueError:
                try:
                    exp_date = dt.datetime.strptime(exp_raw, "%d-%b-%Y").date()
                except ValueError:
                    continue
        else:
            continue

        dte = (exp_date - today).days
        ltp = float(r.get("ltp") or 0)
        iv = float(r.get("implied_vol") or 0)
        spot = float(r.get("underlying_value") or 0)
        if ltp <= 0 or iv <= 0 or spot <= 0:
            continue
        candidates.append(
            _OptionCandidate(
                expiry_date=exp_date,
                strike_price=float(r.get("strike_price") or 0),
                option_type=option_type,
                ltp=ltp,
                implied_vol=iv,
                open_interest=int(r.get("open_interest") or 0),
                volume=int(r.get("volume") or 0),
                underlying_value=spot,
                dte=dte,
            )
        )
    return candidates


def _extract_candidates_from_db(rows: list, option_type: str) -> list[_OptionCandidate]:
    candidates: list[_OptionCandidate] = []
    for r in rows:
        dte = int(r.dte) if r.dte is not None else (r.expiry_date - dt.date.today()).days
        candidates.append(
            _OptionCandidate(
                expiry_date=r.expiry_date,
                strike_price=float(r.strike_price),
                option_type=option_type,
                ltp=float(r.ltp),
                implied_vol=float(r.implied_vol),
                open_interest=int(r.open_interest or 0),
                volume=int(r.volume or 0),
                underlying_value=float(r.underlying_value),
                dte=dte,
            )
        )
    return candidates


def get_symbol_option_chain_aliases(symbol: str) -> list[str]:
    """Return prioritized lookup symbols for option chain searches.

    Handles standard variations for indices (e.g. NIFTY50 vs NIFTY, BANKNIFTY vs NIFTY BANK).
    """
    if not symbol:
        return []
    s = str(symbol).strip().upper()
    if s in ("NIFTY", "NIFTY50", "NIFTY 50", "NSE:NIFTY50"):
        return ["NIFTY50", "NIFTY", "NIFTY 50"]
    if s in ("BANKNIFTY", "NIFTYBANK", "NIFTY BANK", "BANK NIFTY"):
        return ["BANKNIFTY", "NIFTY BANK", "NIFTYBANK", "BANK NIFTY"]
    if s in ("FINNIFTY", "NIFTY FIN SERVICE", "NIFTY FINANCIAL SERVICES", "FIN NIFTY"):
        return ["FINNIFTY", "NIFTY FIN SERVICE", "FIN NIFTY"]
    if s in ("MIDCPNIFTY", "NIFTY MIDCAP SELECT", "MIDCAP NIFTY"):
        return ["MIDCPNIFTY", "NIFTY MIDCAP SELECT", "MIDCAP NIFTY"]
    return [s]


def resolve_option_contract(
    db: Session,
    symbol: str,
    action: str,
    target_delta: float = TARGET_DELTA,
    redis_store: Optional[SyncMarketStore] = None,
    underlying_entry_price: Optional[float] = None,
    underlying_target_price: Optional[float] = None,
    min_target_move_pct: float = MIN_INTRADAY_OPTION_TARGET_MOVE_PCT,
) -> Optional[ResolvedContract]:
    """Resolve a concrete, liquid option contract for a directional (BUY/SELL) signal.

    Args:
        db: Active SQLAlchemy session.
        symbol: Underlying symbol (e.g. "TATAMOTORS", "NIFTY").
        action: "BUY" for a bullish view (resolves a CE) or "SELL" for a
            bearish view (resolves a PE). Note the resulting trade is always a
            *long premium* position (buy the CE or buy the PE) -- this
            resolver does not support option-writing strategies.
        target_delta: Desired absolute delta of the selected contract.
        redis_store: Optional SyncMarketStore instance. If None, checks default store.
        underlying_entry_price: Optional entry price of the underlying signal.
        underlying_target_price: Optional target 1 price of the underlying signal.
        min_target_move_pct: Minimum required percentage difference between Target 1
            and Entry (default: 2.0%) to offer an intraday option trade.

    Returns:
        ResolvedContract, or None if no liquid contract could be resolved or if
        the underlying move is insufficient (< 2.0%) for options.
    """
    # Guard: Require >= 2.0% expected move in underlying before offering option trade
    if (
        underlying_entry_price is not None
        and underlying_target_price is not None
        and underlying_entry_price > 0
    ):
        target_move_pct = (
            abs(underlying_target_price - underlying_entry_price) / underlying_entry_price * 100.0
        )
        if target_move_pct < min_target_move_pct:
            logger.info(
                "[resolve_option_contract] Skipping %s for %s: Target move (%.2f%%) < %.1f%% "
                "minimum threshold (option premium does not move sufficiently).",
                action,
                symbol,
                target_move_pct,
                min_target_move_pct,
            )
            return None

    option_type = "CE" if action.upper() == "BUY" else "PE"
    store = redis_store if redis_store is not None else get_default_redis_store()
    candidates: list[_OptionCandidate] = []
    symbol_candidates = get_symbol_option_chain_aliases(symbol)

    # 1. Try Redis cache first (fresh 3-min snapshots cached with 6h TTL)
    if store is not None:
        for sym in symbol_candidates:
            try:
                cached = store.get_cached_option_chain(sym)
                if cached:
                    candidates = _extract_candidates_from_redis(cached, option_type)
                    if candidates:
                        break
            except Exception as exc:
                logger.warning("[resolve_option_contract] Redis read failed for %s: %s", sym, exc)

    # 2. If not in Redis, try Postgres DB
    if not candidates:
        for sym in symbol_candidates:
            rows = db.execute(
                OPTION_CONTRACTS_QUERY, {"symbol": sym, "option_type": option_type}
            ).fetchall()
            if rows:
                candidates = _extract_candidates_from_db(rows, option_type)
                if candidates:
                    break

    if not candidates:
        logger.info(
            "[resolve_option_contract] %s %s: no option_chain data available in Redis or DB.",
            symbol,
            option_type,
        )
        return None

    # Restrict to the nearest expiry that clears the minimum DTE floor.
    eligible_expiries = sorted({c.expiry_date for c in candidates if c.dte >= MIN_DTE_DAYS})
    if not eligible_expiries:
        logger.info(
            "[resolve_option_contract] %s %s: no expiry with DTE >= %d.",
            symbol,
            option_type,
            MIN_DTE_DAYS,
        )
        return None
    nearest_expiry = eligible_expiries[0]

    filtered_candidates: list[tuple[_OptionCandidate, dict]] = []
    for c in candidates:
        if c.expiry_date != nearest_expiry:
            continue
        if c.open_interest < MIN_OPEN_INTEREST or c.volume < MIN_VOLUME:
            continue
        tte_days = float(c.dte) if c.dte > 0 else 0.5
        greeks = calculate_greeks(
            spot=c.underlying_value,
            strike=c.strike_price,
            tte_days=tte_days,
            iv_pct=c.implied_vol,
            option_type=option_type,
        )
        if greeks["delta"] is None:
            continue
        filtered_candidates.append((c, greeks))

    if not filtered_candidates:
        logger.info(
            "[resolve_option_contract] %s %s: no liquid strike (OI>=%d, Vol>=%d) at expiry %s.",
            symbol,
            option_type,
            MIN_OPEN_INTEREST,
            MIN_VOLUME,
            nearest_expiry,
        )
        return None

    best_candidate, best_greeks = min(
        filtered_candidates, key=lambda pair: abs(abs(pair[1]["delta"]) - target_delta)
    )

    delta_gap = abs(abs(best_greeks["delta"]) - target_delta)
    if delta_gap > DELTA_TOLERANCE_WARN:
        logger.info(
            "[resolve_option_contract] %s %s: closest available delta %.2f is %.2f away "
            "from target %.2f -- using best available liquid strike.",
            symbol,
            option_type,
            best_greeks["delta"],
            delta_gap,
            target_delta,
        )

    entry_premium = float(best_candidate.ltp)
    target_premium = round(entry_premium * PREMIUM_TARGET_RATIO, 2)
    stop_premium = round(entry_premium * PREMIUM_STOP_RATIO, 2)

    return ResolvedContract(
        symbol=symbol,
        expiry_date=best_candidate.expiry_date,
        strike_price=float(best_candidate.strike_price),
        option_type=option_type,
        entry_premium=entry_premium,
        target_premium=target_premium,
        stop_premium=stop_premium,
        delta=best_greeks["delta"],
        gamma=best_greeks["gamma"],
        theta=best_greeks["theta"],
        vega=best_greeks["vega"],
        implied_vol=float(best_candidate.implied_vol),
        open_interest=int(best_candidate.open_interest),
        volume=int(best_candidate.volume),
        underlying_value=float(best_candidate.underlying_value),
    )
