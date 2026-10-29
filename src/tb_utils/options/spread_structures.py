"""What a structure *is*, as data: its legs, how their strikes relate, which rules judge it.

The engine is generic over these. A new strategy is a new :class:`StructureSpec` (and, if it picks
itself from the market, a chooser function), not a new engine: the stages that fetch the expiry,
measure volatility, screen the legs for liquidity, price the payoff and rank the survivors are
shared.

Today's structures are the four vertical spreads (spec §4). A butterfly is three ``LegSpec`` rows
and
a strike predicate; the test-suite defines one to prove it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Optional

from tb_utils.options.spread_policy import HIGH_VOL, SpreadPolicy
from tb_utils.options.spread_rules import (
    Rejection,
    check_credit,
    check_pop,
    check_reward_risk,
)
from tb_utils.options.spread_types import BUY, CREDIT, DEBIT, SELL, Spread

Band = tuple[float, float]


@dataclass(frozen=True)
class LegSpec:
    """One leg of a structure: what to do, on which side, at roughly which delta."""

    action: str  # BUY | SELL
    option_type: str  # CE | PE
    delta_band: Band  # absolute delta the strike must fall in
    lots: int = 1


@dataclass(frozen=True)
class CandidateFacts:
    """What a candidate's rules may look at, computed once by the engine."""

    regime: str
    net_per_share: float  # positive is a credit
    width: float
    reward_risk: float
    pop: float


CandidateRule = Callable[[CandidateFacts, SpreadPolicy], Optional[Rejection]]
StrikeOrder = Callable[[Sequence[float]], bool]  # strikes in leg order -> is this a valid shape
Ranker = Callable[[Spread], tuple]  # smaller sorts first


@dataclass(frozen=True)
class StructureSpec:
    """A complete, engine-ready description of one strategy shape."""

    key: str
    family: str  # DEBIT | CREDIT
    legs: tuple[LegSpec, ...]  # bought legs first: that is the order they are sent
    strike_order: StrikeOrder
    rules: tuple[CandidateRule, ...]
    rank: Ranker

    def __post_init__(self) -> None:
        actions = [leg.action for leg in self.legs]
        first_sold = next((i for i, action in enumerate(actions) if action == SELL), len(actions))
        if BUY in actions[first_sold:]:
            raise ValueError(f"{self.key}: bought legs must come before sold legs")


# ── Rules and rankers shared by the verticals ────────────────────────────────


def _reward_risk_rule(facts: CandidateFacts, policy: SpreadPolicy) -> Optional[Rejection]:
    return check_reward_risk(facts.reward_risk, facts.regime, policy)


def _credit_rule(facts: CandidateFacts, policy: SpreadPolicy) -> Optional[Rejection]:
    return check_credit(facts.net_per_share, facts.width, policy)


def _pop_rule(family: str) -> CandidateRule:
    return lambda facts, policy: check_pop(facts.pop, family, policy)


def _least_risk_first(spread: Spread) -> tuple:
    return (spread.max_loss, -spread.pop)


def _richest_credit_first(spread: Spread) -> tuple:
    return (-spread.net_premium / (spread.width * spread.lot_size), spread.max_loss)


# ── The four verticals ───────────────────────────────────────────────────────


def _vertical(
    key: str,
    family: str,
    option_type: str,
    bought: Band,
    sold: Band,
    sold_above_bought: bool,
) -> StructureSpec:
    return StructureSpec(
        key=key,
        family=family,
        legs=(LegSpec(BUY, option_type, bought), LegSpec(SELL, option_type, sold)),
        strike_order=(lambda k: k[1] > k[0]) if sold_above_bought else (lambda k: k[1] < k[0]),
        rules=(
            (_reward_risk_rule if family == DEBIT else _credit_rule),
            _pop_rule(family),
        ),
        rank=_least_risk_first if family == DEBIT else _richest_credit_first,
    )


def choose_vertical(action: str, regime: str, policy: SpreadPolicy) -> StructureSpec:
    """The vertical for a BUY/SELL signal: debit in low volatility, credit when premium is rich."""
    bullish = action == BUY
    if regime == HIGH_VOL:
        return _vertical(
            "bull_put_spread" if bullish else "bear_call_spread",
            CREDIT,
            "PE" if bullish else "CE",
            policy.credit_long_delta,
            policy.credit_short_delta,
            sold_above_bought=bullish,
        )
    return _vertical(
        "bull_call_spread" if bullish else "bear_put_spread",
        DEBIT,
        "CE" if bullish else "PE",
        policy.debit_long_delta,
        policy.debit_short_delta,
        sold_above_bought=bullish,
    )


StructureChooser = Callable[[str, str, SpreadPolicy], StructureSpec]
