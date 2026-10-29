"""One small function per spread rule. Each returns a :class:`Rejection` or ``None``.

A rule never raises and never logs; it says *why* in a short code that a calibration report can
count (``LOW_OI``, ``WIDE_SPREAD``, ...). Adding a rule is adding a function here and one line where
the engine applies it, which is what lets the same pipeline serve other structures later.
"""

from dataclasses import dataclass
from typing import Optional

from tb_utils.options.ideas import Quote
from tb_utils.options.spread_policy import TRANSITIONAL, SpreadPolicy


@dataclass(frozen=True)
class Rejection:
    """Why one contract or one candidate was dropped."""

    code: str
    detail: str
    subject: str = ""  # e.g. "CE 1040", or "BUY CE 1020 / SELL CE 1050"


def _subject(quote: Quote) -> str:
    return f"{quote.option_type} {quote.strike:g}"


def bid_ask_limit(mid: float, tick: float, policy: SpreadPolicy) -> float:
    """The widest acceptable bid-ask spread: a share of the mid, but never less than a tick.

    A pure percentage cannot be met on a cheap option, where one tick is already a large share of
    the price, so the contract's own tick sets a floor.
    """
    return max(policy.max_bid_ask_pct * mid, policy.bid_ask_floor_ticks * tick)


def check_leg_liquidity(quote: Quote, policy: SpreadPolicy) -> Optional[Rejection]:
    """A leg must be two-sided, have an IV, and clear the OI, volume and bid-ask spread floors."""
    subject = _subject(quote)
    if not (quote.bid and quote.ask and quote.bid > 0 and quote.ask > 0):
        return Rejection("NO_QUOTE", "no two-sided quote", subject)
    if not quote.iv or quote.iv <= 0:
        return Rejection("NO_QUOTE", "no implied volatility", subject)
    if quote.open_interest < policy.min_open_interest:
        return Rejection(
            "LOW_OI", f"open interest {quote.open_interest} < {policy.min_open_interest}", subject
        )
    if quote.volume < policy.min_volume:
        return Rejection("LOW_VOLUME", f"volume {quote.volume} < {policy.min_volume}", subject)
    spread = quote.ask - quote.bid
    limit = bid_ask_limit((quote.ask + quote.bid) / 2.0, quote.tick, policy)
    if spread > limit + 1e-9:
        return Rejection("WIDE_SPREAD", f"bid-ask {spread:.2f} > limit {limit:.2f}", subject)
    return None


def check_reward_risk(reward_risk: float, regime: str, policy: SpreadPolicy) -> Optional[Rejection]:
    """Debit spreads: the payoff must be at least the regime's minimum multiple of the risk."""
    floor = (
        policy.transitional_min_reward_risk if regime == TRANSITIONAL else policy.min_reward_risk
    )
    if reward_risk < floor - 1e-9:
        return Rejection("LOW_REWARD_RISK", f"reward:risk {reward_risk:.2f} < {floor:g}")
    return None


def check_pop(pop: float, family: str, policy: SpreadPolicy) -> Optional[Rejection]:
    """Probability of profit, with a higher bar for credit spreads, which win often by design."""
    floor = policy.min_pop_credit if family == "CREDIT" else policy.min_pop_debit
    if pop < floor - 1e-9:
        return Rejection("LOW_POP", f"POP {pop:.0%} < {floor:.0%}")
    return None


def check_credit(credit: float, width: float, policy: SpreadPolicy) -> Optional[Rejection]:
    """Credit spreads: the credit collected must be a minimum share of the strike width."""
    if width <= 0 or credit < policy.min_credit_pct_of_width * width - 1e-9:
        return Rejection(
            "LOW_CREDIT",
            f"credit {credit:.2f} < {policy.min_credit_pct_of_width:.0%} of width {width:g}",
        )
    return None
