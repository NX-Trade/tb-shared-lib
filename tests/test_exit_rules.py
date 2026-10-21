# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.exit_rules — what exit percentages are measured against."""

import datetime as dt
import math

import pytest

from tb_utils.options.exit_rules import EXPIRY_MAX, T_PLUS_N, exit_basis, is_vertical
from tb_utils.options.payoff import Leg

EXPIRY = dt.date(2026, 10, 28)
AS_OF = dt.date(2026, 10, 13)  # 15 days to expiry
LOT = 600
IV = 24.5


def _leg(action, option_type, strike, premium, lots=1, iv=IV):
    return Leg(action, option_type, strike, premium, lots, LOT, EXPIRY, iv)


@pytest.fixture
def techm():
    return [
        _leg("BUY", "CE", 1800, 22.40),
        _leg("SELL", "CE", 1840, 11.55, lots=2),
        _leg("BUY", "CE", 1860, 8.15),
    ]


@pytest.fixture
def bull_call_spread():
    return [_leg("BUY", "CE", 1800, 40.0), _leg("SELL", "CE", 1860, 12.0)]


class TestIsVertical:
    def test_two_leg_same_type_opposite_sides(self, bull_call_spread):
        assert is_vertical(bull_call_spread)

    def test_butterfly_is_not(self, techm):
        assert not is_vertical(techm)

    def test_straddle_is_not(self):
        assert not is_vertical([_leg("SELL", "CE", 1800, 30.0), _leg("SELL", "PE", 1800, 28.0)])

    def test_ratio_spread_is_not(self):
        assert not is_vertical(
            [_leg("BUY", "CE", 1800, 40.0), _leg("SELL", "CE", 1860, 12.0, lots=2)]
        )

    def test_same_direction_is_not(self):
        assert not is_vertical([_leg("BUY", "CE", 1800, 40.0), _leg("BUY", "CE", 1860, 12.0)])


class TestVerticalBasis:
    def test_profit_basis_is_expiry_max(self, bull_call_spread):
        basis = exit_basis(bull_call_spread, 1820.0, AS_OF)
        # width 60 - net debit 28 = 32/share
        assert basis.profit == pytest.approx(32.0 * LOT)
        assert basis.loss == pytest.approx(28.0 * LOT)
        assert basis.profit_source == EXPIRY_MAX


class TestButterflyBasis:
    def test_expiry_maximum_is_still_reported(self, techm):
        basis = exit_basis(techm, 1840.0, AS_OF)
        assert basis.max_profit_at_expiry == pytest.approx(19_530.0)
        assert basis.max_loss_at_expiry == pytest.approx(4_470.0)

    def test_profit_basis_is_reachable_t_plus_n_not_expiry_max(self, techm):
        basis = exit_basis(techm, 1840.0, AS_OF)
        assert basis.profit_source == T_PLUS_N
        # A 75% target on the expiry maximum is unreachable with 15 days left; the T+n
        # reference is well below it, which is the whole point of measuring against T+n.
        assert 0 < basis.profit < 0.75 * basis.max_profit_at_expiry

    def test_profit_basis_grows_toward_expiry(self, techm):
        early = exit_basis(techm, 1840.0, dt.date(2026, 10, 13)).profit
        late = exit_basis(techm, 1840.0, dt.date(2026, 10, 27)).profit
        assert late > early

    def test_credit_structure_has_a_stable_nonzero_basis_at_entry(self):
        # Priced at fair value on entry, a condor's T+n profit *today* is ~0; the halfway
        # reference date keeps the basis meaningful instead of firing on a few rupees.
        condor = [
            _leg("BUY", "PE", 23800, 43.07, iv=15.0),
            _leg("BUY", "CE", 25400, 68.05, iv=15.0),
            _leg("SELL", "PE", 24200, 118.91, iv=15.0),
            _leg("SELL", "CE", 25000, 163.56, iv=15.0),
        ]
        basis = exit_basis(condor, 24600.0, AS_OF)
        assert basis.profit_source == T_PLUS_N
        assert basis.profit is not None
        assert 0.05 * basis.max_profit_at_expiry < basis.profit < basis.max_profit_at_expiry

    def test_loss_basis_is_expiry_max_loss(self, techm):
        assert exit_basis(techm, 1840.0, AS_OF).loss == pytest.approx(4_470.0)

    def test_missing_iv_falls_back_to_expiry_max(self):
        legs = [
            _leg("BUY", "CE", 1800, 22.40, iv=None),
            _leg("SELL", "CE", 1840, 11.55, lots=2, iv=None),
            _leg("BUY", "CE", 1860, 8.15, iv=None),
        ]
        basis = exit_basis(legs, 1840.0, AS_OF)
        assert basis.profit_source == EXPIRY_MAX
        assert basis.profit == pytest.approx(19_530.0)


class TestUnboundedAndDegenerate:
    def test_naked_short_call_has_no_loss_basis(self):
        basis = exit_basis([_leg("SELL", "CE", 1800, 30.0)], 1800.0, AS_OF)
        assert basis.loss is None
        assert math.isinf(basis.max_loss_at_expiry)
        # Best case today is just under the full premium kept (the option is not yet worthless).
        assert 0.9 * 30.0 * LOT < basis.profit <= 30.0 * LOT

    def test_single_long_call_is_priced_on_t_plus_n(self):
        # Not a vertical, so profit is measured on the T+n curve and stays finite.
        basis = exit_basis([_leg("BUY", "CE", 1800, 30.0)], 1800.0, AS_OF)
        assert basis.profit_source == T_PLUS_N
        assert basis.profit is not None and basis.profit > 0
        assert basis.loss == pytest.approx(30.0 * LOT)
