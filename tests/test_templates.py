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
    resolve_butterfly_by_premium,
    resolve_credit_vertical_by_premium,
    resolve_template,
    shape_of,
)

EXPIRY = dt.date(2026, 11, 26)
SPOT = 1000.0
STRIKES = [float(k) for k in range(800, 1201, 20)]  # step 20, ATM = 1000 at index 10
ALL_KEYS = [t.key for t in list_templates()]


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
    def test_loss_is_capped(self, key):
        template = get_template(key)
        extremes = max_profit_loss(_priced(_resolve(key, target=_target_for(template))))
        assert template.defined_risk and math.isfinite(extremes.max_loss.value)

    def test_every_short_leg_is_covered_by_a_long_of_the_same_type(self, key):
        """The structural reason the loss is capped, independent of any price: per option type,
        the lots bought are at least the lots sold."""
        for option_type in ("CE", "PE"):
            legs = [leg for leg in get_template(key).legs if leg.option_type == option_type]
            bought = sum(leg.lots for leg in legs if leg.action == "BUY")
            sold = sum(leg.lots for leg in legs if leg.action == "SELL")
            assert bought >= sold, (key, option_type)

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
            return  # neutral structures are not meant to carry a one-sided payoff
        legs = _priced(_resolve(key, target=_target_for(template)))
        up = [payoff_at_expiry(legs, SPOT + step) for step in range(0, 81, 10)]
        down = [payoff_at_expiry(legs, SPOT - step) for step in range(0, 81, 10)]
        if template.bias == BULLISH:
            assert sum(up) >= sum(down)
        else:
            assert sum(down) >= sum(up)


class TestUndefinedRiskIsNotOffered:
    @pytest.mark.parametrize(
        "key", ["short_straddle", "short_strangle", "call_ratio_spread", "put_ratio_spread"]
    )
    def test_an_uncovered_structure_is_not_in_the_registry(self, key):
        assert key not in ALL_KEYS
        with pytest.raises(TemplateError, match="unknown template"):
            get_template(key)

    def test_every_registered_template_is_flagged_defined_risk(self):
        assert all(t.defined_risk for t in list_templates())


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


class TestButterflyByPremium:
    """The sold strike costs 40-50% of the first buy, the far wing at most 30%."""

    STRIKES = [24000.0 + 50 * i for i in range(0, 13)]  # 24000 .. 24600
    # Call premiums falling away from the money, roughly the 5 Nov Nifty chain.
    CALLS = dict(zip(STRIKES, [140, 123, 107, 91, 76, 64, 54, 45, 38, 31, 26, 21, 17], strict=True))

    def resolve(self, premiums=None, **kw):
        template = get_template("call_butterfly")
        return resolve_butterfly_by_premium(
            template, self.STRIKES, premiums or self.CALLS, 24050.0, 1, **kw
        )

    def test_the_sold_strike_is_forty_to_fifty_percent_of_the_first_buy(self):
        first, body, _ = self.resolve(target=24100.0)
        ratio = self.CALLS[body.strike] / self.CALLS[first.strike]
        assert 0.40 <= ratio <= 0.50

    def test_the_far_wing_is_at_most_thirty_percent(self):
        first, _, wing = self.resolve(target=24100.0)
        assert self.CALLS[wing.strike] / self.CALLS[first.strike] <= 0.30

    def test_it_is_still_one_two_one_with_capped_loss(self):
        legs = self.resolve(target=24100.0)
        assert [(leg.action, leg.lots) for leg in legs] == [("BUY", 1), ("SELL", 2), ("BUY", 1)]
        priced = [
            Leg(g.action, g.option_type, g.strike, self.CALLS[g.strike], g.lots, 65, EXPIRY)
            for g in legs
        ]
        assert math.isfinite(max_profit_loss(priced).max_loss.value)

    def test_strikes_are_further_out_than_the_equal_step_placement(self):
        by_steps = resolve_template(
            get_template("call_butterfly"), self.STRIKES, 24050.0, 1, 24100.0
        )
        by_premium = self.resolve(target=24100.0)
        assert by_premium[1].strike > by_steps[1].strike

    def test_a_put_butterfly_mirrors_it_downwards(self):
        puts = dict(zip(reversed(self.STRIKES), self.CALLS.values(), strict=True))
        legs = resolve_butterfly_by_premium(
            get_template("put_butterfly"), self.STRIKES, puts, 24550.0, 1, 24500.0
        )
        first, body, wing = legs
        assert wing.strike < body.strike < first.strike
        assert 0.40 <= puts[body.strike] / puts[first.strike] <= 0.50

    def test_no_strike_in_the_band_is_an_error_not_a_drift(self):
        first = self.resolve(target=24100.0)[0]
        base = self.CALLS[first.strike]
        sparse = {s: p for s, p in self.CALLS.items() if not 0.40 <= p / base <= 0.50}
        with pytest.raises(TemplateError, match="40%-50%"):
            self.resolve(sparse, target=24100.0)

    def test_other_templates_are_refused(self):
        with pytest.raises(TemplateError, match="not a 1:2:1"):
            resolve_butterfly_by_premium(
                get_template("bull_call_spread"), self.STRIKES, self.CALLS, 24050.0
            )


class TestCreditVerticalByPremium:
    """The sold strike stays near the money; the hedge costs at most 30% of it."""

    STRIKES = [float(k) for k in range(23000, 24401, 50)]
    # Put premiums rising with the strike, dearer near the money (about 3 up to about 100).
    PUTS = {strike: round(3 * 1.13**i, 2) for i, strike in enumerate(STRIKES)}

    def resolve(self, key="bull_put_spread", premiums=None, spot=24100.0):
        return resolve_credit_vertical_by_premium(
            get_template(key), self.STRIKES, premiums or self.PUTS, spot, 1
        )

    def test_the_hedge_costs_at_most_thirty_percent_of_the_sold_put(self):
        sold, hedge = self.resolve()
        assert (sold.action, hedge.action) == ("SELL", "BUY")
        assert self.PUTS[hedge.strike] <= 0.30 * self.PUTS[sold.strike]

    def test_the_hedge_is_the_dearest_strike_that_still_qualifies(self):
        sold, hedge = self.resolve()
        nearer = [s for s in self.STRIKES if hedge.strike < s < sold.strike]
        assert nearer and all(self.PUTS[s] > 0.30 * self.PUTS[sold.strike] for s in nearer)

    def test_it_is_further_from_the_short_than_the_equal_step_placement(self):
        sold, hedge = self.resolve()
        by_steps = resolve_template(get_template("bull_put_spread"), self.STRIKES, 24100.0, 1)
        assert sold.strike - hedge.strike > by_steps[0].strike - by_steps[1].strike

    def test_no_cheap_enough_strike_is_an_error(self):
        dear = {s: 100.0 for s in self.STRIKES}
        with pytest.raises(TemplateError, match="30%"):
            self.resolve(premiums=dear)

    def test_a_bear_call_spread_mirrors_it_upwards(self):
        calls = dict(zip(self.STRIKES, reversed(list(self.PUTS.values())), strict=True))
        sold, hedge = self.resolve("bear_call_spread", calls, spot=23200.0)
        assert hedge.strike > sold.strike
        assert calls[hedge.strike] <= 0.30 * calls[sold.strike]
