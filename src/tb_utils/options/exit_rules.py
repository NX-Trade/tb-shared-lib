"""Reference amounts that exit thresholds are measured against, for any option basket.

A position monitor exits at "75 % of the profit target" and "60 % of the loss limit". Those
percentages are only meaningful against the right amount:

* **Loss limit** is the expiry max loss — always correct, it is what you can actually lose.
* **Profit target** is the expiry max profit for a plain vertical, where the leg values converge
  on it as spot moves through the short strike. For a butterfly, condor or any other shaped
  structure the expiry maximum is *unreachable before expiry*: with 15 days left a long
  butterfly is worth ~21 % of it even with spot sitting on the peak strike, so a threshold set
  against the expiry maximum never fires and the position rides to expiry by default. Those
  structures use the peak of the Black-Scholes T+n curve at the **halfway date** between today
  and expiry. That is the best the position can realistically be closed for over a typical hold:
  measuring at "today" is unstable (a credit structure is priced at fair value on entry, so its
  T+n peak today is ~0 and a percentage of it would fire on a few rupees), while the halfway
  date is stable at entry and rises toward the expiry maximum as the position ages.

Pure functions only — see ``payoff.py``. Design: OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md
§5A.3 and open item O-6.
"""

# stdlib
import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

# internal
from tb_utils.options.payoff import (
    CE,
    PE,
    Leg,
    default_spot_range,
    max_profit_loss,
    payoff_curve,
)

EXPIRY_MAX = "EXPIRY_MAX"
T_PLUS_N = "T_PLUS_N"

_CURVE_POINTS = 241


@dataclass(frozen=True)
class ExitBasis:
    """Rupee amounts for the whole position that exit percentages are applied to.

    ``None`` means no finite basis exists (open-ended loss, or no profit to capture), in which
    case the caller must not apply a percentage threshold on that side.
    """

    profit: Optional[float]
    loss: Optional[float]
    profit_source: str  # EXPIRY_MAX | T_PLUS_N
    max_profit_at_expiry: float  # may be math.inf
    max_loss_at_expiry: float  # positive magnitude, may be math.inf


def is_vertical(legs: Sequence[Leg]) -> bool:
    """Two options of the same type and expiry, one bought and one sold, same quantity."""
    if len(legs) != 2:
        return False
    first, second = legs
    return (
        first.option_type in (CE, PE)
        and first.option_type == second.option_type
        and first.expiry == second.expiry
        and first.direction != second.direction
        and first.strike != second.strike
        and first.lots * first.lot_size == second.lots * second.lot_size
    )


def _halfway_date(legs: Sequence[Leg], as_of: dt.date) -> dt.date:
    """Midpoint between ``as_of`` and the last expiry; ``as_of`` itself once at/after expiry."""
    expiry = max(leg.expiry for leg in legs)
    remaining = (expiry - as_of).days
    return as_of + dt.timedelta(days=max(remaining, 0) // 2)


def _t_plus_n_peak(legs: Sequence[Leg], spot: float, as_of: dt.date) -> float:
    spot_min, spot_max = default_spot_range(legs, spot)
    reference = _halfway_date(legs, as_of)
    curve = payoff_curve(legs, spot_min, spot_max, _CURVE_POINTS, as_of=reference)
    return max(pnl for _, pnl in curve)


def exit_basis(legs: Sequence[Leg], spot: float, as_of: dt.date) -> ExitBasis:
    """Amounts a profit-target and a stop-loss percentage should be applied to.

    ``as_of`` is today; the T+n reference date is derived from it (see module docstring).

    Falls back to the expiry maximum when a leg has no IV (T+n cannot be priced) rather than
    guessing one.
    """
    extremes = max_profit_loss(legs)
    max_profit = extremes.max_profit.value
    max_loss = -extremes.max_loss.value if extremes.max_loss.value < 0 else 0.0

    priceable = all(leg.iv is not None and leg.iv > 0 for leg in legs)
    if is_vertical(legs) or not priceable:
        profit: Optional[float] = max_profit
        source = EXPIRY_MAX
    else:
        peak = _t_plus_n_peak(legs, spot, as_of)
        profit = min(peak, max_profit)
        source = T_PLUS_N

    if profit is not None and (profit <= 0 or math.isinf(profit)):
        profit = None
    loss: Optional[float] = None if (max_loss <= 0 or math.isinf(max_loss)) else max_loss
    return ExitBasis(
        profit=profit,
        loss=loss,
        profit_source=source,
        max_profit_at_expiry=max_profit,
        max_loss_at_expiry=max_loss,
    )
