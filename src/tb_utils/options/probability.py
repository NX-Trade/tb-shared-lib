"""Probability of profit and expected value of an option basket at expiry.

Pure functions over :mod:`tb_utils.options.payoff` legs — no DB, no Redis, no HTTP.
Design: tb-ai-brain/upcoming/OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md §8A.2, §8A.3 and
open item M-2.

Model
-----
The terminal price is lognormal: ``ln S_T ~ Normal(m, s²)`` with ``s = σ√T``.

* **Market (risk-neutral)** distribution: ``m = ln F − s²/2`` with ``F = S·e^{rT}``, so the mean is
  the forward. A fairly priced basket has EV ≈ 0 here — what it shows is the *cost* of trading
  (crossing the bid-ask). It cannot rank structures, which is why M-2 exists.
* **View-tilted** distribution: the same width, with the mean log-return shifted by
  ``conviction × ln(target / spot)``. EV at the view is the quantity a generator may rank on.

Both measures are **exact**, not simulated. The expiry payoff is piecewise linear in spot with
kinks only at strikes, so on each segment ``payoff = α + β·S`` and the lognormal partial moments
``P(a < S < b)`` and ``E[S; a < S < b]`` have closed forms. POP is the probability mass of the
segments between breakevens where the payoff is positive.

One ``σ`` is used for the whole basket (the at-the-money IV), so the smile is not modelled in
the distribution; the legs themselves are still priced from their own strikes by ``payoff.py``.
Units follow ``payoff.py``: money is rupees for the whole position, ``σ`` is in percent points.
"""

# stdlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

# internal
from tb_utils.greeks import DEFAULT_RISK_FREE_RATE
from tb_utils.options.payoff import Leg, breakevens, payoff_at_expiry

DAYS_PER_YEAR = 365.0
_MAX_CONVICTION = 1.0


@dataclass(frozen=True)
class Terminal:
    """Lognormal terminal-price distribution: ``ln S_T ~ Normal(mu, sigma_t²)``."""

    spot: float
    mu: float  # mean of ln S_T
    sigma_t: float  # σ√T; 0 means the price is already known (expiry today)

    @property
    def mean(self) -> float:
        return math.exp(self.mu + self.sigma_t**2 / 2.0)

    @property
    def median(self) -> float:
        return math.exp(self.mu)


@dataclass(frozen=True)
class ProbabilityResult:
    pop: float  # 0..1
    expected_value: float  # rupees, whole position
    sigma_pct: float
    days: float
    mean: float  # mean terminal price
    one_sigma_low: float
    one_sigma_high: float


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def view_tilt(spot: float, target: float, conviction: float) -> float:
    """Shift of the mean log-return that a view with ``target`` and ``conviction`` implies."""
    if spot <= 0 or target <= 0:
        raise ValueError("spot and target must be positive")
    if not 0.0 <= conviction <= _MAX_CONVICTION:
        raise ValueError("conviction must be between 0 and 1")
    return conviction * math.log(target / spot)


def terminal_distribution(
    spot: float,
    iv_pct: float,
    days: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
    tilt: float = 0.0,
) -> Terminal:
    """Terminal distribution at expiry, ``days`` calendar days out.

    ``tilt`` is added to the mean log-return (see :func:`view_tilt`); 0 is the market measure.
    """
    if spot <= 0:
        raise ValueError("spot must be positive")
    if iv_pct <= 0:
        raise ValueError("iv_pct must be positive")
    t = max(days, 0.0) / DAYS_PER_YEAR
    sigma_t = (iv_pct / 100.0) * math.sqrt(t)
    mu = math.log(spot) + rate * t - sigma_t**2 / 2.0 + tilt
    return Terminal(spot=spot, mu=mu, sigma_t=sigma_t)


def density(dist: Terminal, price: float) -> float:
    """Probability density of the terminal price at ``price`` (0 for non-positive prices)."""
    if price <= 0 or dist.sigma_t <= 0:
        return 0.0
    z = (math.log(price) - dist.mu) / dist.sigma_t
    return math.exp(-0.5 * z * z) / (price * dist.sigma_t * math.sqrt(2.0 * math.pi))


def _mass(dist: Terminal, low: float, high: float) -> float:
    """``P(low < S_T < high)``; ``high`` may be ``inf``, ``low`` may be 0."""
    lo = 0.0 if low <= 0 else _cdf((math.log(low) - dist.mu) / dist.sigma_t)
    hi = 1.0 if math.isinf(high) else _cdf((math.log(high) - dist.mu) / dist.sigma_t)
    return max(hi - lo, 0.0)


def _partial_mean(dist: Terminal, low: float, high: float) -> float:
    """``E[S_T; low < S_T < high]``."""

    def shifted(x: float) -> float:
        if x <= 0:
            return 0.0
        if math.isinf(x):
            return 1.0
        return _cdf((math.log(x) - dist.mu - dist.sigma_t**2) / dist.sigma_t)

    return dist.mean * max(shifted(high) - shifted(low), 0.0)


def _segments(legs: Sequence[Leg]) -> list[tuple[float, float, float, float]]:
    """``(low, high, alpha, beta)`` per linear piece of the expiry payoff, tails included."""
    knots = sorted({0.0, *(leg.strike for leg in legs)})
    pieces = []
    for low, high in zip(knots, knots[1:], strict=False):
        p_low, p_high = payoff_at_expiry(legs, low), payoff_at_expiry(legs, high)
        beta = (p_high - p_low) / (high - low)
        pieces.append((low, high, p_low - beta * low, beta))
    last = knots[-1]
    p_last = payoff_at_expiry(legs, last)
    beta = payoff_at_expiry(legs, last + 1.0) - p_last
    pieces.append((last, math.inf, p_last - beta * last, beta))
    return pieces


def _known_price_value(legs: Sequence[Leg], price: float) -> tuple[float, float]:
    """Degenerate case (expiry today): the payoff at the current price, and 1 if it is a profit."""
    pnl = payoff_at_expiry(legs, price)
    return pnl, 1.0 if pnl > 0 else 0.0


def expected_value(legs: Sequence[Leg], dist: Terminal, costs: float = 0.0) -> float:
    """Expected expiry P&L in rupees for the whole position, minus ``costs``."""
    if dist.sigma_t <= 0:
        return _known_price_value(legs, dist.mean)[0] - costs
    total = 0.0
    for low, high, alpha, beta in _segments(legs):
        total += alpha * _mass(dist, low, high) + beta * _partial_mean(dist, low, high)
    return total - costs


def probability_of_profit(legs: Sequence[Leg], dist: Terminal) -> float:
    """Probability the position finishes at expiry with a positive P&L."""
    if dist.sigma_t <= 0:
        return _known_price_value(legs, dist.mean)[1]
    edges = [0.0, *breakevens(legs), math.inf]
    mass = 0.0
    for low, high in zip(edges, edges[1:], strict=False):
        probe = low + 1.0 if math.isinf(high) else (low + high) / 2.0
        if payoff_at_expiry(legs, probe) > 0:
            mass += _mass(dist, low, high)
    return min(mass, 1.0)


def analyze_probability(
    legs: Sequence[Leg],
    spot: float,
    iv_pct: float,
    days: float,
    *,
    rate: float = DEFAULT_RISK_FREE_RATE,
    tilt: float = 0.0,
    costs: float = 0.0,
) -> ProbabilityResult:
    """POP, expected value and the one-σ range under the market (``tilt=0``) or a tilted view."""
    dist = terminal_distribution(spot, iv_pct, days, rate, tilt)
    return ProbabilityResult(
        pop=probability_of_profit(legs, dist),
        expected_value=expected_value(legs, dist, costs),
        sigma_pct=iv_pct,
        days=max(days, 0.0),
        mean=dist.mean,
        one_sigma_low=math.exp(dist.mu - dist.sigma_t),
        one_sigma_high=math.exp(dist.mu + dist.sigma_t),
    )


def density_curve(dist: Terminal, spots: Sequence[float]) -> list[tuple[float, float]]:
    """``(spot, density)`` pairs for shading a payoff chart."""
    return [(s, density(dist, s)) for s in spots]


__all__ = [
    "ProbabilityResult",
    "Terminal",
    "analyze_probability",
    "density",
    "density_curve",
    "expected_value",
    "probability_of_profit",
    "terminal_distribution",
    "view_tilt",
]
