"""Multi-leg option strategy builder for the research agent's directional signals.

Builds a defined-risk vertical spread (Bull Call, Bear Put, Bull Put or Bear Call) from a BUY or
SELL signal on an F&O underlying. The strikes and every rule come from the same engine that builds
the STC spreads (:mod:`tb_utils.options.spread_engine`), so the research agent, the Option Builder
and the auto-trader follow one rule set:

  * strikes chosen by **delta band** (debit: long 0.35 to 0.45, short 0.15 to 0.20; credit: short
    0.30 to 0.40, long 0.15 to 0.20), not by "at the money" and "near the target";
  * every leg individually liquid (open interest, volume, bid-ask), reward:risk of at least 2.5 for
    a debit spread, a credit of at least a quarter of the width, a minimum probability of profit;
  * debit in low volatility and credit when premium is rich, decided from the ATM straddle;
  * bought legs first (execution order 1), which earns the exchange's spread margin relief.

This replaced an older builder (30 Oct 2026) that bought the at-the-money strike, sold near the
signal's target and accepted a reward:risk of 1.2 on an open interest of 300 with no volume,
bid-ask or probability check, which put its debit spreads near 1:1 and made a target price
mandatory. A signal needs only an entry and a stop now; the target is carried for the record.

The chain is the latest stored ``option_chain`` snapshot (bid, ask, volume and all), refused when
it is older than :data:`MAX_CHAIN_AGE`. Prices are per share (a one-lot position's rupees divided
by the lot size), as the old builder reported them.
"""
# pylint: disable=too-many-instance-attributes

# stdlib
import datetime as dt
import logging
from dataclasses import dataclass, field, replace
from typing import Optional

# third-party
from sqlalchemy import func
from sqlalchemy.orm import Session

# internal
from tb_utils.models.historical_data import OptionChain
from tb_utils.models.instrument import Instrument
from tb_utils.options.ideas import ChainData, Quote
from tb_utils.options.margin import STOCK, estimate_margin, sigma_from_iv
from tb_utils.options.payoff import Leg
from tb_utils.options.spread_engine import FreshChain, Spread, SpreadLeg, build_vertical_spread
from tb_utils.options.spread_policy import SpreadPolicy
from tb_utils.redis.sync_market_store import SyncMarketStore

logger = logging.getLogger("tb_utils.options.strategy_builder")

# ── Tunables ──────────────────────────────────────────────────────────────────

MIN_POSITIONAL_DTE: int = 4  # the spec's rule: closer than this, use the next month's contracts
MAX_CHAIN_AGE: dt.timedelta = dt.timedelta(hours=30)  # a stored chain older than this is not used
# Kept for callers that import it (the basket analyzer's per-leg warning). The builder itself uses
# SpreadPolicy, whose open interest floor is 5,000.
MIN_SPREAD_OPEN_INTEREST: int = 300
DEFAULT_LOT_SIZE: int = 1


@dataclass
class BuiltOptionLeg:
    """Concrete leg specification for execution and persistence."""

    execution_order: int  # 1 = BUY hedge first, then the SELL
    action: str  # BUY or SELL
    option_type: str  # CE or PE
    strike_price: float
    symbol: str  # e.g. "ICICIBANK 29OCT 1360 CE"
    entry_premium: float
    lots: int = 1  # ratio units of the strategy lot_size (a 1x2x1 butterfly is 1, 2, 1)
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

    strategy_type: str  # BULL_CALL_SPREAD, BEAR_PUT_SPREAD, BULL_PUT_SPREAD, BEAR_CALL_SPREAD
    spread_type: str  # DEBIT or CREDIT
    underlying_symbol: str
    expiry_date: dt.date
    dte: int
    lot_size: int
    net_premium: float  # per share: a net debit is positive, a net credit negative
    max_profit: float  # per share
    max_loss: float  # per share
    risk_reward_ratio: float
    breakeven_price: float
    underlying_entry_price: float
    underlying_target_price: float
    underlying_stop_loss: float
    margin_required_approx: float  # rupees, one lot
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


def _price(value: object) -> Optional[float]:
    """A stored price as a float, or None when it is missing or zero (unpriced)."""
    number = float(value) if value is not None else 0.0  # type: ignore[arg-type]
    return number if number > 0 else None


def load_stored_chain(db: Session, symbol: str, lot_size: int) -> Optional[ChainData]:
    """The latest stored ``option_chain`` snapshot for ``symbol`` as :class:`ChainData`, or None."""
    name = symbol.upper()
    latest = db.query(func.max(OptionChain.ts)).filter(OptionChain.symbol == name).scalar()
    if latest is None:
        return None
    rows = db.query(OptionChain).filter(OptionChain.symbol == name, OptionChain.ts == latest).all()
    spots = [float(r.underlying_value) for r in rows if r.underlying_value]
    if not rows or not spots:
        return None
    quotes = [
        Quote(
            expiry=r.expiry_date,
            strike=float(r.strike_price),
            option_type=r.option_type,
            bid=_price(r.bid_price),
            ask=_price(r.ask_price),
            ltp=_price(r.ltp),
            open_interest=int(r.open_interest or 0),
            volume=int(r.volume or 0),
            iv=_price(r.implied_vol),
        )
        for r in rows
    ]
    return ChainData(name, latest, spots[0], lot_size, False, quotes)


def _resolve_lot_size(
    db: Session, symbol: str, lot_size: int, redis_store: Optional[SyncMarketStore]
) -> int:
    """The lot size: the caller's when it is real, else the cache's, else the instrument's."""
    if lot_size > DEFAULT_LOT_SIZE:
        return lot_size
    if redis_store is not None:
        cached = redis_store.get_lot_size(symbol)
        if cached and cached > 0:
            return cached
    if db is not None:
        stored = db.query(Instrument.lot_size).filter(Instrument.symbol == symbol.upper()).scalar()
        if isinstance(stored, (int, float)) and stored > 0:
            if redis_store is not None:
                redis_store.set_lot_size(symbol, int(stored))
            return int(stored)
    return max(lot_size, DEFAULT_LOT_SIZE)


def _estimate_margin(spread: Spread, spot: float, today: dt.date) -> float:
    """Margin for the one-lot spread from the shared SPAN estimate.

    Falls back to the most the spread can lose, which is what a defined-risk spread blocks, if the
    estimate cannot be produced.
    """
    try:
        legs = [
            Leg(
                l.action,
                l.option_type,
                l.strike,
                l.premium,
                l.lots,
                spread.lot_size,
                spread.expiry,
                l.iv,
            )
            for l in spread.legs  # noqa: E741
        ]
        sigma = sigma_from_iv(sum(l.iv for l in spread.legs) / len(spread.legs))  # noqa: E741
        return round(estimate_margin(legs, spot, sigma, STOCK, today).total, 2)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("[strategy_builder] Margin estimate failed, using max loss.")
        return round(spread.max_loss, 2)


def _built_leg(symbol: str, spread: Spread, order: int, leg: SpreadLeg) -> BuiltOptionLeg:
    buying = leg.action == "BUY"
    premium = leg.premium
    return BuiltOptionLeg(
        execution_order=order,
        action=leg.action,
        option_type=leg.option_type,
        strike_price=leg.strike,
        symbol=_build_leg_contract_label(symbol, spread.expiry, leg.strike, leg.option_type),
        entry_premium=premium,
        lots=leg.lots,
        target_premium=round(premium * (1.35 if buying else 0.30), 2),
        stop_loss_premium=round(premium * (0.70 if buying else 1.60), 2),
        delta=leg.delta,
        iv=round(leg.iv, 2),
        open_interest=leg.open_interest,
        volume=leg.volume,
        is_hedge=buying,
    )


def build_vertical_spread_strategy(  # pylint: disable=too-many-arguments
    db: Session,
    symbol: str,
    action: str,  # BUY or SELL
    entry_price: float,
    target_price: float,
    stop_loss: float,
    lot_size: int = DEFAULT_LOT_SIZE,
    redis_store: Optional[SyncMarketStore] = None,
    min_dte: int = MIN_POSITIONAL_DTE,
    now: Optional[dt.datetime] = None,
) -> Optional[BuiltOptionStrategy]:
    """Build a defined-risk vertical spread for a directional signal, or None (reason logged).

    .. warning::
       The price parameters are ``entry_price``/``target_price``/``stop_loss``,
       **not** the ``underlying_*`` names used by
       :func:`tb_utils.options.resolver.resolve_option_contract` or by the
       ``underlying_*`` fields on the :class:`BuiltOptionStrategy` this returns.
       That asymmetry cost months of silently dead spread generation in
       ``tb-research-agent``'s ``research_signals.py``. Keep the names aligned if either
       signature is ever revised.

    Args:
        db: SQLAlchemy database session.
        symbol: Underlying equity symbol (e.g. "ICICIBANK").
        action: Signal action ("BUY" is bullish, "SELL" is bearish).
        entry_price: Underlying entry spot price.
        target_price: Underlying Target 1, kept for the record. Strikes come from delta bands, so
            ``0`` is fine when a signal has no target.
        stop_loss: Underlying stop loss.
        lot_size: Market lot size for the derivative.
        redis_store: Optional market store, used only to cache the lot size.
        min_dte: Calendar days to expiry below which the next month's contracts are used.
        now: The clock, for tests.

    Returns:
        The strategy, or None when the chain is missing or stale or no strike pair passes the rules.
    """
    if entry_price <= 0 or stop_loss <= 0:
        logger.warning("[build_vertical_spread_strategy] Invalid prices for %s.", symbol)
        return None

    now = now or dt.datetime.now(dt.UTC)
    lot_size = _resolve_lot_size(db, symbol, lot_size, redis_store)
    chain = load_stored_chain(db, symbol, lot_size)
    if chain is None:
        logger.info("[build_vertical_spread_strategy] No stored option chain for %s.", symbol)
        return None
    if now - chain.ts > MAX_CHAIN_AGE:
        logger.info(
            "[build_vertical_spread_strategy] The stored chain for %s is %.1f h old; not used.",
            symbol,
            (now - chain.ts).total_seconds() / 3600,
        )
        return None

    policy = replace(SpreadPolicy(), min_dte=min_dte)
    result = build_vertical_spread(FreshChain(chain, requested_at=chain.ts), action, now, policy)
    spread = result.spread
    if spread is None:
        why = f"{result.skip.code}: {result.skip.message}" if result.skip else "no strike pair"
        logger.info(
            "[build_vertical_spread_strategy] No spread for %s %s (%s).", symbol, action, why
        )
        return None

    per_share = float(spread.lot_size)
    return BuiltOptionStrategy(
        strategy_type=spread.structure.upper(),
        spread_type=spread.family,
        underlying_symbol=symbol,
        expiry_date=spread.expiry,
        dte=spread.dte,
        lot_size=spread.lot_size,
        net_premium=round(-spread.net_premium / per_share, 2),
        max_profit=round(spread.max_profit / per_share, 2),
        max_loss=round(spread.max_loss / per_share, 2),
        risk_reward_ratio=round(spread.reward_risk, 2),
        breakeven_price=round(spread.breakevens[0], 2),
        underlying_entry_price=entry_price,
        underlying_target_price=target_price,
        underlying_stop_loss=stop_loss,
        margin_required_approx=_estimate_margin(spread, chain.spot, now.date()),
        legs=[_built_leg(symbol, spread, i, leg) for i, leg in enumerate(spread.legs, start=1)],
    )
