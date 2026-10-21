"""Gamma exposure (GEX) of an option chain: where dealers' hedging would damp or amplify a move.

Pure functions, no I/O. The figures are an **estimate under a stated convention**: exchanges publish
open interest by strike but not who holds it, so this assumes the usual one - customers net long the
calls and short the puts, dealers the other side - which counts call gamma as positive and put
gamma as negative. Where that is wrong the sign of a strike's GEX is wrong; the shape (where gamma
is concentrated) is not.

* GEX of a contract is ``gamma x open_interest x spot^2 x 1%`` in rupees: how many rupees of the
  underlying dealers must trade to stay hedged for a 1% move. ``open_interest`` is in shares, as the
  chain stores it.
* Positive total GEX (spot above the *flip*): dealers buy dips and sell rallies, so moves are damped
  and price tends to pin. Negative (spot below the flip): they chase the move, so it accelerates.
* Gamma is recomputed from each contract's implied volatility, because the broker's published gamma
  is rounded to four decimals, too coarse near the tails.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from tb_utils.greeks import DEFAULT_RISK_FREE_RATE

PERCENT_MOVE = 0.01
MIN_YEARS = (
    0.5 / 365.0
)  # gamma blows up as time runs out; never read a chain as less than half a day
CALL = "CE"
PUT = "PE"


@dataclass(frozen=True)
class GexContract:
    strike: float
    option_type: str  # CE | PE
    open_interest: float  # shares
    iv: Optional[float] = None  # percent
    gamma: Optional[float] = None  # the broker's, used only when there is no IV


@dataclass(frozen=True)
class GexStrike:
    strike: float
    call_gex: float  # positive
    put_gex: float  # negative

    @property
    def net_gex(self) -> float:
        return self.call_gex + self.put_gex


@dataclass(frozen=True)
class Gex:
    spot: float
    by_strike: tuple[GexStrike, ...]
    profile: tuple[tuple[float, float], ...]  # (hypothetical spot, total net GEX)
    flip: Optional[float]  # spot where total net GEX changes sign, nearest to spot
    total: float  # net GEX at the current spot
    call_wall: Optional[float]  # strike with the most call GEX: resistance
    put_wall: Optional[float]  # strike with the most put GEX: support


def bs_gamma(
    spot: float,
    strike: float,
    years: float,
    iv_percent: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> float:
    """Black-Scholes gamma (per unit of underlying). Zero for a degenerate input."""
    sigma = iv_percent / 100.0
    if spot <= 0 or strike <= 0 or sigma <= 0 or years <= 0:
        return 0.0
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * years) / (sigma * root_t)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    return pdf / (spot * sigma * root_t)


def _gamma(contract: GexContract, spot: float, years: float, reference_spot: float) -> float:
    """Gamma at ``spot``; the broker's number is only usable at the spot it was published for."""
    if contract.iv and contract.iv > 0:
        return bs_gamma(spot, contract.strike, years, contract.iv)
    if contract.gamma and spot == reference_spot:
        return contract.gamma
    return 0.0


def _contract_gex(contract: GexContract, gamma: float, spot: float) -> float:
    sign = 1.0 if contract.option_type == CALL else -1.0
    return sign * gamma * contract.open_interest * spot * spot * PERCENT_MOVE


def net_gex_at(
    contracts: Sequence[GexContract], spot: float, years: float, reference_spot: float
) -> float:
    """Total net GEX if the underlying stood at ``spot``."""
    return sum(_contract_gex(c, _gamma(c, spot, years, reference_spot), spot) for c in contracts)


def _crossings(profile: Sequence[tuple[float, float]]) -> list[float]:
    """Spots where the profile changes sign, linearly interpolated between grid points."""
    found = []
    for (x0, y0), (x1, y1) in zip(profile, profile[1:], strict=False):
        if y0 == 0:
            found.append(x0)
        elif y0 * y1 < 0:
            found.append(x0 + (x1 - x0) * (-y0) / (y1 - y0))
    return found


def compute_gex(
    contracts: Sequence[GexContract],
    spot: float,
    days_to_expiry: float,
    *,
    span: float = 0.08,
    steps: int = 33,
) -> Gex:
    """GEX by strike at ``spot``, the total over a grid of spots ``+-span``, and the flip level."""
    years = max(days_to_expiry / 365.0, MIN_YEARS)

    per_strike: dict[float, list[float]] = {}
    for c in contracts:
        if c.open_interest <= 0:
            continue
        value = _contract_gex(c, _gamma(c, spot, years, spot), spot)
        calls_puts = per_strike.setdefault(c.strike, [0.0, 0.0])
        calls_puts[0 if c.option_type == CALL else 1] += value
    by_strike = tuple(
        GexStrike(k, round(v[0], 2), round(v[1], 2)) for k, v in sorted(per_strike.items())
    )

    grid = (
        [spot * (1 - span + 2 * span * i / (steps - 1)) for i in range(steps)] if spot > 0 else []
    )
    profile = tuple((round(s, 2), round(net_gex_at(contracts, s, years, spot), 2)) for s in grid)
    crossings = _crossings(profile)
    flip = round(min(crossings, key=lambda x: abs(x - spot)), 2) if crossings else None

    calls = [s for s in by_strike if s.call_gex > 0]
    puts = [s for s in by_strike if s.put_gex < 0]
    return Gex(
        spot=spot,
        by_strike=by_strike,
        profile=profile,
        flip=flip,
        total=round(sum(s.net_gex for s in by_strike), 2),
        call_wall=max(calls, key=lambda s: s.call_gex).strike if calls else None,
        put_wall=min(puts, key=lambda s: s.put_gex).strike if puts else None,
    )
