"""Option basket payoff, breakevens, max profit/loss and net greeks.

Pure functions over plain dataclasses — no DB session, no Redis, no HTTP — so the same
numbers can be produced from a request path, a Celery task and a backtest alike.
Design: tb-ai-brain/upcoming/OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md (§5A, §6.1, App. A).

Units (the most common bug in payoff code)
------------------------------------------
* ``Leg.premium``, ``Leg.strike`` and spot are **per share**.
* Every ``*_pnl`` / payoff / greek returned here is in **rupees for the whole position**,
  i.e. already multiplied by ``lots × lot_size``. The multiplication happens exactly once,
  inside ``_leg_scale``; nothing downstream mixes units.
* ``Leg.iv`` and ``iv_shift`` are in **percent points** (24.5 = 24.5 %), matching
  ``tb_utils.greeks``.

Sign convention: ``net_premium`` negative = debit (you pay), positive = credit.

Scope: single-expiry baskets for the at-expiry functions. Calendars/diagonals need per-leg
pre-expiry pricing, which ``payoff_at_date`` supports, but the at-expiry shortcuts refuse
mixed expiries rather than return a wrong curve.
"""

# stdlib
import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

# internal
from tb_utils.greeks import DEFAULT_RISK_FREE_RATE, black_scholes_price, calculate_greeks

BUY = "BUY"
SELL = "SELL"
CE = "CE"
PE = "PE"
FUT = "FUT"

_ACTIONS = (BUY, SELL)
_INSTRUMENT_TYPES = (CE, PE, FUT)
_MIN_IV_PCT = 0.01  # floor after an iv_shift, so a large down-shift cannot go non-positive
_ZERO_TOL = 1e-9
_DEFAULT_RANGE_PAD = 0.10  # curve extends 10 % beyond the outermost strike / spot

GREEK_KEYS = ("delta", "gamma", "theta", "vega")


@dataclass(frozen=True)
class Leg:
    """One leg of an option basket.

    For ``FUT`` legs ``strike`` is the futures entry price and ``premium`` must be 0.
    """

    action: str  # BUY | SELL
    option_type: str  # CE | PE | FUT
    strike: float
    premium: float  # per share
    lots: int
    lot_size: int
    expiry: dt.date
    iv: Optional[float] = None  # percent; per-strike IV, required for pre-expiry pricing

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError(f"action must be one of {_ACTIONS}, got {self.action!r}")
        if self.option_type not in _INSTRUMENT_TYPES:
            raise ValueError(
                f"option_type must be one of {_INSTRUMENT_TYPES}, got {self.option_type!r}"
            )
        if self.strike <= 0:
            raise ValueError(f"strike must be > 0, got {self.strike}")
        if self.premium < 0:
            raise ValueError(f"premium must be >= 0, got {self.premium}")
        if self.option_type == FUT and self.premium != 0:
            raise ValueError("FUT legs carry no premium; strike is the entry price")
        if self.lots <= 0 or self.lot_size <= 0:
            raise ValueError("lots and lot_size must be positive")

    @property
    def direction(self) -> int:
        """+1 for BUY, -1 for SELL."""
        return 1 if self.action == BUY else -1


@dataclass(frozen=True)
class Extreme:
    """A profit or loss extreme. ``value`` is ±inf when that side is unbounded."""

    value: float
    at_spot: Optional[float]  # None when unbounded (the extreme lies on an open tail)


@dataclass(frozen=True)
class PayoffExtremes:
    max_profit: Extreme
    max_loss: Extreme


# ── Internals ────────────────────────────────────────────────────────────────


def _leg_scale(leg: Leg) -> float:
    """Signed share count of a leg: the single place per-share becomes rupees."""
    return leg.direction * leg.lots * leg.lot_size


def _intrinsic(leg: Leg, spot: float) -> float:
    if leg.option_type == CE:
        return max(spot - leg.strike, 0.0)
    if leg.option_type == PE:
        return max(leg.strike - spot, 0.0)
    return spot - leg.strike


def _require_legs(legs: Sequence[Leg]) -> None:
    if not legs:
        raise ValueError("at least one leg is required")


def _require_single_expiry(legs: Sequence[Leg]) -> None:
    _require_legs(legs)
    if len({leg.expiry for leg in legs}) > 1:
        raise ValueError(
            "at-expiry payoff requires a single expiry; use payoff_at_date for calendars"
        )


def _days_to_expiry(leg: Leg, as_of: dt.date) -> int:
    return (leg.expiry - as_of).days


def _shifted_iv(leg: Leg, iv_shift: float) -> float:
    if leg.iv is None:
        raise ValueError(
            f"pre-expiry pricing needs iv on every option leg ({leg.option_type} {leg.strike})"
        )
    return max(leg.iv + iv_shift, _MIN_IV_PCT)


def _leg_value(leg: Leg, spot: float, as_of: dt.date, iv_shift: float, rate: float) -> float:
    """Per-share value of a leg at ``as_of`` — Black-Scholes before expiry, intrinsic at/after."""
    if leg.option_type == FUT:
        return spot - leg.strike
    tau = _days_to_expiry(leg, as_of)
    if tau <= 0:
        return _intrinsic(leg, spot)
    price = black_scholes_price(
        spot, leg.strike, tau, _shifted_iv(leg, iv_shift), leg.option_type, rate
    )
    if price is None:
        raise ValueError(
            f"cannot price {leg.option_type} {leg.strike} at spot {spot} with {tau} days left"
        )
    return price


def _tail_slope(legs: Sequence[Leg]) -> float:
    """Rupees of P&L per +1 of spot as spot → ∞. Only CE and FUT legs keep moving."""
    return sum(_leg_scale(leg) for leg in legs if leg.option_type in (CE, FUT))


# ── Net premium ──────────────────────────────────────────────────────────────


def net_premium_per_share(legs: Sequence[Leg]) -> float:
    """Σ sign × lots × premium. Negative = debit. Matches App. A.1 (TechM: −7.45)."""
    _require_legs(legs)
    return sum(-leg.direction * leg.lots * leg.premium for leg in legs)


def net_premium(legs: Sequence[Leg]) -> float:
    """Signed cash flow at entry in rupees. Negative = debit (TechM: −4,470)."""
    _require_legs(legs)
    return sum(-_leg_scale(leg) * leg.premium for leg in legs)


# ── Payoff ───────────────────────────────────────────────────────────────────


def payoff_at_expiry(legs: Sequence[Leg], spot: float) -> float:
    """Position P&L in rupees if every leg expires with the underlying at ``spot``."""
    _require_single_expiry(legs)
    return sum(_leg_scale(leg) * (_intrinsic(leg, spot) - leg.premium) for leg in legs)


def payoff_at_date(
    legs: Sequence[Leg],
    spot: float,
    as_of: dt.date,
    iv_shift: float = 0.0,
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> float:
    """Position P&L in rupees at ``as_of`` (T+n), each option priced by Black-Scholes.

    Uses each leg's own IV so the smile prices wings differently from the body. Legs
    at or past expiry fall back to intrinsic value. ``iv_shift`` is added to every
    leg's IV, in percent points, for a vega stress view.
    """
    _require_legs(legs)
    return sum(
        _leg_scale(leg) * (_leg_value(leg, spot, as_of, iv_shift, rate) - leg.premium)
        for leg in legs
    )


def default_spot_range(
    legs: Sequence[Leg], spot: float, pad: float = _DEFAULT_RANGE_PAD
) -> tuple[float, float]:
    """Spot range wide enough to show the flat tails beyond the outermost strikes."""
    _require_legs(legs)
    levels = [leg.strike for leg in legs] + [spot]
    return min(levels) * (1.0 - pad), max(levels) * (1.0 + pad)


def payoff_curve(
    legs: Sequence[Leg],
    spot_min: float,
    spot_max: float,
    points: int = 201,
    as_of: Optional[dt.date] = None,
    iv_shift: float = 0.0,
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> list[tuple[float, float]]:
    """``(spot, pnl)`` pairs across ``[spot_min, spot_max]``.

    At expiry when ``as_of`` is None, otherwise Black-Scholes priced at ``as_of``.
    """
    if points < 2:
        raise ValueError("points must be >= 2")
    if spot_max <= spot_min:
        raise ValueError("spot_max must be greater than spot_min")
    step = (spot_max - spot_min) / (points - 1)
    spots = [spot_min + i * step for i in range(points)]
    if as_of is None:
        return [(s, payoff_at_expiry(legs, s)) for s in spots]
    return [(s, payoff_at_date(legs, s, as_of, iv_shift, rate)) for s in spots]


# ── Breakevens and extremes ──────────────────────────────────────────────────
# Expiry payoff of an option portfolio is piecewise linear in spot with kinks only at
# strikes, so both are solved exactly on the kinks — no grid, no bisection tolerance.


def _knots(legs: Sequence[Leg]) -> list[float]:
    return sorted({0.0, *(leg.strike for leg in legs)})


def breakevens(legs: Sequence[Leg]) -> list[float]:
    """Every spot at which the expiry payoff crosses zero, ascending.

    Never assumes a count: a long call has one, a long fly one, an iron condor two,
    a short straddle two. Returns [] when the payoff never crosses zero.
    """
    _require_single_expiry(legs)
    xs = _knots(legs)
    vs = [payoff_at_expiry(legs, x) for x in xs]
    found: list[float] = []

    for i in range(len(xs) - 1):
        a, b, va, vb = xs[i], xs[i + 1], vs[i], vs[i + 1]
        if abs(va) > _ZERO_TOL and abs(vb) > _ZERO_TOL and (va < 0) != (vb < 0):
            found.append(a + (b - a) * (-va) / (vb - va))

    # Open right tail: linear beyond the last strike with a non-zero slope.
    slope = _tail_slope(legs)
    last_x, last_v = xs[-1], vs[-1]
    if abs(slope) > _ZERO_TOL and abs(last_v) > _ZERO_TOL and (last_v < 0) != (slope < 0):
        # sign differs between the tail's value at the last strike and its direction of travel
        found.append(last_x + (-last_v) / slope)

    # Exact zeros sitting on a kink (a crossing or an isolated touch, not a flat zero run).
    for i, (x, v) in enumerate(zip(xs, vs, strict=True)):
        if abs(v) > _ZERO_TOL or x == 0.0:
            continue
        left = vs[i - 1] if i > 0 else 0.0
        right = vs[i + 1] if i + 1 < len(xs) else (slope if abs(slope) > _ZERO_TOL else 0.0)
        if abs(left) > _ZERO_TOL or abs(right) > _ZERO_TOL:
            found.append(x)

    return sorted({round(x, 6) for x in found})


def max_profit_loss(legs: Sequence[Leg]) -> PayoffExtremes:
    """Max profit and max loss at expiry, in rupees.

    An open tail with non-zero slope is reported as ±inf, never as a finite number
    read off the end of a plotting grid — a short straddle must not show a finite loss.
    Ties resolve to the lowest *strike* (the left flat tail is reported at its kink, not at 0).
    """
    _require_single_expiry(legs)
    strikes = sorted({leg.strike for leg in legs})
    candidates = [(s, payoff_at_expiry(legs, s)) for s in strikes]
    # Spot cannot go below 0, so the left side is a finite endpoint; it only wins if
    # strictly better.
    zero_value = payoff_at_expiry(legs, 0.0)

    best_profit = max(candidates, key=lambda c: c[1])
    best_loss = min(candidates, key=lambda c: c[1])
    max_p = Extreme(best_profit[1], best_profit[0])
    max_l = Extreme(best_loss[1], best_loss[0])
    if zero_value > max_p.value + _ZERO_TOL:
        max_p = Extreme(zero_value, 0.0)
    if zero_value < max_l.value - _ZERO_TOL:
        max_l = Extreme(zero_value, 0.0)

    slope = _tail_slope(legs)
    if slope > _ZERO_TOL:
        max_p = Extreme(math.inf, None)
    elif slope < -_ZERO_TOL:
        max_l = Extreme(-math.inf, None)

    return PayoffExtremes(max_profit=max_p, max_loss=max_l)


# ── Net greeks ───────────────────────────────────────────────────────────────


def net_greeks(
    legs: Sequence[Leg],
    spot: float,
    as_of: dt.date,
    iv_shift: float = 0.0,
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> dict[str, float]:
    """Position greeks, summed over legs and scaled by lots × lot_size.

    Units follow ``tb_utils.greeks``: delta in share-equivalents, gamma per ₹1 of spot,
    theta in ₹/day, vega in ₹ per 1 IV point. A leg at or past expiry contributes only
    its intrinsic delta.
    """
    _require_legs(legs)
    totals: dict[str, float] = {key: 0.0 for key in GREEK_KEYS}
    for leg in legs:
        scale = _leg_scale(leg)
        if leg.option_type == FUT:
            totals["delta"] += scale
            continue
        tau = _days_to_expiry(leg, as_of)
        if tau <= 0:
            in_the_money = _intrinsic(leg, spot) > 0
            if in_the_money:
                totals["delta"] += scale * (1.0 if leg.option_type == CE else -1.0)
            continue
        greeks = calculate_greeks(
            spot, leg.strike, tau, _shifted_iv(leg, iv_shift), rate, leg.option_type
        )
        for key in GREEK_KEYS:
            value = greeks[key]
            if value is None:
                raise ValueError(
                    f"cannot compute {key} for {leg.option_type} {leg.strike} at spot {spot}"
                )
            totals[key] += scale * value
    return totals
