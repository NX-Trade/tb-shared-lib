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


class GreeksResult(dict):
    """Dictionary subclass supporting attribute-style access for Greeks.

    Supports both dictionary access (greeks['delta'], greeks.get('delta'))
    and attribute access (greeks.delta, greeks.theta).
    """

    def __getattr__(self, name: str) -> Optional[float]:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'GreeksResult' object has no attribute '{name}'") from None

    def __setattr__(self, name: str, value: Optional[float]) -> None:
        self[name] = value


def calculate_greeks(
    spot: float,
    strike: float,
    tte_days: Optional[float] = None,
    iv_pct: Optional[float] = None,
    rate: float = DEFAULT_RISK_FREE_RATE,
    option_type: str = "CE",
    *,
    dte_days: Optional[float] = None,
    iv: Optional[float] = None,
) -> GreeksResult:
    """Calculate Black-Scholes Option Greeks for a single contract.

    Args:
        spot: Current underlying spot price (must be > 0).
        strike: Option strike price (must be > 0).
        tte_days: Time to expiration in calendar days (must be > 0).
            Can also be supplied via keyword alias `dte_days`.
        iv_pct: Implied volatility in percentage (e.g., 22.5 for 22.5%).
            Can also be supplied via keyword alias `iv`.
        rate: Annual risk-free interest rate (default: 0.0675).
        option_type: "CE" for Call or "PE" for Put.
        dte_days: Keyword alias for `tte_days`.
        iv: Keyword alias for `iv_pct`.

    Returns:
        GreeksResult (dict): {
            "delta": float or None,
            "gamma": float or None,
            "theta": float or None,
            "vega": float or None,
        }
    """
    if tte_days is None:
        tte_days = dte_days
    if iv_pct is None:
        iv_pct = iv

    if any(val is None or val <= 0 for val in (spot, strike, tte_days, iv_pct)):
        return GreeksResult({"delta": None, "gamma": None, "theta": None, "vega": None})

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
            return GreeksResult({"delta": None, "gamma": None, "theta": None, "vega": None})

        return GreeksResult(
            {
                "delta": round(float(delta), 6),
                "gamma": round(float(gamma), 6),
                "theta": round(float(theta), 6),
                "vega": round(float(vega), 6),
            }
        )

    except (ValueError, ZeroDivisionError, OverflowError):
        return GreeksResult({"delta": None, "gamma": None, "theta": None, "vega": None})


def black_scholes_price(
    spot: float,
    strike: float,
    tte_days: float,
    iv_pct: float,
    option_type: str,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> Optional[float]:
    """Black-Scholes fair value of a European option.

    Args:
        spot: Underlying price.
        strike: Strike price.
        tte_days: Calendar days to expiry.
        iv_pct: Implied volatility in percent (e.g. 22.5).
        option_type: ``"CE"``/``"CALL"`` or ``"PE"``/``"PUT"``.
        risk_free_rate: Annualised rate as a fraction.

    Returns:
        Theoretical premium, or ``None`` when an input is unusable.
    """
    if any(v is None or v <= 0 for v in (spot, strike, tte_days, iv_pct)):
        return None
    try:
        sigma = iv_pct / 100.0
        t = tte_days / 365.0
        d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * sigma**2) * t) / (
            sigma * math.sqrt(t)
        )
        d2 = d1 - sigma * math.sqrt(t)
        discount = math.exp(-risk_free_rate * t)
        if option_type.upper() in ("CE", "CALL", "C"):
            return spot * norm.cdf(d1) - strike * discount * norm.cdf(d2)
        return strike * discount * norm.cdf(-d2) - spot * norm.cdf(-d1)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def implied_volatility(
    option_price: float,
    spot: float,
    strike: float,
    tte_days: float,
    option_type: str,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    max_iterations: int = 100,
    tolerance: float = 1e-5,
) -> Optional[float]:
    """Invert Black-Scholes to recover implied volatility from a premium.

    Needed because the NSE F&O bhavcopy publishes settlement prices but no IV,
    so historical ATM IV — and therefore IV rank — has to be solved for rather
    than read. Uses bisection on [0.01 %, 1000 %]: slower than Newton but it
    cannot diverge, which matters when processing tens of thousands of
    contracts a day unattended.

    Args:
        option_price: Observed premium (settlement or close).
        spot: Underlying price.
        strike: Strike price.
        tte_days: Calendar days to expiry.
        option_type: ``"CE"``/``"CALL"`` or ``"PE"``/``"PUT"``.
        risk_free_rate: Annualised rate as a fraction.
        max_iterations: Bisection iteration cap.
        tolerance: Absolute price tolerance for convergence.

    Returns:
        Implied volatility in percent, or ``None`` when the price is outside
        the no-arbitrage bounds or the solve does not converge. Returning
        ``None`` rather than a boundary value keeps un-inverted contracts out
        of an IV series instead of pinning it to 1 % or 1000 %.
    """
    if any(v is None or v <= 0 for v in (option_price, spot, strike, tte_days)):
        return None

    t = tte_days / 365.0
    discount = math.exp(-risk_free_rate * t)
    if option_type.upper() in ("CE", "CALL", "C"):
        intrinsic = max(0.0, spot - strike * discount)
    else:
        intrinsic = max(0.0, strike * discount - spot)

    low, high = 0.01, 1000.0
    price_low = black_scholes_price(spot, strike, tte_days, low, option_type, risk_free_rate)
    price_high = black_scholes_price(spot, strike, tte_days, high, option_type, risk_free_rate)

    # Unsolvable in one check: below intrinsic there is no volatility that
    # reprices the option (deep ITM contracts settling at intrinsic are the
    # usual cause), and outside the bracket bisection has no root to find.
    unsolvable = (
        option_price < intrinsic - tolerance
        or price_low is None
        or price_high is None
        or not price_low <= option_price <= price_high
    )
    if unsolvable:
        return None

    for _ in range(max_iterations):
        mid = 0.5 * (low + high)
        price = black_scholes_price(spot, strike, tte_days, mid, option_type, risk_free_rate)
        if price is None:
            return None
        if abs(price - option_price) < tolerance:
            return round(mid, 4)
        if price < option_price:
            low = mid
        else:
            high = mid

    return None


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
