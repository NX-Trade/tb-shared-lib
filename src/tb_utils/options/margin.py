"""Estimated margin for an option basket: SPAN scan risk, exposure margin and premium.

Pure functions over ``payoff.Leg`` (no DB, Redis or HTTP), so a request path, a Celery task and a
backtest all produce the same number. Design:
tb-ai-brain/upcoming/OPTION_STRATEGY_BUILDER_AND_MARGIN_DESIGN.md (section 4, Appendix A.7-A.9).

What is implemented
-------------------
SPAN scan risk is the worst one-day loss of the *whole basket* over 16 scenarios, each repricing
every leg with Black-Scholes:

* price moves of 0, +-1/3, +-2/3 and +-1 of the price scan range, each with volatility up and down
  (14 scenarios), then
* two extreme gap moves of +-3x the price scan range, volatility unchanged, where only a fraction
  of the gain or loss is counted (2 scenarios).

Because every leg is repriced together, a hedge leg lowers the worst case automatically; there is
no structure-specific logic. This is the standard SPAN algorithm (CME's published methodology,
which NSE Clearing follows).

Net option value: the scan loss of a basket cannot exceed what its options are worth, and a debit
basket has already paid for that value through the premium margin. SPAN therefore credits a
positive net option value against the scan loss, so a debit spread's margin is about its net debit
rather than the debit plus the same amount again.

What is NOT verified
--------------------
This is an *estimate*. Every constant in ``INDEX_PARAMS`` / ``STOCK_PARAMS`` carries a source note;
the ones marked unverified come from the design doc, not from NSE's current risk-parameter file,
and the netting rule for exposure margin is an assumption. ``MarginBreakdown.validated`` is
therefore always ``False`` until the numbers have been reconciled with a broker's calculator (open
items O-1 to O-4). Never present the result as exact.

Units: premiums, strikes and spot are per share; every margin figure is rupees for the whole basket
(already multiplied by lots x lot size). Volatilities ``iv`` and the volatility scan are in percent
points.
"""

# stdlib
import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

# internal
from tb_utils.greeks import DEFAULT_RISK_FREE_RATE, black_scholes_price
from tb_utils.options.payoff import CE, FUT, Leg, net_premium

INDEX = "INDEX"
STOCK = "STOCK"

# NSE publishes annualised volatility as daily sigma x sqrt(365).
DAYS_PER_YEAR = 365
MPOR_SCALE = math.sqrt(2)  # 2-day margin period of risk
EWMA_LAMBDA = 0.94
MIN_EWMA_RETURNS = 30
_MIN_IV_PCT = 0.5  # a volatility-down scenario never reprices at or below zero vol


@dataclass(frozen=True)
class MarginParams:
    """Margin constants for one instrument class. Each field's comment says where it came from."""

    # Price scan range = max(psr_sigmas x sigma_daily x sqrt(2), psr_floor).
    # NSE Clearing's SPAN page: six standard deviations scaled by sqrt(2), subject to a MINIMUM of
    # 9.3% of the underlying for index products. (The design doc had this as a cap; the NSE page
    # says floor.)
    psr_sigmas: float
    psr_floor: float
    # Volatility scan range, in vol POINTS = max(vsr_fraction x annualised sigma %, vsr_floor_pts).
    vsr_fraction: float
    vsr_floor_pts: float
    # Extreme scenarios: a move of extreme_move x PSR, counting extreme_fraction of the result.
    # The 3x move matches CME's published method. The fraction is 0.35 here (CME uses 0.33);
    # unverified for NSE.
    extreme_move: float
    extreme_fraction: float
    # Exposure margin on net short options
    #   = max(exposure_floor, exposure_sigmas x sigma_daily) x sqrt(2).
    # Design doc A.8, unverified against NSE's current circulars.
    exposure_floor: float
    exposure_sigmas: float
    # Short option minimum, as a fraction of net short notional. Unverified (doc says 5% index; the
    # stock figure may be 7.5%).
    som_pct: float


INDEX_PARAMS = MarginParams(
    psr_sigmas=6.0,
    psr_floor=0.093,
    vsr_fraction=0.25,
    vsr_floor_pts=4.0,
    extreme_move=3.0,
    extreme_fraction=0.35,
    exposure_floor=0.03,
    exposure_sigmas=0.0,
    som_pct=0.05,
)

STOCK_PARAMS = MarginParams(
    psr_sigmas=6.0,
    psr_floor=0.142,
    vsr_fraction=0.25,
    vsr_floor_pts=10.0,
    extreme_move=3.0,
    extreme_fraction=0.35,
    exposure_floor=0.05,
    exposure_sigmas=1.5,
    som_pct=0.075,
)

# Shown to the user beside every estimate. Keep them true: each is a thing this module assumes.
ASSUMPTIONS = (
    "SPAN uses the standard 16 scenarios; the scan ranges and the extreme-move weight are not yet "
    "checked against NSE's current risk-parameter file.",
    "Exposure margin is charged on net short options per expiry and type (a long call covers a "
    "short call), at 3% x sqrt(2) for indices and max(5%, 1.5 sigma) x sqrt(2) for stocks.",
    "Premium margin is the net debit; the premium received on short legs is treated as credited "
    "in the same basket.",
    "A debit basket's SPAN is reduced by the value of the options already paid for, so its margin "
    "is close to its net debit.",
    "Volatility is an EWMA of daily closes (lambda 0.94) annualised with sqrt(365), not NSE's "
    "published figure.",
    "Calendar-spread and cross-margin credits are not modelled; brokers add their own buffer.",
)


def params_for(kind: str) -> MarginParams:
    if kind == INDEX:
        return INDEX_PARAMS
    if kind == STOCK:
        return STOCK_PARAMS
    raise ValueError(f"kind must be {INDEX} or {STOCK}, got {kind!r}")


# ── Volatility ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Sigma:
    """Daily volatility of the underlying's returns, as a fraction (0.009 = 0.9% a day)."""

    daily: float
    source: str  # EWMA_COMPUTED | IV_FALLBACK

    @property
    def annual_pct(self) -> float:
        return self.daily * math.sqrt(DAYS_PER_YEAR) * 100.0


def ewma_daily_vol(closes: Sequence[float], lam: float = EWMA_LAMBDA) -> Optional[float]:
    """EWMA daily volatility from closes in chronological order, or None without enough history.

    RiskMetrics recursion on log returns, seeded with the sample variance of the first
    ``MIN_EWMA_RETURNS`` returns.
    """
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:], strict=False) if a > 0 and b > 0]
    if len(returns) < MIN_EWMA_RETURNS:
        return None
    seed = returns[:MIN_EWMA_RETURNS]
    variance = sum(r * r for r in seed) / len(seed)
    for r in returns[MIN_EWMA_RETURNS:]:
        variance = lam * variance + (1.0 - lam) * r * r
    return math.sqrt(variance)


def sigma_from_iv(iv_pct: float) -> Sigma:
    """Fallback with no price history: the basket's own implied volatility as a daily figure."""
    return Sigma(daily=iv_pct / 100.0 / math.sqrt(DAYS_PER_YEAR), source="IV_FALLBACK")


def price_scan_range(sigma: Sigma, params: MarginParams) -> float:
    """Fraction of spot the scan moves by at 100%."""
    return max(params.psr_sigmas * sigma.daily * MPOR_SCALE, params.psr_floor)


def vol_scan_points(sigma: Sigma, params: MarginParams) -> float:
    """Vol points the volatility scan moves each option's IV by."""
    return max(params.vsr_fraction * sigma.annual_pct, params.vsr_floor_pts)


# ── Scenarios ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scenario:
    price_frac: float  # of the price scan range
    vol_dir: int  # +1 up, -1 down, 0 unchanged
    weight: float  # share of the gain or loss that counts


def span_scenarios(params: MarginParams) -> list[Scenario]:
    """The 16 SPAN scenarios, in the conventional order."""
    scenarios = [Scenario(0.0, 1, 1.0), Scenario(0.0, -1, 1.0)]
    for step in (1 / 3, 2 / 3, 1.0):
        for sign in (1, -1):
            for vol in (1, -1):
                scenarios.append(Scenario(sign * step, vol, 1.0))
    scenarios.append(Scenario(params.extreme_move, 0, params.extreme_fraction))
    scenarios.append(Scenario(-params.extreme_move, 0, params.extreme_fraction))
    return scenarios


def _intrinsic(leg: Leg, spot: float) -> float:
    return max(spot - leg.strike, 0.0) if leg.option_type == CE else max(leg.strike - spot, 0.0)


def _leg_iv(leg: Leg) -> float:
    if leg.iv is None or leg.iv <= 0:
        raise ValueError(
            f"margin needs an implied volatility on every leg ({leg.option_type} {leg.strike})"
        )
    return leg.iv


def _value(leg: Leg, spot: float, days: float, iv: float, rate: float) -> float:
    if days <= 0:
        return _intrinsic(leg, spot)
    price = black_scholes_price(spot, leg.strike, days, iv, leg.option_type, rate)
    return _intrinsic(leg, spot) if price is None else price


@dataclass(frozen=True)
class ScanResult:
    worst_loss: float  # rupees, >= 0
    worst_scenario: int  # 1-based, as in the SPAN risk array
    pnl_by_scenario: tuple[float, ...]
    net_option_value: (
        float  # model value of the basket today: positive for a net long (debit) basket
    )


# pylint: disable=too-many-locals  # the scenario loop reads best as one pass
def scan_risk(
    legs: Sequence[Leg],
    spot: float,
    sigma: Sigma,
    kind: str,
    entry_date: dt.date,
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> ScanResult:
    """Largest one-day loss of the whole basket across the 16 scenarios, in rupees."""
    if not legs:
        raise ValueError("at least one leg is required")
    if any(leg.option_type == FUT for leg in legs):
        raise ValueError("futures legs are not supported by the margin estimate")

    params = params_for(kind)
    psr = price_scan_range(sigma, params)
    vsr = vol_scan_points(sigma, params)

    base = []
    for leg in legs:
        days = (leg.expiry - entry_date).days
        iv = _leg_iv(leg)
        base.append((leg, days, iv, _value(leg, spot, days, iv, rate)))

    net_option_value = sum(leg.direction * leg.lots * leg.lot_size * v0 for leg, _, _, v0 in base)

    pnls = []
    for sc in span_scenarios(params):
        moved = spot * (1.0 + sc.price_frac * psr)
        total = 0.0
        for leg, days, iv, v0 in base:
            shocked_iv = max(iv + sc.vol_dir * vsr, _MIN_IV_PCT)
            v1 = _value(leg, moved, max(days - 1, 0), shocked_iv, rate)
            total += leg.direction * leg.lots * leg.lot_size * (v1 - v0)
        pnls.append(total * sc.weight)

    worst = min(range(len(pnls)), key=pnls.__getitem__)
    return ScanResult(
        worst_loss=max(0.0, -pnls[worst]),
        worst_scenario=worst + 1,
        pnl_by_scenario=tuple(pnls),
        net_option_value=net_option_value,
    )


# ── Exposure, short option minimum, premium ──────────────────────────────────


def net_short_shares(legs: Sequence[Leg]) -> float:
    """Shares short after a long leg of the same expiry and option type covers a short one.

    Strike is deliberately ignored: a long 1860 call caps the loss of a short 1840 call, which is
    the defined-risk hedge relief. Assumed, not verified (open item O-1).
    """
    groups: dict[tuple[dt.date, str], float] = {}
    lot_size = legs[0].lot_size
    for leg in legs:
        key = (leg.expiry, leg.option_type)
        groups[key] = groups.get(key, 0.0) - leg.direction * leg.lots
    return sum(max(0.0, net) for net in groups.values()) * lot_size


def exposure_margin(legs: Sequence[Leg], spot: float, sigma: Sigma, kind: str) -> float:
    params = params_for(kind)
    pct = max(params.exposure_floor, params.exposure_sigmas * sigma.daily) * MPOR_SCALE
    return net_short_shares(legs) * spot * pct


def short_option_minimum(legs: Sequence[Leg], spot: float, kind: str) -> float:
    return net_short_shares(legs) * spot * params_for(kind).som_pct


def premium_margin(legs: Sequence[Leg]) -> float:
    """Net debit paid at entry. A net credit needs none."""
    return max(0.0, -net_premium(legs))


# ── Total ────────────────────────────────────────────────────────────────────


# pylint: disable=too-many-instance-attributes  # one flat record the API returns as-is
@dataclass(frozen=True)
class MarginBreakdown:
    span: float
    exposure: float
    premium: float
    short_option_min: float
    total: float
    standalone: float  # the same legs each priced alone
    spread_benefit: float
    sigma_source: str
    price_scan_pct: float
    vol_scan_points: float
    worst_scenario: Optional[int]  # None when there is no short leg to scan
    validated: bool = False


def _margin_of(
    legs: Sequence[Leg], spot: float, sigma: Sigma, kind: str, entry_date: dt.date, rate: float
):
    """(span, exposure, premium, som, worst_scenario) for one set of legs."""
    if all(leg.direction > 0 for leg in legs):
        # Long-only: the premium is the whole risk; no SPAN, no exposure.
        return 0.0, 0.0, premium_margin(legs), 0.0, None
    scan = scan_risk(legs, spot, sigma, kind, entry_date, rate)
    som = short_option_minimum(legs, spot, kind)
    credited = max(0.0, scan.net_option_value)  # value already paid for through the premium
    return (
        max(scan.worst_loss - credited, som),
        exposure_margin(legs, spot, sigma, kind),
        premium_margin(legs),
        som,
        scan.worst_scenario,
    )


def estimate_margin(
    legs: Sequence[Leg],
    spot: float,
    sigma: Sigma,
    kind: str,
    entry_date: dt.date,
    rate: float = DEFAULT_RISK_FREE_RATE,
) -> MarginBreakdown:
    """Estimated margin for a basket: SPAN + exposure + premium, and the benefit of netting legs.

    ``entry_date`` is when the basket would be opened (today), not a T+n date.
    """
    span, exposure, premium, som, worst = _margin_of(legs, spot, sigma, kind, entry_date, rate)
    total = span + exposure + premium

    standalone = 0.0
    for leg in legs:
        s, e, p, _, _ = _margin_of([leg], spot, sigma, kind, entry_date, rate)
        standalone += s + e + p

    params = params_for(kind)
    return MarginBreakdown(
        span=span,
        exposure=exposure,
        premium=premium,
        short_option_min=som,
        total=total,
        standalone=standalone,
        spread_benefit=max(0.0, standalone - total),
        sigma_source=sigma.source,
        price_scan_pct=price_scan_range(sigma, params) * 100.0,
        vol_scan_points=vol_scan_points(sigma, params),
        worst_scenario=worst,
    )
