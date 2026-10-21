# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.payoff.

Acceptance fixture is the TechM broken-wing butterfly from the design doc (§10, App. A):
BUY 1×1800 CE @22.40, SELL 2×1840 CE @11.55, BUY 1×1860 CE @8.15, lot size 600.
"""

import datetime as dt
import math

import pytest

from tb_utils.options.payoff import (
    Leg,
    breakevens,
    default_spot_range,
    max_profit_loss,
    net_greeks,
    net_premium,
    net_premium_per_share,
    payoff_at_date,
    payoff_at_expiry,
    payoff_curve,
)

EXPIRY = dt.date(2026, 10, 28)
LOT = 600
IV = 24.5


def _leg(action, option_type, strike, premium, lots=1, lot_size=LOT, iv=None, expiry=EXPIRY):
    return Leg(action, option_type, strike, premium, lots, lot_size, expiry, iv)


@pytest.fixture
def techm():
    return [
        _leg("BUY", "CE", 1800, 22.40, iv=IV),
        _leg("SELL", "CE", 1840, 11.55, lots=2, iv=IV),
        _leg("BUY", "CE", 1860, 8.15, iv=IV),
    ]


# ── TechM acceptance fixture ─────────────────────────────────────────────────


class TestTechmButterfly:
    def test_net_premium_is_debit(self, techm):
        assert net_premium_per_share(techm) == pytest.approx(-7.45)
        assert net_premium(techm) == pytest.approx(-4470.0)

    @pytest.mark.parametrize("spot", [1500, 1767, 1800])
    def test_max_loss_flat_below_lower_strike(self, techm, spot):
        assert payoff_at_expiry(techm, spot) == pytest.approx(-4470.0)

    def test_max_profit_at_body(self, techm):
        assert payoff_at_expiry(techm, 1840) == pytest.approx(19530.0)

    @pytest.mark.parametrize("spot", [1860, 2200, 5000])
    def test_broken_wing_residual_above_upper_strike(self, techm, spot):
        assert payoff_at_expiry(techm, spot) == pytest.approx(7530.0)

    def test_exactly_one_breakeven(self, techm):
        assert breakevens(techm) == [pytest.approx(1807.45)]

    def test_extremes_are_bounded_and_located(self, techm):
        ext = max_profit_loss(techm)
        assert ext.max_profit.value == pytest.approx(19530.0)
        assert ext.max_profit.at_spot == 1840
        assert ext.max_loss.value == pytest.approx(-4470.0)
        assert ext.max_loss.at_spot == 1800

    def test_value_at_body_with_15_days_left_is_mostly_terminal(self, techm):
        """App. A.6: ~14.44/share, ~₹4,192, ~21 % of the expiry maximum."""
        as_of = EXPIRY - dt.timedelta(days=15)
        pnl = payoff_at_date(techm, 1840, as_of)
        structure_value_per_share = pnl / LOT + 7.45
        assert structure_value_per_share == pytest.approx(14.44, abs=0.15)
        assert pnl == pytest.approx(4192, abs=100)
        assert pnl / 19530.0 == pytest.approx(0.21, abs=0.01)

    @pytest.mark.parametrize(
        "days_left,expected_per_share",
        [(7, 16.35), (3, 19.30), (1, 24.35)],
    )
    def test_value_rises_toward_expiry(self, techm, days_left, expected_per_share):
        as_of = EXPIRY - dt.timedelta(days=days_left)
        value = payoff_at_date(techm, 1840, as_of) / LOT + 7.45
        assert value == pytest.approx(expected_per_share, abs=0.5)

    def test_at_expiry_date_matches_expiry_payoff(self, techm):
        for spot in (1700, 1807.45, 1840, 1900):
            assert payoff_at_date(techm, spot, EXPIRY) == pytest.approx(
                payoff_at_expiry(techm, spot)
            )

    def test_never_reaches_expiry_max_early(self, techm):
        early = payoff_at_date(techm, 1840, EXPIRY - dt.timedelta(days=15))
        assert early < 0.3 * payoff_at_expiry(techm, 1840)


# ── Other structures ─────────────────────────────────────────────────────────


class TestSingleLongCall:
    legs = [_leg("BUY", "CE", 100, 5.0, lot_size=100)]

    def test_one_breakeven_no_upper(self):
        assert breakevens(self.legs) == [pytest.approx(105.0)]

    def test_loss_bounded_profit_unbounded(self):
        ext = max_profit_loss(self.legs)
        assert ext.max_loss.value == pytest.approx(-500.0)
        assert ext.max_profit.value == math.inf
        assert ext.max_profit.at_spot is None


class TestShortStraddle:
    legs = [_leg("SELL", "CE", 100, 5.0, lot_size=100), _leg("SELL", "PE", 100, 5.0, lot_size=100)]

    def test_two_breakevens(self):
        assert breakevens(self.legs) == [pytest.approx(90.0), pytest.approx(110.0)]

    def test_loss_is_unbounded_not_a_grid_number(self):
        ext = max_profit_loss(self.legs)
        assert ext.max_loss.value == -math.inf
        assert ext.max_profit.value == pytest.approx(1000.0)
        assert ext.max_profit.at_spot == 100


class TestIronCondor:
    # sell 90 PE / 110 CE for 3 each, buy 80 PE / 120 CE for 1 each → credit 4/share
    legs = [
        _leg("BUY", "PE", 80, 1.0, lot_size=100),
        _leg("SELL", "PE", 90, 3.0, lot_size=100),
        _leg("SELL", "CE", 110, 3.0, lot_size=100),
        _leg("BUY", "CE", 120, 1.0, lot_size=100),
    ]

    def test_credit(self):
        assert net_premium_per_share(self.legs) == pytest.approx(4.0)

    def test_breakevens_bracket_the_body(self):
        # A short-body condor crosses zero once on each wing: two breakevens.
        assert breakevens(self.legs) == [pytest.approx(86.0), pytest.approx(114.0)]

    def test_defined_risk_both_sides(self):
        ext = max_profit_loss(self.legs)
        assert ext.max_profit.value == pytest.approx(400.0)
        assert ext.max_loss.value == pytest.approx(-600.0)

    def test_profit_flat_between_short_strikes(self):
        assert payoff_at_expiry(self.legs, 95) == pytest.approx(400.0)
        assert payoff_at_expiry(self.legs, 105) == pytest.approx(400.0)


class TestLongOnlyBasket:
    legs = [_leg("BUY", "CE", 100, 4.0, lot_size=50), _leg("BUY", "PE", 100, 3.0, lot_size=50)]

    def test_max_loss_equals_premium_paid(self):
        assert max_profit_loss(self.legs).max_loss.value == pytest.approx(net_premium(self.legs))
        assert net_premium(self.legs) == pytest.approx(-350.0)


class TestFuturesLeg:
    def test_long_future_is_linear(self):
        legs = [_leg("BUY", "FUT", 100, 0.0, lot_size=10)]
        assert payoff_at_expiry(legs, 110) == pytest.approx(100.0)
        assert payoff_at_expiry(legs, 90) == pytest.approx(-100.0)
        assert breakevens(legs) == [pytest.approx(100.0)]

    def test_covered_call_caps_profit(self):
        legs = [
            _leg("BUY", "FUT", 100, 0.0, lot_size=10),
            _leg("SELL", "CE", 110, 2.0, lot_size=10),
        ]
        ext = max_profit_loss(legs)
        assert ext.max_profit.value == pytest.approx(120.0)
        assert ext.max_loss.value == pytest.approx(-980.0)
        assert ext.max_loss.at_spot == 0.0


class TestVerticalMatchesStrategyBuilderClosedForm:
    """The 2-leg closed form (max_profit = width − debit) must agree with the general scan."""

    def test_bull_call_spread(self):
        legs = [_leg("BUY", "CE", 100, 6.0, lot_size=1), _leg("SELL", "CE", 110, 2.0, lot_size=1)]
        ext = max_profit_loss(legs)
        assert ext.max_profit.value == pytest.approx(10 - 4.0)
        assert ext.max_loss.value == pytest.approx(-4.0)
        assert breakevens(legs) == [pytest.approx(104.0)]


# ── Curve ────────────────────────────────────────────────────────────────────


class TestCurve:
    def test_extends_beyond_outer_strikes_so_tails_are_visible(self, techm):
        lo, hi = default_spot_range(techm, spot=1767)
        assert lo < 1767 < 1800 and hi > 1860
        curve = payoff_curve(techm, lo, hi)
        assert curve[0][1] == pytest.approx(-4470.0)
        assert curve[-1][1] == pytest.approx(7530.0)

    def test_length_and_endpoints(self, techm):
        curve = payoff_curve(techm, 1600, 2000, points=201)
        assert len(curve) == 201
        assert curve[0][0] == 1600 and curve[-1][0] == pytest.approx(2000)

    def test_as_of_curve_differs_from_expiry_curve(self, techm):
        as_of = EXPIRY - dt.timedelta(days=15)
        expiry = dict(payoff_curve(techm, 1700, 1900, points=5))
        t_n = dict(payoff_curve(techm, 1700, 1900, points=5, as_of=as_of))
        assert t_n[1800.0] != pytest.approx(expiry[1800.0])

    def test_rejects_bad_ranges(self, techm):
        with pytest.raises(ValueError):
            payoff_curve(techm, 1900, 1800)
        with pytest.raises(ValueError):
            payoff_curve(techm, 1700, 1900, points=1)


# ── IV shift and greeks ──────────────────────────────────────────────────────


class TestIvShiftAndGreeks:
    def test_iv_up_raises_value_of_long_option(self):
        legs = [_leg("BUY", "CE", 1800, 20.0, iv=IV)]
        as_of = EXPIRY - dt.timedelta(days=15)
        assert payoff_at_date(legs, 1800, as_of, iv_shift=5.0) > payoff_at_date(legs, 1800, as_of)

    def test_long_call_greeks_signs_and_scale(self):
        legs = [_leg("BUY", "CE", 1800, 20.0, iv=IV)]
        g = net_greeks(legs, 1800, EXPIRY - dt.timedelta(days=15))
        assert 0 < g["delta"] < LOT  # share-equivalents, scaled by lot size
        assert g["gamma"] > 0
        assert g["vega"] > 0
        assert g["theta"] < 0

    def test_short_leg_flips_sign(self):
        as_of = EXPIRY - dt.timedelta(days=15)
        long_g = net_greeks([_leg("BUY", "CE", 1800, 20.0, iv=IV)], 1800, as_of)
        short_g = net_greeks([_leg("SELL", "CE", 1800, 20.0, iv=IV)], 1800, as_of)
        for key, long_value in long_g.items():
            assert short_g[key] == pytest.approx(-long_value)

    def test_butterfly_is_near_delta_neutral_at_body(self, techm):
        g = net_greeks(techm, 1840, EXPIRY - dt.timedelta(days=15))
        assert abs(g["delta"]) < 0.25 * LOT

    def test_expired_itm_leg_contributes_intrinsic_delta_only(self):
        legs = [_leg("BUY", "CE", 1800, 20.0, iv=IV)]
        g = net_greeks(legs, 1900, EXPIRY)
        assert g == {"delta": float(LOT), "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    def test_missing_iv_before_expiry_is_an_error_not_a_guess(self):
        legs = [_leg("BUY", "CE", 1800, 20.0)]
        with pytest.raises(ValueError, match="iv"):
            payoff_at_date(legs, 1800, EXPIRY - dt.timedelta(days=15))


# ── Validation ───────────────────────────────────────────────────────────────


class TestValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"action": "HOLD"},
            {"option_type": "XX"},
            {"strike": 0},
            {"premium": -1},
            {"lots": 0},
            {"lot_size": 0},
        ],
    )
    def test_bad_leg_rejected(self, kwargs):
        base = {
            "action": "BUY",
            "option_type": "CE",
            "strike": 100,
            "premium": 1,
            "lots": 1,
            "lot_size": 1,
            "expiry": EXPIRY,
        }
        with pytest.raises(ValueError):
            Leg(**{**base, **kwargs})

    def test_future_with_premium_rejected(self):
        with pytest.raises(ValueError):
            _leg("BUY", "FUT", 100, 1.0)

    def test_empty_basket_rejected(self):
        with pytest.raises(ValueError):
            payoff_at_expiry([], 100)

    def test_mixed_expiries_refused_at_expiry_but_priced_by_date(self):
        legs = [
            _leg("SELL", "CE", 100, 3.0, iv=20.0, expiry=dt.date(2026, 10, 28)),
            _leg("BUY", "CE", 100, 5.0, iv=20.0, expiry=dt.date(2026, 11, 25)),
        ]
        with pytest.raises(ValueError, match="single expiry"):
            payoff_at_expiry(legs, 100)
        assert math.isfinite(payoff_at_date(legs, 100, dt.date(2026, 10, 14)))
