# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.probability — exact POP and EV against independent checks."""

import datetime as dt
import math

import numpy as np
import pytest

from tb_utils.greeks import DEFAULT_RISK_FREE_RATE, black_scholes_price
from tb_utils.options.payoff import Leg, payoff_at_expiry
from tb_utils.options.probability import (
    analyze_probability,
    density,
    density_curve,
    expected_value,
    probability_of_profit,
    terminal_distribution,
    view_tilt,
)

EXPIRY = dt.date(2026, 11, 26)
SPOT = 1000.0
IV = 25.0
DAYS = 30.0
LOT = 100


def _leg(action, option_type, strike, premium, lots=1):
    return Leg(action, option_type, strike, premium, lots, LOT, EXPIRY, IV)


def _fair(option_type, strike):
    return round(float(black_scholes_price(SPOT, strike, DAYS, IV, option_type)), 6)


@pytest.fixture
def market():
    return terminal_distribution(SPOT, IV, DAYS)


@pytest.fixture
def butterfly():
    """TechM-shaped 1x2x1 call butterfly around the money, priced fairly."""
    return [
        _leg("BUY", "CE", 960, _fair("CE", 960)),
        _leg("SELL", "CE", 1000, _fair("CE", 1000), lots=2),
        _leg("BUY", "CE", 1040, _fair("CE", 1040)),
    ]


def _grid_expectation(legs, dist, fn):
    """Independent numerical integral of ``fn(payoff) × density`` over a fine price grid."""
    xs = np.linspace(1.0, SPOT * 3.0, 20_001)
    pdf = np.array([density(dist, x) for x in xs])
    payoff = np.array([payoff_at_expiry(legs, x) for x in xs])
    return float(np.trapezoid(fn(payoff) * pdf, xs))


class TestDistribution:
    def test_market_mean_is_the_forward(self, market):
        forward = SPOT * math.exp(DEFAULT_RISK_FREE_RATE * DAYS / 365.0)
        assert market.mean == pytest.approx(forward)

    def test_density_integrates_to_one(self, market):
        xs = np.linspace(1.0, SPOT * 3.0, 20_001)
        total = float(np.trapezoid([density(market, x) for x in xs], xs))
        assert total == pytest.approx(1.0, abs=1e-4)

    def test_tilt_shifts_the_mean_log_return(self):
        base = terminal_distribution(SPOT, IV, DAYS)
        tilted = terminal_distribution(SPOT, IV, DAYS, tilt=0.05)
        assert tilted.mu - base.mu == pytest.approx(0.05)
        assert tilted.sigma_t == base.sigma_t

    def test_longer_horizon_is_wider(self):
        assert (
            terminal_distribution(SPOT, IV, 60).sigma_t
            > terminal_distribution(SPOT, IV, 30).sigma_t
        )

    @pytest.mark.parametrize("kwargs", [{"spot": 0, "iv_pct": 20}, {"spot": 100, "iv_pct": 0}])
    def test_rejects_non_positive_inputs(self, kwargs):
        with pytest.raises(ValueError):
            terminal_distribution(days=30, **kwargs)

    def test_density_is_zero_for_non_positive_price(self, market):
        assert density(market, 0) == 0.0 and density(market, -5) == 0.0

    def test_density_curve_pairs_each_spot(self, market):
        curve = density_curve(market, [900.0, 1000.0, 1100.0])
        assert [s for s, _ in curve] == [900.0, 1000.0, 1100.0]
        assert curve[1][1] > curve[0][1]


class TestExpectedValue:
    def test_fair_long_call_has_ev_of_its_carry_only(self, market):
        """Under the market measure a fairly priced option earns the risk-free carry, no more."""
        premium = _fair("CE", 1000)
        legs = [_leg("BUY", "CE", 1000, premium)]
        carry = premium * (math.exp(DEFAULT_RISK_FREE_RATE * DAYS / 365.0) - 1.0) * LOT
        assert expected_value(legs, market) == pytest.approx(carry, rel=1e-4)

    def test_fair_short_put_mirrors_the_carry(self, market):
        premium = _fair("PE", 950)
        legs = [_leg("SELL", "PE", 950, premium)]
        carry = -premium * (math.exp(DEFAULT_RISK_FREE_RATE * DAYS / 365.0) - 1.0) * LOT
        assert expected_value(legs, market) == pytest.approx(carry, rel=1e-4)

    def test_matches_numerical_integration_for_a_butterfly(self, butterfly, market):
        exact = expected_value(butterfly, market)
        numeric = _grid_expectation(butterfly, market, lambda p: p)
        assert exact == pytest.approx(numeric, abs=0.5)

    def test_crossing_the_spread_makes_a_market_ev_negative(self):
        """Pay the ask / receive the bid and the market EV is minus the half-spreads."""
        fair_long, fair_short = _fair("CE", 1000), _fair("CE", 1040)
        legs = [
            _leg("BUY", "CE", 1000, fair_long + 0.25),
            _leg("SELL", "CE", 1040, fair_short - 0.25),
        ]
        market = terminal_distribution(SPOT, IV, DAYS)
        carry = (
            (fair_long - fair_short) * (math.exp(DEFAULT_RISK_FREE_RATE * DAYS / 365.0) - 1) * LOT
        )
        assert expected_value(legs, market) == pytest.approx(carry - 0.5 * LOT, rel=1e-3)

    def test_costs_are_subtracted(self, butterfly, market):
        assert expected_value(butterfly, market, costs=250.0) == pytest.approx(
            expected_value(butterfly, market) - 250.0
        )

    def test_expiry_today_uses_the_known_price(self):
        dist = terminal_distribution(SPOT, IV, 0)
        legs = [_leg("BUY", "CE", 900, 10.0)]
        assert expected_value(legs, dist) == pytest.approx((SPOT - 900 - 10.0) * LOT)


class TestProbabilityOfProfit:
    def test_long_call_pop_is_the_chance_of_clearing_its_breakeven(self, market):
        premium = 20.0
        legs = [_leg("BUY", "CE", 1000, premium)]
        breakeven = 1000 + premium
        expected = 1.0 - 0.5 * (
            1.0 + math.erf((math.log(breakeven) - market.mu) / market.sigma_t / math.sqrt(2))
        )
        assert probability_of_profit(legs, market) == pytest.approx(expected)

    def test_matches_numerical_integration_for_a_butterfly(self, butterfly, market):
        exact = probability_of_profit(butterfly, market)
        numeric = _grid_expectation(butterfly, market, lambda p: (p > 0).astype(float))
        assert exact == pytest.approx(numeric, abs=2e-3)

    def test_far_otm_credit_spread_wins_most_of_the_time(self, market):
        legs = [_leg("SELL", "PE", 850, 4.0), _leg("BUY", "PE", 800, 1.5)]
        assert probability_of_profit(legs, market) > 0.9

    def test_butterfly_wins_far_less_often_than_a_credit_spread(self, butterfly, market):
        assert probability_of_profit(butterfly, market) < 0.5

    def test_short_straddle_pop_is_between_zero_and_one(self, market):
        legs = [_leg("SELL", "CE", 1000, 30.0), _leg("SELL", "PE", 1000, 28.0)]
        assert 0.0 < probability_of_profit(legs, market) < 1.0

    def test_expiry_today_is_certain_either_way(self):
        dist = terminal_distribution(SPOT, IV, 0)
        assert probability_of_profit([_leg("BUY", "CE", 900, 10.0)], dist) == 1.0
        assert probability_of_profit([_leg("BUY", "CE", 1100, 10.0)], dist) == 0.0


class TestViewTilt:
    def test_tilt_is_conviction_times_log_target(self):
        assert view_tilt(1000, 1100, 0.5) == pytest.approx(0.5 * math.log(1.1))

    def test_zero_conviction_is_the_market(self):
        assert view_tilt(1000, 1100, 0.0) == 0.0

    @pytest.mark.parametrize(
        "args", [(0, 1100, 0.5), (1000, 0, 0.5), (1000, 1100, 1.5), (1000, 1100, -0.1)]
    )
    def test_rejects_bad_inputs(self, args):
        with pytest.raises(ValueError):
            view_tilt(*args)

    def test_bullish_view_helps_a_bull_call_spread_and_hurts_a_bear_put_spread(self):
        bull = [_leg("BUY", "CE", 1000, 25.0), _leg("SELL", "CE", 1040, 10.0)]
        bear = [_leg("BUY", "PE", 1000, 25.0), _leg("SELL", "PE", 960, 10.0)]
        neutral = analyze_probability(bull, SPOT, IV, DAYS)
        tilt = view_tilt(SPOT, 1060, 0.8)
        up = analyze_probability(bull, SPOT, IV, DAYS, tilt=tilt)
        assert up.expected_value > neutral.expected_value and up.pop > neutral.pop
        assert (
            analyze_probability(bear, SPOT, IV, DAYS, tilt=tilt).expected_value
            < analyze_probability(bear, SPOT, IV, DAYS).expected_value
        )

    def test_more_conviction_raises_ev_monotonically(self):
        bull = [_leg("BUY", "CE", 1000, 25.0), _leg("SELL", "CE", 1040, 10.0)]
        evs = [
            analyze_probability(bull, SPOT, IV, DAYS, tilt=view_tilt(SPOT, 1060, c)).expected_value
            for c in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        assert evs == sorted(evs)


class TestAnalyzeProbability:
    def test_reports_the_one_sigma_range_around_the_median(self):
        result = analyze_probability([_leg("BUY", "CE", 1000, 20.0)], SPOT, IV, DAYS)
        sigma_t = (IV / 100.0) * math.sqrt(DAYS / 365.0)
        assert result.one_sigma_high / result.one_sigma_low == pytest.approx(math.exp(2 * sigma_t))
        assert result.one_sigma_low < SPOT < result.one_sigma_high
        assert result.sigma_pct == IV and result.days == DAYS

    def test_negative_days_are_clamped(self):
        assert analyze_probability([_leg("BUY", "CE", 900, 5.0)], SPOT, IV, -3).days == 0.0
