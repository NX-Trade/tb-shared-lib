"""Black-Scholes Option Greeks Calculator.

Provides exact analytical Option Greeks (Delta, Gamma, Theta, Vega) using the
Black-Scholes-Merton (BSM) formula, as well as IV Rank and IV Percentile utilities.
"""

import math
from collections.abc import Sequence
from typing import Optional

try:
    from scipy.stats import norm
except ImportError:

    class _NormFallback:
        @staticmethod
        def cdf(x: float) -> float:
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

        @staticmethod
        def pdf(x: float) -> float:
            return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    norm = _NormFallback()

# Standard risk-free rate for Indian markets (RBI 91-day T-Bill rate ~6.75%)
DEFAULT_RISK_FREE_RATE = 0.0675


def calculate_greeks(
    spot: float,
    strike: float,
    tte_days: float,
    iv_pct: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
    option_type: str = "CE",
) -> dict[str, Optional[float]]:
    """Calculate Black-Scholes Option Greeks for a single contract.

    Args:
        spot: Current underlying spot price (must be > 0).
        strike: Option strike price (must be > 0).
        tte_days: Time to expiration in calendar days (must be > 0).
        iv_pct: Implied volatility in percentage (e.g., 22.5 for 22.5%).
        rate: Annual risk-free interest rate (default: 0.0675).
        option_type: "CE" for Call or "PE" for Put.

    Returns:
        dict: {
            "delta": float or None,
            "gamma": float or None,
            "theta": float or None,
            "vega": float or None,
        }
    """
    if spot <= 0 or strike <= 0 or tte_days <= 0 or iv_pct <= 0:
        return {"delta": None, "gamma": None, "theta": None, "vega": None}

    try:
        T = tte_days / 365.0
        sigma = iv_pct / 100.0

        d1 = (math.log(spot / strike) + (rate + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        n_d1 = norm.pdf(d1)

        # Gamma (identical for Call and Put)
        gamma = n_d1 / (spot * sigma * math.sqrt(T))

        # Vega (sensitivity per 1% change in IV, identical for Call and Put)
        vega = (spot * n_d1 * math.sqrt(T)) / 100.0

        opt_type_upper = option_type.upper()
        if opt_type_upper == "CE":
            delta = norm.cdf(d1)
            # Daily Theta for Call
            theta = (
                -(spot * n_d1 * sigma) / (2 * math.sqrt(T))
                - rate * strike * math.exp(-rate * T) * norm.cdf(d2)
            ) / 365.0
        elif opt_type_upper == "PE":
            delta = norm.cdf(d1) - 1.0
            # Daily Theta for Put
            theta = (
                -(spot * n_d1 * sigma) / (2 * math.sqrt(T))
                + rate * strike * math.exp(-rate * T) * norm.cdf(-d2)
            ) / 365.0
        else:
            return {"delta": None, "gamma": None, "theta": None, "vega": None}

        return {
            "delta": round(float(delta), 6),
            "gamma": round(float(gamma), 6),
            "theta": round(float(theta), 6),
            "vega": round(float(vega), 6),
        }

    except (ValueError, ZeroDivisionError, OverflowError):
        return {"delta": None, "gamma": None, "theta": None, "vega": None}


def calculate_iv_rank(current_iv: float, iv_series: Sequence[float]) -> Optional[float]:
    """Calculate IV Rank relative to historical IV series over a period (e.g. 252 days).

    Formula: IV Rank = (Current IV - Min IV) / (Max IV - Min IV) * 100

    Args:
        current_iv: Today's ATM implied volatility.
        iv_series: Historical series of ATM implied volatilities.

    Returns:
        float (0.0 to 100.0) or None if insufficient history.
    """
    if not iv_series or len(iv_series) < 10:
        return None

    min_iv = min(iv_series)
    max_iv = max(iv_series)

    if max_iv <= min_iv:
        return 50.0  # Constant IV range

    rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100.0
    return round(max(0.0, min(100.0, rank)), 2)


def calculate_iv_percentile(current_iv: float, iv_series: Sequence[float]) -> Optional[float]:
    """Calculate IV Percentile (percentage of historical days where IV was lower than current IV).

    Args:
        current_iv: Today's ATM implied volatility.
        iv_series: Historical series of ATM implied volatilities.

    Returns:
        float (0.0 to 100.0) or None if insufficient history.
    """
    if not iv_series or len(iv_series) < 10:
        return None

    count_below = sum(1 for iv in iv_series if iv < current_iv)
    percentile = (count_below / len(iv_series)) * 100.0
    return round(percentile, 2)
