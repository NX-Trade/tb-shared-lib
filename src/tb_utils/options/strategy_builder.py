"""Multi-Leg Option Strategy Builder for Positional / Directional Setups.

Constructs institutional-grade multi-leg option strategies (Bull Call Spread,
Bear Put Spread) from directional signals (e.g. LTC Positional signals).

Key Rules:
  1. Strict Execution Ordering:
     - Leg 1: BUY / Long Hedge Leg (execution_order = 1, is_hedge = True)
     - Leg 2: SELL / Short Leg (execution_order = 2, is_hedge = False)
     Deploying Leg 1 first unlocks the 75-80% exchange spread margin discount
     in Indian broker RMS and avoids naked short margin rejections.
  2. Expiry Selection & DTE Roll Rule:
     - Prefers monthly contracts with DTE > 6 days to avoid expiry week
       gamma crush and physical delivery margin escalation on the NSE.
  3. Dynamic Strike Selection:
     - Bull Call Spread:
         Leg 1 (BUY): ATM Strike (Delta ~ 0.50)
         Leg 2 (SELL): OTM Strike at/near Target 1 (Delta ~ 0.25 - 0.30)
     - Bear Put Spread:
         Leg 1 (BUY): ATM Strike (Delta ~ -0.50)
         Leg 2 (SELL): OTM Strike at/near Target 1 (Delta ~ -0.25 to -0.30)
"""
# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-return-statements,too-many-branches,too-many-statements

# stdlib
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Optional

# third-party
from sqlalchemy.orm import Session

# internal
from tb_utils.greeks import calculate_greeks
from tb_utils.options.resolver import (
    OPTION_CONTRACTS_QUERY,
    _extract_candidates_from_db,
    _extract_candidates_from_redis,
    _OptionCandidate,
    get_default_redis_store,
)
from tb_utils.redis.sync_market_store import SyncMarketStore

logger = logging.getLogger("tb_utils.options.strategy_builder")

# ── Tunables ──────────────────────────────────────────────────────────────────

MIN_POSITIONAL_DTE: int = 6  # Roll if <= 6 calendar days to expiry
MIN_SPREAD_OPEN_INTEREST: int = 300  # Liquidity floor per leg
MIN_RISK_REWARD_RATIO: float = 1.20  # Minimum R:R ratio required to qualify
DEFAULT_LOT_SIZE: int = 1


@dataclass
class BuiltOptionLeg:
    """Concrete leg specification for execution and persistence."""

    execution_order: int  # 1 = BUY hedge first, 2 = SELL second
    action: str  # BUY or SELL
    option_type: str  # CE or PE
    strike_price: float
    symbol: str  # e.g. "ICICIBANK 29OCT 1360 CE"
    entry_premium: float
    target_premium: Optional[float] = None
    stop_loss_premium: Optional[float] = None
    delta: Optional[float] = None
    theta: Optional[float] = None
    iv: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    is_hedge: bool = False


@dataclass
class BuiltOptionStrategy:
    """Complete multi-leg option strategy package."""

    strategy_type: str  # BULL_CALL_SPREAD, BEAR_PUT_SPREAD
    spread_type: str  # DEBIT or CREDIT
    underlying_symbol: str
    expiry_date: dt.date
    dte: int
    lot_size: int
    net_premium: float  # Net Debit (positive) or Net Credit (negative)
    max_profit: float
    max_loss: float
    risk_reward_ratio: float
    breakeven_price: float
    underlying_entry_price: float
    underlying_target_price: float
    underlying_stop_loss: float
    margin_required_approx: float
    legs: list[BuiltOptionLeg] = field(default_factory=list)


def _build_leg_contract_label(
    symbol: str, expiry_date: dt.date, strike_price: float, option_type: str
) -> str:
    """Format standard NSE derivative contract label, e.g. 'TATASTEEL 29OCT 185 CE'."""
    exp_str = expiry_date.strftime("%d%b").upper()
    strike_str = (
        f"{strike_price:.0f}" if float(strike_price).is_integer() else f"{strike_price:.1f}"
    )
    return f"{symbol} {exp_str} {strike_str} {option_type}"


def _get_candidate_chain(
    db: Session,
    symbol: str,
    option_type: str,
    redis_store: Optional[SyncMarketStore] = None,
) -> list[_OptionCandidate]:
    """Fetch option chain candidates from Redis cache first, then PostgreSQL."""
    store = redis_store or get_default_redis_store()
    if store is not None:
        try:
            records = store.get_option_chain_records(symbol)
            if records:
                candidates = _extract_candidates_from_redis(records, option_type)
                if candidates:
                    return candidates
        except Exception:
            logger.exception(
                "[strategy_builder] Redis option chain fetch failed for %s, falling back to DB.",
                symbol,
            )

    rows = db.execute(
        OPTION_CONTRACTS_QUERY, {"symbol": symbol, "option_type": option_type}
    ).fetchall()
    return _extract_candidates_from_db(rows, option_type)


def build_vertical_spread_strategy(
    db: Session,
    symbol: str,
    action: str,  # BUY or SELL
    entry_price: float,
    target_price: float,
    stop_loss: float,
    lot_size: int = DEFAULT_LOT_SIZE,
    redis_store: Optional[SyncMarketStore] = None,
    min_dte: int = MIN_POSITIONAL_DTE,
) -> Optional[BuiltOptionStrategy]:
    """Build a margin-optimized vertical spread strategy for a directional signal.

    Args:
        db: SQLAlchemy database session.
        symbol: Underlying equity symbol (e.g. "ICICIBANK").
        action: Signal action ("BUY" -> Bull Call Spread, "SELL" -> Bear Put Spread).
        entry_price: Underlying entry spot price.
        target_price: Underlying Target 1 price.
        stop_loss: Underlying Stop Loss price.
        lot_size: Market lot size for the derivative.
        redis_store: Optional market store for live cache.
        min_dte: Minimum DTE threshold before rolling to next expiry.

    Returns:
        Optional[BuiltOptionStrategy]: Strategy definition if valid, else None.
    """
    if entry_price <= 0 or target_price <= 0 or stop_loss <= 0:
        logger.warning(
            "[build_vertical_spread_strategy] Invalid prices for %s (entry=%s, target=%s).",
            symbol,
            entry_price,
            target_price,
        )
        return None

    is_bullish = action.upper() == "BUY"
    option_type = "CE" if is_bullish else "PE"
    strategy_type = "BULL_CALL_SPREAD" if is_bullish else "BEAR_PUT_SPREAD"

    candidates = _get_candidate_chain(db, symbol, option_type, redis_store=redis_store)
    if not candidates:
        logger.info(
            "[build_vertical_spread_strategy] No option candidates for %s %s.",
            symbol,
            option_type,
        )
        return None

    # Group candidates by expiry date
    expiries: dict[dt.date, list[_OptionCandidate]] = {}
    for c in candidates:
        expiries.setdefault(c.expiry_date, []).append(c)

    # Sort expiries ascending
    sorted_expiries = sorted(expiries.keys())
    valid_expiry: Optional[dt.date] = None
    target_chain: list[_OptionCandidate] = []

    # Select earliest expiry with DTE > min_dte
    for exp in sorted_expiries:
        chain = expiries[exp]
        dte = chain[0].dte
        if dte >= min_dte:
            valid_expiry = exp
            target_chain = chain
            break

    if valid_expiry is None or not target_chain:
        logger.info(
            "[build_vertical_spread_strategy] No expiry clearing %d DTE for %s.",
            min_dte,
            symbol,
        )
        return None

    dte = target_chain[0].dte

    # Enrich candidates with live Greeks
    enriched: list[tuple[_OptionCandidate, float, float]] = []  # (cand, delta, theta)
    for c in target_chain:
        if c.open_interest < MIN_SPREAD_OPEN_INTEREST:
            continue
        try:
            greeks = calculate_greeks(
                spot=c.underlying_value,
                strike=c.strike_price,
                tte_days=max(float(c.dte), 1.0),
                iv_pct=c.implied_vol,
                option_type=c.option_type,
            )
            delta = greeks.get("delta")
            theta = greeks.get("theta")
            if delta is None or theta is None:
                continue
            enriched.append((c, float(delta), float(theta)))
        except Exception:
            logger.debug(
                "[build_vertical_spread_strategy] Greeks calculation failed for %s strike %s.",
                symbol,
                c.strike_price,
            )

    if len(enriched) < 2:
        logger.info(
            "[build_vertical_spread_strategy] Insufficient liquid strikes for %s %s (found %d).",
            symbol,
            valid_expiry,
            len(enriched),
        )
        return None

    # Strike selection logic
    if is_bullish:
        # Leg 1: ATM Call (strike <= entry_price, highest strike <= entry_price
        # or closest delta to 0.50)
        atm_candidates = [x for x in enriched if x[0].strike_price <= entry_price]
        if not atm_candidates:
            atm_candidates = enriched
        leg1_cand, leg1_delta, leg1_theta = min(atm_candidates, key=lambda x: abs(x[1] - 0.50))

        # Leg 2: OTM Call at or near target_price (must be strike > leg1 strike)
        otm_candidates = [
            x
            for x in enriched
            if x[0].strike_price > leg1_cand.strike_price
            and x[0].strike_price >= target_price * 0.98
        ]
        if not otm_candidates:
            # Fallback to any higher strike with Delta ~ 0.25
            otm_candidates = [x for x in enriched if x[0].strike_price > leg1_cand.strike_price]
        if not otm_candidates:
            return None

        # Pick candidate closest to target_price or delta 0.25
        leg2_cand, leg2_delta, leg2_theta = min(
            otm_candidates, key=lambda x: abs(x[0].strike_price - target_price)
        )

    else:
        # Leg 1: ATM Put (strike >= entry_price, closest delta to -0.50)
        atm_candidates = [x for x in enriched if x[0].strike_price >= entry_price]
        if not atm_candidates:
            atm_candidates = enriched
        leg1_cand, leg1_delta, leg1_theta = min(atm_candidates, key=lambda x: abs(x[1] - (-0.50)))

        # Leg 2: OTM Put at or near target_price (must be strike < leg1 strike)
        otm_candidates = [
            x
            for x in enriched
            if x[0].strike_price < leg1_cand.strike_price
            and x[0].strike_price <= target_price * 1.02
        ]
        if not otm_candidates:
            otm_candidates = [x for x in enriched if x[0].strike_price < leg1_cand.strike_price]
        if not otm_candidates:
            return None

        leg2_cand, leg2_delta, leg2_theta = min(
            otm_candidates, key=lambda x: abs(x[0].strike_price - target_price)
        )

    # Spread Economics
    spread_width = abs(leg2_cand.strike_price - leg1_cand.strike_price)
    net_premium = round(leg1_cand.ltp - leg2_cand.ltp, 2)

    # Sanity checks: debit spread must have positive net debit < spread_width
    if net_premium <= 0 or net_premium >= spread_width:
        logger.info(
            "[build_vertical_spread_strategy] Invalid spread pricing for %s: "
            "net_premium=%.2f, width=%.2f.",
            symbol,
            net_premium,
            spread_width,
        )
        return None

    max_profit = round(spread_width - net_premium, 2)
    max_loss = net_premium
    risk_reward = round(max_profit / max_loss, 2) if max_loss > 0 else 0.0

    if risk_reward < MIN_RISK_REWARD_RATIO:
        logger.info(
            "[build_vertical_spread_strategy] R:R %.2f below threshold %.2f for %s.",
            risk_reward,
            MIN_RISK_REWARD_RATIO,
            symbol,
        )
        return None

    # Breakeven point
    if is_bullish:
        breakeven = round(leg1_cand.strike_price + net_premium, 2)
    else:
        breakeven = round(leg1_cand.strike_price - net_premium, 2)

    # Approximate margin for a hedged debit spread in India:
    approx_margin = round(max(net_premium * lot_size, 25000.0), 2)

    # Construct the two sequenced legs:
    # LEG 1: BUY HEDGE FIRST (unlocks margin benefit)
    # LEG 2: SELL SECOND
    leg1 = BuiltOptionLeg(
        execution_order=1,
        action="BUY",
        option_type=option_type,
        strike_price=leg1_cand.strike_price,
        symbol=_build_leg_contract_label(symbol, valid_expiry, leg1_cand.strike_price, option_type),
        entry_premium=leg1_cand.ltp,
        target_premium=round(leg1_cand.ltp * 1.35, 2),
        stop_loss_premium=round(leg1_cand.ltp * 0.70, 2),
        delta=round(leg1_delta, 4),
        theta=round(leg1_theta, 4),
        iv=round(leg1_cand.implied_vol, 2),
        open_interest=leg1_cand.open_interest,
        volume=leg1_cand.volume,
        is_hedge=True,
    )

    leg2 = BuiltOptionLeg(
        execution_order=2,
        action="SELL",
        option_type=option_type,
        strike_price=leg2_cand.strike_price,
        symbol=_build_leg_contract_label(symbol, valid_expiry, leg2_cand.strike_price, option_type),
        entry_premium=leg2_cand.ltp,
        target_premium=round(leg2_cand.ltp * 0.30, 2),
        stop_loss_premium=round(leg2_cand.ltp * 1.60, 2),
        delta=round(leg2_delta, 4),
        theta=round(leg2_theta, 4),
        iv=round(leg2_cand.implied_vol, 2),
        open_interest=leg2_cand.open_interest,
        volume=leg2_cand.volume,
        is_hedge=False,
    )

    return BuiltOptionStrategy(
        strategy_type=strategy_type,
        spread_type="DEBIT",
        underlying_symbol=symbol,
        expiry_date=valid_expiry,
        dte=dte,
        lot_size=lot_size,
        net_premium=net_premium,
        max_profit=max_profit,
        max_loss=max_loss,
        risk_reward_ratio=risk_reward,
        breakeven_price=breakeven,
        underlying_entry_price=entry_price,
        underlying_target_price=target_price,
        underlying_stop_loss=stop_loss,
        margin_required_approx=approx_margin,
        legs=[leg1, leg2],
    )
