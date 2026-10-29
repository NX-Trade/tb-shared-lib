"""Builds one defined-risk option structure from a fresh option chain. Pure: no I/O of any kind.

The engine cannot be handed a chain that predates the decision: its input is a :class:`FreshChain`,
which refuses to exist unless the chain was stored at or after the moment the caller asked for it.
Fetching that chain is somebody else's job; this module only turns it into a trade or a reason.

Shape
-----
A **pipeline of small stages** over an immutable :class:`Frame`. Each stage takes the frame and
returns either the next frame or a final :class:`SpreadResult` (a Skip that says why), so there is
no tuple-of-optionals to misread and every exit is one line::

    validate → pick expiry → measure volatility → choose structure → screen legs
             → generate candidates → evaluate candidates → rank

What is strategy-specific lives in a :class:`StructureSpec` (see ``spread_structures``), picked by a
*chooser* function. The stages are shared, so a butterfly or condor is a new spec, not a new engine.
:func:`build_vertical_spread` is that engine with the four vertical spreads of the spec (§4).

Money is rupees for the whole position; prices and strikes are per share. A debit is a negative
``net_premium``. Bought legs are always listed first: they are sent first, which is what earns the
exchange's margin relief on the sold legs.
"""

import datetime as dt
import itertools
import math
from dataclasses import dataclass, replace
from typing import Optional

from tb_utils.greeks import calculate_greeks
from tb_utils.options.ideas import Quote, Skip
from tb_utils.options.payoff import Leg, breakevens, max_profit_loss, net_premium
from tb_utils.options.probability import analyze_probability
from tb_utils.options.spread_policy import SpreadPolicy, classify_regime
from tb_utils.options.spread_rules import Rejection, check_leg_liquidity
from tb_utils.options.spread_structures import (
    CandidateFacts,
    StructureChooser,
    StructureSpec,
    choose_vertical,
)
from tb_utils.options.spread_types import (
    BUY,
    SELL,
    FreshChain,
    Spread,
    SpreadLeg,
    SpreadResult,
    StaleChainError,
)
from tb_utils.time import IST

EXPIRY_CLOSE = dt.time(15, 30)
MIN_DAYS = 0.01  # greeks need a positive time to expiry

Scored = tuple[Quote, float]  # a quote and its absolute delta
Candidate = tuple[Scored, ...]  # one scored quote per leg, in the structure's leg order


@dataclass(frozen=True)
class Frame:  # pylint: disable=too-many-instance-attributes
    """Everything the pipeline knows so far. Each stage adds the fields it owns."""

    fresh: FreshChain
    action: str
    now: dt.datetime
    policy: SpreadPolicy
    chooser: StructureChooser
    expiry: Optional[dt.date] = None
    dte: int = 0
    days: float = 0.0  # fractional days to the expiry close
    quotes: tuple[Quote, ...] = ()  # the chosen expiry only
    atm_iv: float = 0.0
    straddle_pct: Optional[float] = None
    regime: Optional[str] = None
    structure: Optional[StructureSpec] = None
    liquid: tuple[Scored, ...] = ()
    candidates: tuple[Candidate, ...] = ()
    passed: tuple[Spread, ...] = ()
    rejections: tuple[Rejection, ...] = ()

    @property
    def chain(self):
        return self.fresh.chain

    def skip(self, code: str, message: str) -> SpreadResult:
        """A final result that carries everything learned so far."""
        return SpreadResult(
            skip=Skip(code, message),
            rejections=self.rejections,
            regime=self.regime,
            straddle_pct=None if self.straddle_pct is None else round(self.straddle_pct, 3),
        )


# ── Stages ───────────────────────────────────────────────────────────────────


def _validate(frame: Frame) -> Frame | SpreadResult:
    chain = frame.chain
    if frame.action not in (BUY, SELL):
        return frame.skip("BAD_ACTION", f"action must be BUY or SELL, got {frame.action!r}")
    if chain.spot <= 0 or not chain.quotes:
        return frame.skip("NO_CHAIN", "the chain has no spot price or no quotes")
    if chain.lot_size is None or chain.lot_size <= 0:
        return frame.skip("NO_LOT_SIZE", f"the lot size for {chain.symbol} is not set")
    return frame


def _pick_expiry(frame: Frame) -> Frame | SpreadResult:
    """The nearest expiry at least ``min_dte`` days out; nearer ones risk physical settlement."""
    today = frame.now.astimezone(IST).date()
    for expiry in sorted({q.expiry for q in frame.chain.quotes}):
        if (expiry - today).days >= frame.policy.min_dte:
            close = dt.datetime.combine(expiry, EXPIRY_CLOSE, tzinfo=IST)
            days = max((close - frame.now).total_seconds() / 86400.0, MIN_DAYS)
            quotes = tuple(q for q in frame.chain.quotes if q.expiry == expiry)
            dte = (expiry - today).days
            return replace(frame, expiry=expiry, dte=dte, days=days, quotes=quotes)
    return frame.skip("NO_EXPIRY", f"no listed expiry is at least {frame.policy.min_dte} days away")


def _price(quote: Quote) -> Optional[float]:
    if quote.ltp and quote.ltp > 0:
        return quote.ltp
    if quote.bid and quote.ask and quote.bid > 0 and quote.ask > 0:
        return (quote.bid + quote.ask) / 2.0
    return None


def _atm_straddle(quotes: tuple[Quote, ...], spot: float) -> Optional[tuple[float, float]]:
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


def _measure_volatility(frame: Frame) -> Frame | SpreadResult:
    straddle = _atm_straddle(frame.quotes, frame.chain.spot)
    if straddle is None:
        return frame.skip("NO_STRADDLE", "the ATM straddle cannot be priced (side, price or IV)")
    straddle_pct, atm_iv = straddle
    regime = classify_regime(straddle_pct, frame.policy)
    return replace(frame, straddle_pct=straddle_pct, atm_iv=atm_iv, regime=regime)


def _choose_structure(frame: Frame) -> Frame | SpreadResult:
    return replace(frame, structure=frame.chooser(frame.action, frame.regime, frame.policy))


def _screen_legs(frame: Frame) -> Frame | SpreadResult:
    """Keep the quotes of the structure's option types that clear the liquidity rules."""
    wanted = {leg.option_type for leg in frame.structure.legs}
    liquid: list[Scored] = []
    rejected = list(frame.rejections)
    for quote in frame.quotes:
        if quote.option_type not in wanted:
            continue
        failed = check_leg_liquidity(quote, frame.policy)
        if failed:
            rejected.append(failed)
            continue
        greeks = calculate_greeks(
            frame.chain.spot, quote.strike, tte_days=frame.days, iv_pct=quote.iv,
            option_type=quote.option_type,
        )  # fmt: skip
        delta = greeks.get("delta")
        if delta is None:
            subject = f"{quote.option_type} {quote.strike:g}"
            rejected.append(Rejection("NO_GREEKS", "delta could not be computed", subject))
            continue
        liquid.append((quote, abs(float(delta))))
    screened = replace(frame, liquid=tuple(liquid), rejections=tuple(rejected))
    if len(liquid) < len(frame.structure.legs):
        return screened.skip(
            "NO_LIQUID_STRIKES", f"only {len(liquid)} strike(s) clear the liquidity rules"
        )
    return screened


def _generate(frame: Frame) -> Frame | SpreadResult:
    """Every combination of one liquid quote per leg whose deltas and strikes fit the structure."""
    spec = frame.structure
    per_leg = [
        [s for s in frame.liquid if s[0].option_type == leg.option_type
         and leg.delta_band[0] <= s[1] <= leg.delta_band[1]]
        for leg in spec.legs
    ]  # fmt: skip
    candidates = tuple(
        combo
        for combo in itertools.product(*per_leg)
        if len({(c[0].option_type, c[0].strike) for c in combo}) == len(combo)
        and spec.strike_order([c[0].strike for c in combo])
    )
    generated = replace(frame, candidates=candidates)
    if not candidates:
        bands = " / ".join(str(leg.delta_band) for leg in spec.legs)
        return generated.skip("NO_CANDIDATE", f"no strike combination fits the delta bands {bands}")
    return generated


def _spread_leg(action: str, lots: int, quote: Quote, delta: float) -> SpreadLeg:
    buying = action == BUY
    return SpreadLeg(
        action, quote.option_type, quote.strike, lots,
        quote.ask if buying else quote.bid, "ask" if buying else "bid",
        quote.iv, round(delta, 4), quote.bid, quote.ask, quote.open_interest, quote.volume,
        quote.tick,
    )  # fmt: skip


def _evaluate_one(
    frame: Frame, candidate: Candidate
) -> tuple[Optional[Spread], Optional[Rejection]]:
    """Price one candidate and apply the rules: ``(spread, None)`` or ``(None, why)``."""
    spec, chain = frame.structure, frame.chain
    legs = tuple(
        _spread_leg(leg.action, leg.lots, quote, delta)
        for leg, (quote, delta) in zip(spec.legs, candidate, strict=True)
    )
    subject = " / ".join(f"{l.action} {l.option_type} {l.strike:g}" for l in legs)  # noqa: E741
    payoff_legs = [
        Leg(
            l.action,
            l.option_type,
            l.strike,
            l.premium,
            l.lots,
            chain.lot_size,
            frame.expiry,
            l.iv,
        )  # fmt: skip
        for l in legs  # noqa: E741 - short alias in a one-line comprehension
    ]
    extremes = max_profit_loss(payoff_legs)
    max_profit, max_loss = extremes.max_profit.value, -extremes.max_loss.value
    if not (0 < max_profit < math.inf and 0 < max_loss < math.inf):
        return None, Rejection("NO_EDGE", "no finite, positive profit and risk", subject)

    net = net_premium(payoff_legs)
    strikes = [l.strike for l in legs]  # noqa: E741
    facts = CandidateFacts(
        regime=frame.regime,
        net_per_share=net / chain.lot_size,
        width=max(strikes) - min(strikes),
        reward_risk=max_profit / max_loss,
        pop=analyze_probability(payoff_legs, chain.spot, frame.atm_iv, frame.days).pop,
    )
    for rule in spec.rules:
        failed = rule(facts, frame.policy)
        if failed:
            return None, Rejection(failed.code, failed.detail, subject)

    return (
        Spread(
            structure=spec.key, family=spec.family, regime=frame.regime, underlying=chain.symbol,
            expiry=frame.expiry, dte=frame.dte, lot_size=chain.lot_size, legs=legs,
            width=facts.width, net_premium=round(net, 2), max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2), reward_risk=round(facts.reward_risk, 2),
            pop=round(facts.pop, 4), breakevens=tuple(round(b, 2) for b in breakevens(payoff_legs)),
            straddle_pct=round(frame.straddle_pct, 3), atm_iv=round(frame.atm_iv, 2),
        ),
        None,
    )  # fmt: skip


def _evaluate(frame: Frame) -> Frame | SpreadResult:
    passed: list[Spread] = []
    rejected = list(frame.rejections)
    for candidate in frame.candidates:
        spread, why = _evaluate_one(frame, candidate)
        if spread is not None:
            passed.append(spread)
        else:
            rejected.append(why)
    evaluated = replace(frame, passed=tuple(passed), rejections=tuple(rejected))
    if not passed:
        return evaluated.skip(
            "ALL_REJECTED", f"{len(frame.candidates)} candidate(s) failed the payoff rules"
        )
    return evaluated


def _rank(frame: Frame) -> SpreadResult:
    ranked = tuple(sorted(frame.passed, key=frame.structure.rank))
    return SpreadResult(
        spread=ranked[0],
        rejections=frame.rejections,
        alternatives=ranked,
        regime=frame.regime,
        straddle_pct=round(frame.straddle_pct, 3),
    )


PIPELINE = (
    _validate,
    _pick_expiry,
    _measure_volatility,
    _choose_structure,
    _screen_legs,
    _generate,
    _evaluate,
)


# ── Entry points ─────────────────────────────────────────────────────────────


def build_spread(
    fresh: FreshChain,
    action: str,
    now: dt.datetime,
    policy: SpreadPolicy,
    chooser: StructureChooser,
) -> SpreadResult:
    """Run the pipeline with any structure chooser: a new strategy is a new chooser."""
    frame: Frame | SpreadResult = Frame(fresh, (action or "").upper(), now, policy, chooser)
    for stage in PIPELINE:
        frame = stage(frame)
        if isinstance(frame, SpreadResult):
            return frame
    return _rank(frame)


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
    return build_spread(fresh, action, now, policy, choose_vertical)


__all__ = [
    "FreshChain",
    "Frame",
    "Spread",
    "SpreadLeg",
    "SpreadResult",
    "StaleChainError",
    "build_spread",
    "build_vertical_spread",
]
