"""Builds one defined-risk vertical spread from a fresh option chain. Pure: no I/O of any kind.

The engine cannot be handed a chain that predates the decision: its input is a :class:`FreshChain`,
which refuses to exist unless the chain was stored at or after the moment the caller asked for it.
Fetching that chain is somebody else's job; this module only turns it into a trade or a reason.

Pipeline (spec §2-§4)
---------------------
expiry (nearest at least ``min_dte`` days out) → ATM straddle % → regime → structure
→ legs that clear the liquidity rules → pairs inside the delta bands → payoff, POP, reward:risk
→ candidate rules → best one, or a :class:`Skip` that says why nothing qualified.

====================  ==============  =====================================================
signal / regime       structure       legs
====================  ==============  =====================================================
BUY,  low/transition  bull call       buy call, sell a higher call (debit)
SELL, low/transition  bear put        buy put, sell a lower put (debit)
BUY,  high            bull put        sell put, buy a lower put (credit)
SELL, high            bear call       sell call, buy a higher call (credit)
====================  ==============  =====================================================

Money is rupees for the whole position; prices and strikes are per share. A debit is a negative
``net_premium``. The bought leg is always listed first: it is sent first, which is what earns the
exchange's margin relief on the sold leg.
"""

import datetime as dt
import math
from dataclasses import dataclass
from typing import Optional

from tb_utils.greeks import calculate_greeks
from tb_utils.options.ideas import ChainData, Quote, Skip
from tb_utils.options.payoff import Leg, breakevens, max_profit_loss, net_premium
from tb_utils.options.probability import analyze_probability
from tb_utils.options.spread_policy import HIGH_VOL, SpreadPolicy, classify_regime
from tb_utils.options.spread_rules import (
    Rejection,
    check_credit,
    check_leg_liquidity,
    check_pop,
    check_reward_risk,
)
from tb_utils.time import IST

BUY = "BUY"
SELL = "SELL"
DEBIT = "DEBIT"
CREDIT = "CREDIT"
EXPIRY_CLOSE = dt.time(15, 30)
MIN_DAYS = 0.01  # greeks need a positive time to expiry


class StaleChainError(ValueError):
    """A chain older than the request that was meant to refresh it."""


@dataclass(frozen=True)
class FreshChain:
    """A chain proven to have been stored at or after ``requested_at``.

    Constructing one is the freshness check, so a cached or hours-old snapshot cannot reach the
    engine by accident: it raises :class:`StaleChainError` instead.
    """

    chain: ChainData
    requested_at: dt.datetime

    def __post_init__(self) -> None:
        if self.chain.ts < self.requested_at:
            raise StaleChainError(
                f"chain for {self.chain.symbol} was stored at {self.chain.ts.isoformat()}, "
                f"before it was requested at {self.requested_at.isoformat()}"
            )


@dataclass(frozen=True)
class SpreadLeg:  # pylint: disable=too-many-instance-attributes
    action: str
    option_type: str
    strike: float
    lots: int
    premium: float  # per share: the ask for a bought leg, the bid for a sold one
    premium_basis: str  # ask | bid
    iv: float
    delta: float
    bid: float
    ask: float
    open_interest: int
    volume: int
    tick: float


@dataclass(frozen=True)
class Spread:  # pylint: disable=too-many-instance-attributes
    structure: str  # bull_call_spread | bear_put_spread | bull_put_spread | bear_call_spread
    family: str  # DEBIT | CREDIT
    regime: str
    underlying: str
    expiry: dt.date
    dte: int
    lot_size: int
    legs: tuple[SpreadLeg, ...]  # bought leg first
    width: float  # strike distance, per share
    net_premium: float  # rupees; negative is a debit
    max_profit: float
    max_loss: float  # positive magnitude
    reward_risk: float
    pop: float
    breakevens: tuple[float, ...]
    straddle_pct: float
    atm_iv: float


@dataclass(frozen=True)
class SpreadResult:
    """The outcome for one signal: a spread, or a Skip that explains why not. Never silent."""

    spread: Optional[Spread] = None
    skip: Optional[Skip] = None
    rejections: tuple[Rejection, ...] = ()
    alternatives: tuple[Spread, ...] = ()  # every candidate that passed, best first
    regime: Optional[str] = None
    straddle_pct: Optional[float] = None


@dataclass(frozen=True)
class _Plan:
    structure: str
    family: str
    option_type: str
    bought_band: tuple[float, float]
    sold_band: tuple[float, float]
    sold_above_bought: bool


@dataclass(frozen=True)
class _Context:  # pylint: disable=too-many-instance-attributes
    """What every candidate of one signal shares."""

    policy: SpreadPolicy
    plan: _Plan
    symbol: str
    spot: float
    lot_size: int
    expiry: dt.date
    dte: int
    days: float
    atm_iv: float
    straddle_pct: float
    regime: str
    quotes: tuple[Quote, ...]  # the chosen expiry only


def _plan(action: str, regime: str, policy: SpreadPolicy) -> _Plan:
    bullish = action == BUY
    if regime == HIGH_VOL:  # premium is rich: sell it
        kind = "PE" if bullish else "CE"
        return _Plan(
            "bull_put_spread" if bullish else "bear_call_spread", CREDIT, kind,
            policy.credit_long_delta, policy.credit_short_delta, sold_above_bought=bullish,
        )  # fmt: skip
    kind = "CE" if bullish else "PE"
    return _Plan(
        "bull_call_spread" if bullish else "bear_put_spread", DEBIT, kind,
        policy.debit_long_delta, policy.debit_short_delta, sold_above_bought=bullish,
    )  # fmt: skip


def _skip(code: str, message: str, rejections: tuple[Rejection, ...] = ()) -> SpreadResult:
    return SpreadResult(skip=Skip(code, message), rejections=rejections)


def _choose_expiry(quotes: list[Quote], today: dt.date, min_dte: int) -> Optional[dt.date]:
    for expiry in sorted({q.expiry for q in quotes}):
        if (expiry - today).days >= min_dte:
            return expiry
    return None


def _price(quote: Quote) -> Optional[float]:
    if quote.ltp and quote.ltp > 0:
        return quote.ltp
    if quote.bid and quote.ask and quote.bid > 0 and quote.ask > 0:
        return (quote.bid + quote.ask) / 2.0
    return None


def _atm_straddle(quotes: list[Quote], spot: float) -> Optional[tuple[float, float]]:
    """``(straddle % of spot, ATM implied vol)`` from the strike nearest spot with both sides."""
    by_strike: dict[float, dict[str, Quote]] = {}
    for quote in quotes:
        by_strike.setdefault(quote.strike, {})[quote.option_type] = quote
    both = [(k, sides) for k, sides in by_strike.items() if "CE" in sides and "PE" in sides]
    if not both:
        return None
    _, sides = min(both, key=lambda item: abs(item[0] - spot))
    call, put = _price(sides["CE"]), _price(sides["PE"])
    ivs = [q.iv for q in (sides["CE"], sides["PE"]) if q.iv and q.iv > 0]
    if call is None or put is None or not ivs:
        return None
    return (call + put) / spot * 100.0, sum(ivs) / len(ivs)


def _precheck(chain: ChainData, action: str) -> Optional[SpreadResult]:
    """The Skip for an input that cannot be traded at all, or None."""
    if action not in (BUY, SELL):
        return _skip("BAD_ACTION", f"action must be BUY or SELL, got {action!r}")
    if chain.spot <= 0 or not chain.quotes:
        return _skip("NO_CHAIN", "the chain has no spot price or no quotes")
    if chain.lot_size is None or chain.lot_size <= 0:
        return _skip("NO_LOT_SIZE", f"the lot size for {chain.symbol} is not set")
    return None


def _context(
    chain: ChainData, action: str, now: dt.datetime, policy: SpreadPolicy
) -> tuple[Optional[_Context], Optional[SpreadResult]]:
    """Everything shared by the candidates, or the early Skip that ends the attempt."""
    early = _precheck(chain, action)
    if early is not None:
        return None, early
    today = now.astimezone(IST).date()
    expiry = _choose_expiry(list(chain.quotes), today, policy.min_dte)
    if expiry is None:
        return None, _skip("NO_EXPIRY", f"no listed expiry is at least {policy.min_dte} days away")
    quotes = tuple(q for q in chain.quotes if q.expiry == expiry)
    straddle = _atm_straddle(list(quotes), chain.spot)
    if straddle is None:
        return None, _skip("NO_STRADDLE", "the ATM straddle cannot be priced (side, price or IV)")
    straddle_pct, atm_iv = straddle
    regime = classify_regime(straddle_pct, policy)
    close = dt.datetime.combine(expiry, EXPIRY_CLOSE, tzinfo=IST)
    days = max((close - now).total_seconds() / 86400.0, MIN_DAYS)
    return (
        _Context(
            policy, _plan(action, regime, policy), chain.symbol, chain.spot, chain.lot_size,
            expiry, (expiry - today).days, days, atm_iv, straddle_pct, regime, quotes,
        ),
        None,
    )  # fmt: skip


def _liquid_legs(ctx: _Context) -> tuple[list[tuple[Quote, float]], list[Rejection]]:
    """The legs that clear the liquidity rules, each with its absolute delta; plus what failed."""
    liquid: list[tuple[Quote, float]] = []
    rejected: list[Rejection] = []
    for quote in ctx.quotes:
        if quote.option_type != ctx.plan.option_type:
            continue
        failed = check_leg_liquidity(quote, ctx.policy)
        if failed:
            rejected.append(failed)
            continue
        delta = calculate_greeks(
            ctx.spot, quote.strike, tte_days=ctx.days, iv_pct=quote.iv,
            option_type=quote.option_type,
        ).get("delta")  # fmt: skip
        if delta is None:
            subject = f"{quote.option_type} {quote.strike:g}"
            rejected.append(Rejection("NO_GREEKS", "delta could not be computed", subject))
            continue
        liquid.append((quote, abs(float(delta))))
    return liquid, rejected


def _in_band(value: float, band: tuple[float, float]) -> bool:
    return band[0] <= value <= band[1]


def _pairs(ctx: _Context, liquid: list[tuple[Quote, float]]) -> list[tuple]:
    """Every (bought, sold) pair with deltas in the plan's bands and correctly ordered strikes."""
    plan = ctx.plan
    return [
        (bought, sold)
        for bought in liquid if _in_band(bought[1], plan.bought_band)
        for sold in liquid if _in_band(sold[1], plan.sold_band)
        if sold[0].strike != bought[0].strike
        and (sold[0].strike > bought[0].strike) == plan.sold_above_bought
    ]  # fmt: skip


def _leg(action: str, quote: Quote, delta: float) -> SpreadLeg:
    buying = action == BUY
    return SpreadLeg(
        action, quote.option_type, quote.strike, 1,
        quote.ask if buying else quote.bid, "ask" if buying else "bid",
        quote.iv, round(delta, 4), quote.bid, quote.ask, quote.open_interest, quote.volume,
        quote.tick,
    )  # fmt: skip


def _candidate_failure(
    ctx: _Context, reward_risk: float, pop: float, credit: float, width: float
) -> Optional[Rejection]:
    """The first candidate rule this pair breaks, or None."""
    if ctx.plan.family == DEBIT:
        failed = check_reward_risk(reward_risk, ctx.regime, ctx.policy)
    else:
        failed = check_credit(credit, width, ctx.policy)
    return failed or check_pop(pop, ctx.plan.family, ctx.policy)


def _evaluate(
    ctx: _Context, bought: tuple[Quote, float], sold: tuple[Quote, float]
) -> tuple[Optional[Spread], Optional[Rejection]]:
    """Price one pair and apply the candidate rules: ``(spread, None)`` or ``(None, reason)``."""
    long_leg, short_leg = _leg(BUY, *bought), _leg(SELL, *sold)
    subject = (
        f"BUY {long_leg.option_type} {long_leg.strike:g} / "
        f"SELL {short_leg.option_type} {short_leg.strike:g}"
    )
    payoff_legs = [
        Leg(l.action, l.option_type, l.strike, l.premium, 1, ctx.lot_size, ctx.expiry, l.iv)
        for l in (long_leg, short_leg)  # noqa: E741 - short alias in a one-line comprehension
    ]  # fmt: skip
    extremes = max_profit_loss(payoff_legs)
    max_profit, max_loss = extremes.max_profit.value, -extremes.max_loss.value
    if not (0 < max_profit < math.inf and 0 < max_loss < math.inf):
        return None, Rejection("NO_EDGE", "no finite, positive profit and risk", subject)

    net = net_premium(payoff_legs)
    width = abs(short_leg.strike - long_leg.strike)
    reward_risk = max_profit / max_loss
    pop = analyze_probability(payoff_legs, ctx.spot, ctx.atm_iv, ctx.days).pop
    failed = _candidate_failure(ctx, reward_risk, pop, net / ctx.lot_size, width)
    if failed:
        return None, Rejection(failed.code, failed.detail, subject)

    return (
        Spread(
            structure=ctx.plan.structure, family=ctx.plan.family, regime=ctx.regime,
            underlying=ctx.symbol, expiry=ctx.expiry, dte=ctx.dte, lot_size=ctx.lot_size,
            legs=(long_leg, short_leg), width=width, net_premium=round(net, 2),
            max_profit=round(max_profit, 2), max_loss=round(max_loss, 2),
            reward_risk=round(reward_risk, 2), pop=round(pop, 4),
            breakevens=tuple(round(b, 2) for b in breakevens(payoff_legs)),
            straddle_pct=round(ctx.straddle_pct, 3), atm_iv=round(ctx.atm_iv, 2),
        ),
        None,
    )  # fmt: skip


def _rank(family: str):
    """Debit: least rupee risk first. Credit: richest credit for the width first."""
    if family == DEBIT:
        return lambda s: (s.max_loss, -s.pop)
    return lambda s: (-s.net_premium / (s.width * s.lot_size), s.max_loss)


def build_vertical_spread(
    fresh: FreshChain,
    action: str,
    now: dt.datetime,
    policy: SpreadPolicy = SpreadPolicy(),  # noqa: B008 - frozen, so safe as a default
) -> SpreadResult:
    """The best vertical spread for a BUY or SELL signal on this chain, or why there is none.

    No target price is needed: strikes come from delta bands, so a signal that carries only an
    entry and a stop (such as STC) is enough.
    """
    ctx, early = _context(fresh.chain, (action or "").upper(), now, policy)
    if early is not None:
        return early
    liquid, rejections = _liquid_legs(ctx)
    seen = {"regime": ctx.regime, "straddle_pct": round(ctx.straddle_pct, 3)}
    if len(liquid) < 2:
        message = f"only {len(liquid)} {ctx.plan.option_type} strike(s) clear the liquidity rules"
        skip = Skip("NO_LIQUID_STRIKES", message)
        return SpreadResult(skip=skip, rejections=tuple(rejections), **seen)

    pairs = _pairs(ctx, liquid)
    if not pairs:
        bands = f"{ctx.plan.bought_band} / {ctx.plan.sold_band}"
        message = f"no strike pair fits the delta bands {bands}"
        skip = Skip("NO_CANDIDATE", message)
        return SpreadResult(skip=skip, rejections=tuple(rejections), **seen)

    passed: list[Spread] = []
    for bought, sold in pairs:
        spread, rejected = _evaluate(ctx, bought, sold)
        if spread is not None:
            passed.append(spread)
        else:
            rejections.append(rejected)
    if not passed:
        message = f"{len(pairs)} candidate(s) failed the payoff rules"
        skip = Skip("ALL_REJECTED", message)
        return SpreadResult(skip=skip, rejections=tuple(rejections), **seen)

    ranked = tuple(sorted(passed, key=_rank(ctx.plan.family)))
    return SpreadResult(spread=ranked[0], rejections=tuple(rejections), alternatives=ranked, **seen)


__all__ = [
    "FreshChain",
    "Spread",
    "SpreadLeg",
    "SpreadResult",
    "StaleChainError",
    "build_vertical_spread",
]
