"""The spread policy carries every number from the strategy spec, and the regime gate follows it."""

import dataclasses

import pytest

from tb_utils.options.spread_policy import (
    HIGH_VOL,
    LOW_VOL,
    TRANSITIONAL,
    SpreadPolicy,
    classify_regime,
)


def test_defaults_are_the_spec_numbers():
    p = SpreadPolicy()
    assert (p.min_open_interest, p.min_volume) == (5_000, 10_000)
    assert p.max_bid_ask_pct == 0.015 and p.bid_ask_floor_ticks == 1
    assert p.min_dte == 4
    assert (p.low_vol_max_straddle_pct, p.high_vol_min_straddle_pct) == (5.5, 6.0)
    assert p.debit_long_delta == (0.35, 0.45) and p.debit_short_delta == (0.15, 0.20)
    assert p.credit_short_delta == (0.30, 0.40) and p.credit_long_delta == (0.15, 0.20)
    assert (p.min_reward_risk, p.transitional_min_reward_risk) == (2.5, 3.0)
    assert (p.min_pop_debit, p.min_pop_credit) == (0.30, 0.65)
    assert p.min_credit_pct_of_width == 0.25


def test_the_policy_cannot_be_mutated_in_place():
    with pytest.raises(dataclasses.FrozenInstanceError):
        SpreadPolicy().min_dte = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("straddle_pct", "regime"),
    [
        (0.0, LOW_VOL),
        (5.5, LOW_VOL),  # the spec's boundary belongs to the low band: "<= 5.5 %"
        (5.51, TRANSITIONAL),
        (6.0, TRANSITIONAL),  # "5.5 % - 6.0 %" is transitional
        (6.01, HIGH_VOL),
        (12.0, HIGH_VOL),
    ],
)
def test_classify_regime_follows_the_straddle_bands(straddle_pct, regime):
    assert classify_regime(straddle_pct, SpreadPolicy()) == regime


def test_classify_regime_uses_the_policy_not_constants():
    policy = SpreadPolicy(low_vol_max_straddle_pct=3.0, high_vol_min_straddle_pct=4.0)
    assert classify_regime(3.5, policy) == TRANSITIONAL
    assert classify_regime(4.5, policy) == HIGH_VOL


def test_the_two_calibrated_defaults():
    """Added after the real-chain survey: widened delta reach and a tenor-normalised regime."""
    p = SpreadPolicy()
    assert p.delta_tolerance == 0.07
    assert p.regime_reference_days == 30.0


def test_classify_regime_is_unchanged_by_the_new_fields():
    legacy = SpreadPolicy(delta_tolerance=0.0, regime_reference_days=None)
    assert classify_regime(5.5, legacy) == LOW_VOL
