"""Every number of the option-spread strategy spec, in one frozen place, plus the volatility gate.

Pure data and one pure function. The thresholds are *starting values from the spec*, meant to be
calibrated against recorded skips and outcomes, so nothing else in the engine hard-codes them: a
rule reads its limit from the :class:`SpreadPolicy` it is handed.

Spec: ``tb-ai-brain/strategies/options_spread_and_basket_strategies.md`` §2 (liquidity), §3
(regimes), §4 (vertical spreads).
"""

from dataclasses import dataclass
from typing import Optional

# Volatility regimes, from the ATM straddle as a share of the underlying (spec §3).
LOW_VOL = "LOW_NORMAL"  # options are cheap: buy a debit spread
TRANSITIONAL = "TRANSITIONAL"  # fairly priced: debit, but only with a better payoff
HIGH_VOL = "HIGH"  # premium is rich: sell a credit spread


@dataclass(frozen=True)
class SpreadPolicy:  # pylint: disable=too-many-instance-attributes
    """Limits a vertical spread must satisfy. Defaults are the spec's numbers."""

    # §2 liquidity: every leg, individually.
    min_open_interest: int = 5_000
    min_volume: int = 10_000
    max_bid_ask_pct: float = 0.015  # of the mid price ...
    bid_ask_floor_ticks: int = 1  # ... but never tighter than this many ticks (see spread_rules)

    # §2 expiry: under this many calendar days to expiry, use the next month's contracts.
    min_dte: int = 4

    # §3 regimes: ATM straddle value as a percentage of spot.
    low_vol_max_straddle_pct: float = 5.5
    high_vol_min_straddle_pct: float = 6.0
    # The straddle shrinks with the square root of the time left, so the same market reads "high"
    # early in the month and "low" near expiry. The bands above are applied to the straddle scaled
    # to this many days; None compares the raw straddle (the original wording of the spec).
    regime_reference_days: Optional[float] = 30.0

    # How far outside a delta band a strike may sit and still be considered. Added after a survey of
    # 211 real chains: about half had no strike inside the hard bands. Candidates inside the ideal
    # band always rank first; this only widens the pool. 0 restores the hard bands.
    delta_tolerance: float = 0.07

    # §4.1 debit vertical: absolute delta bands of the bought and the sold leg.
    debit_long_delta: tuple[float, float] = (0.35, 0.45)
    debit_short_delta: tuple[float, float] = (0.15, 0.20)
    min_reward_risk: float = 2.5
    transitional_min_reward_risk: float = 3.0
    min_pop_debit: float = 0.30

    # §4.2 credit vertical.
    credit_short_delta: tuple[float, float] = (0.30, 0.40)
    credit_long_delta: tuple[float, float] = (0.15, 0.20)
    min_credit_pct_of_width: float = 0.25
    min_pop_credit: float = 0.65


def classify_regime(straddle_pct: float, policy: SpreadPolicy) -> str:
    """The volatility regime for an ATM straddle of ``straddle_pct`` % of spot.

    Boundaries follow the spec's wording: ``<= 5.5`` is low, ``> 6.0`` is high, and the band
    between them (6.0 included) is transitional.
    """
    if straddle_pct <= policy.low_vol_max_straddle_pct:
        return LOW_VOL
    if straddle_pct > policy.high_vol_min_straddle_pct:
        return HIGH_VOL
    return TRANSITIONAL
