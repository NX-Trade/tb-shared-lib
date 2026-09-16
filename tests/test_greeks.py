"""Unit tests for Black-Scholes Greeks calculator and IV utilities."""

from tb_utils import calculate_greeks, calculate_iv_percentile, calculate_iv_rank


def test_atm_call_greeks():
    """Test ATM Call option Greeks."""
    greeks = calculate_greeks(
        spot=25000.0,
        strike=25000.0,
        tte_days=10.0,
        iv_pct=15.0,
        rate=0.0675,
        option_type="CE",
    )

    assert greeks["delta"] is not None
    assert 0.48 <= greeks["delta"] <= 0.58  # ATM Call delta ~0.50
    assert greeks["gamma"] is not None and greeks["gamma"] > 0.0
    assert greeks["theta"] is not None and greeks["theta"] < 0.0  # Time decay is negative
    assert greeks["vega"] is not None and greeks["vega"] > 0.0


def test_atm_put_greeks():
    """Test ATM Put option Greeks."""
    greeks = calculate_greeks(
        spot=25000.0,
        strike=25000.0,
        tte_days=10.0,
        iv_pct=15.0,
        rate=0.0675,
        option_type="PE",
    )

    assert greeks["delta"] is not None
    assert -0.55 <= greeks["delta"] <= -0.42  # ATM Put delta ~ -0.50
    assert greeks["gamma"] is not None and greeks["gamma"] > 0.0
    assert greeks["theta"] is not None  # Put theta


def test_deep_itm_call_greeks():
    """Test Deep ITM Call option delta near +1.0."""
    greeks = calculate_greeks(
        spot=26000.0,
        strike=22000.0,
        tte_days=10.0,
        iv_pct=15.0,
        option_type="CE",
    )

    assert greeks["delta"] is not None
    assert greeks["delta"] > 0.95


def test_invalid_greeks_inputs():
    """Test invalid or zero inputs return None."""
    g1 = calculate_greeks(spot=0.0, strike=100.0, tte_days=10.0, iv_pct=15.0)
    assert g1["delta"] is None

    g2 = calculate_greeks(spot=100.0, strike=100.0, tte_days=0.0, iv_pct=15.0)
    assert g2["delta"] is None

    g3 = calculate_greeks(spot=100.0, strike=100.0, tte_days=10.0, iv_pct=0.0)
    assert g3["delta"] is None


def test_iv_rank():
    """Test IV Rank calculation."""
    iv_history = [10.0 + i * 0.5 for i in range(20)]  # 10.0 to 19.5
    rank_mid = calculate_iv_rank(15.0, iv_history)
    assert rank_mid is not None
    assert 50.0 <= rank_mid <= 55.0

    rank_high = calculate_iv_rank(19.5, iv_history)
    assert rank_high == 100.0

    rank_low = calculate_iv_rank(10.0, iv_history)
    assert rank_low == 0.0


def test_iv_percentile():
    """Test IV Percentile calculation."""
    iv_history = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0, 28.0]
    p_50 = calculate_iv_percentile(19.0, iv_history)
    assert p_50 == 50.0
