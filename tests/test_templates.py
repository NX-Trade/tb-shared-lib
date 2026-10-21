# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.templates."""

import datetime as dt
import math

import pytest

from tb_utils.greeks import black_scholes_price
from tb_utils.options.payoff import Leg, max_profit_loss, payoff_at_expiry
from tb_utils.options.templates import (
    BEARISH,
    BULLISH,
    TemplateError,
    get_template,
    list_templates,
    resolve_template,
    shape_of,
)

EXPIRY = dt.date(2026, 11, 26)
SPOT = 1000.0
STRIKES = [float(k) for k in range(800, 1201, 20)]  # step 20, ATM = 1000 at index 10
ALL_KEYS = [t.key for t in list_templates()]
# Not "defined risk" (a short leg is uncovered) yet finite at expiry: spot cannot go below 0.
UNCOVERED_BUT_FINITE = {"put_ratio_spread"}


def _target_for(template):
    if not template.needs_target:
        return None
    return 1040.0 if template.bias == BULLISH else 960.0


def _priced(resolved):
    return [
        Leg(
            r.action,
            r.option_type,
            r.strike,
            round(float(black_scholes_price(SPOT, r.strike, 30, 20.0, r.option_type)), 2),
            r.lots,
            100,
            EXPIRY,
            20.0,
        )
        for r in resolved
    ]


def _resolve(key, width=1, target=None):
    return resolve_template(get_template(key), STRIKES, SPOT, width, target)


class TestRegistry:
    def test_every_template_has_a_shape(self):
        assert all(shape_of(t) for t in list_templates())

    def test_a_bull_and_bear_version_share_a_shape(self):
        assert shape_of(get_template("bull_call_spread")) == shape_of(
            get_template("bear_call_spread")
        )
        assert shape_of(get_template("call_butterfly")) != shape_of(
            get_template("bull_call_spread")
        )

    def test_keys_are_unique(self):
        assert len(ALL_KEYS) == len(set(ALL_KEYS))

    def test_unknown_key_raises(self):
        with pytest.raises(TemplateError):
            get_template("nope")

    def test_filter_by_bias(self):
        assert {t.bias for t in list_templates(BULLISH)} == {BULLISH}

    def test_generator_templates_are_directional_and_defined_risk(self):
        eligible = list_templates(generator_only=True)
        assert eligible
        assert all(t.bias in (BULLISH, BEARISH) and t.defined_risk for t in eligible)

    def test_generator_has_both_biases_for_every_family(self):
        for bias in (BULLISH, BEARISH):
            assert len(list_templates(bias, generator_only=True)) >= 5


@pytest.mark.parametrize("key", ALL_KEYS)
class TestEveryTemplate:
    def test_declared_defined_risk_matches_payoff(self, key):
        template = get_template(key)
        extremes = max_profit_loss(_priced(_resolve(key, target=_target_for(template))))
        bounded = math.isfinite(extremes.max_loss.value)
        if key in UNCOVERED_BUT_FINITE:
            assert bounded and not template.defined_risk
        else:
            assert bounded == template.defined_risk

    def test_generator_templates_have_2_to_4_legs(self, key):
        template = get_template(key)
        if template.generator_eligible:
            assert 2 <= len(template.legs) <= 4

    def test_resolves_to_listed_strikes_only(self, key):
        legs = _resolve(key, target=_target_for(get_template(key)))
        assert {leg.strike for leg in legs} <= set(STRIKES)

    def test_bias_matches_payoff_direction(self, key):
        """Directional generator templates earn more on the side their bias names."""
        template = get_template(key)
        if not template.generator_eligible:
            return  # neutral and ratio structures are not meant to carry a one-sided payoff
        legs = _priced(_resolve(key, target=_target_for(template)))
        up = [payoff_at_expiry(legs, SPOT + step) for step in range(0, 81, 10)]
        down = [payoff_at_expiry(legs, SPOT - step) for step in range(0, 81, 10)]
        if template.bias == BULLISH:
            assert sum(up) >= sum(down)
        else:
            assert sum(down) >= sum(up)


class TestResolution:
    def test_bull_call_spread_atm_and_one_width_up(self):
        legs = _resolve("bull_call_spread", width=2)
        assert [(leg.action, leg.option_type, leg.strike) for leg in legs] == [
            ("BUY", "CE", 1000.0),
            ("SELL", "CE", 1040.0),
        ]

    def test_butterfly_body_snaps_to_nearest_listed_strike_to_target(self):
        legs = _resolve("call_butterfly", target=1033.0)
        body = next(leg for leg in legs if leg.action == "SELL")
        assert body.strike == 1040.0
        assert body.lots == 2
        assert sorted(leg.strike for leg in legs if leg.action == "BUY") == [1020.0, 1060.0]

    def test_butterfly_requires_a_target(self):
        with pytest.raises(TemplateError, match="target"):
            _resolve("call_butterfly")

    def test_iron_fly_without_target_shifts_from_atm(self):
        up = {leg.strike for leg in _resolve("bullish_iron_fly") if leg.action == "SELL"}
        down = {leg.strike for leg in _resolve("bearish_iron_fly") if leg.action == "SELL"}
        assert up == {1020.0}
        assert down == {980.0}

    def test_iron_fly_with_target_uses_it(self):
        legs = _resolve("bullish_iron_fly", target=1100.0)
        assert {leg.strike for leg in legs if leg.action == "SELL"} == {1100.0}

    def test_broken_wing_upper_wing_is_twice_as_far(self):
        legs = _resolve("bullish_broken_wing_butterfly", width=1, target=1000.0)
        strikes = sorted(leg.strike for leg in legs if leg.action == "BUY")
        assert strikes == [980.0, 1040.0]

    def test_strike_outside_listed_range_is_rejected_not_truncated(self):
        with pytest.raises(TemplateError, match="outside"):
            _resolve("bull_call_spread", width=11)

    def test_width_must_be_positive(self):
        with pytest.raises(TemplateError):
            _resolve("bull_call_spread", width=0)

    def test_empty_chain_is_rejected(self):
        with pytest.raises(TemplateError):
            resolve_template(get_template("bull_call_spread"), [], SPOT)

    def test_uneven_strike_spacing_counts_listed_steps(self):
        uneven = [900.0, 950.0, 1000.0, 1100.0, 1300.0]
        legs = resolve_template(get_template("bull_call_spread"), uneven, 1000.0, 1)
        assert [leg.strike for leg in legs] == [1000.0, 1100.0]

    def test_atm_tie_resolves_to_lower_strike(self):
        legs = resolve_template(get_template("long_straddle"), STRIKES, 1010.0)
        assert {leg.strike for leg in legs} == {1000.0}

    def test_duplicate_strikes_in_input_are_ignored(self):
        legs = resolve_template(get_template("bull_call_spread"), STRIKES + STRIKES, SPOT)
        assert [leg.strike for leg in legs] == [1000.0, 1020.0]
