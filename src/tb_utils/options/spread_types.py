"""The values the spread engine passes around. Plain frozen data, no behaviour beyond validation.

Kept apart from the engine so a structure definition (``spread_structures``) and the engine can both
use them without importing each other.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from tb_utils.options.ideas import ChainData, Skip
from tb_utils.options.spread_rules import Rejection

BUY = "BUY"
SELL = "SELL"
DEBIT = "DEBIT"
CREDIT = "CREDIT"


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
    structure: str  # the StructureSpec key, e.g. bull_call_spread
    family: str  # DEBIT | CREDIT
    regime: str
    underlying: str
    expiry: dt.date
    dte: int
    lot_size: int
    legs: tuple[SpreadLeg, ...]  # bought legs first
    width: float  # outermost strike distance, per share
    net_premium: float  # rupees for the whole position; negative is a debit
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
