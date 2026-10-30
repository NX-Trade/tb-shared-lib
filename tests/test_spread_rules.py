"""Each rule fails on its own, with a code a calibration report can count."""

import datetime as dt

from tb_utils.options import spread_rules as rules
from tb_utils.options.ideas import Quote
from tb_utils.options.payoff import Leg
from tb_utils.options.spread_policy import HIGH_VOL, LOW_VOL, TRANSITIONAL, SpreadPolicy
from tb_utils.options.spread_rules import vertical_rule_breach

P = SpreadPolicy()


def quote(**kw):
    base = {
        "expiry": dt.date(2026, 11, 26), "strike": 1000.0, "option_type": "CE",
        "bid": 10.00, "ask": 10.05, "ltp": 10.0, "open_interest": 20_000, "volume": 50_000,
        "iv": 30.0, "tick": 0.05,
    }  # fmt: skip
    return Quote(**{**base, **kw})


def code(result):
    return result.code if result else None


def test_a_liquid_tight_quote_passes():
    assert rules.check_leg_liquidity(quote(), P) is None


def test_open_interest_floor_is_inclusive():
    assert code(rules.check_leg_liquidity(quote(open_interest=4_999), P)) == "LOW_OI"
    assert rules.check_leg_liquidity(quote(open_interest=5_000), P) is None


def test_volume_floor_is_inclusive():
    assert code(rules.check_leg_liquidity(quote(volume=9_999), P)) == "LOW_VOLUME"
    assert rules.check_leg_liquidity(quote(volume=10_000), P) is None


def test_a_missing_side_is_not_priced_blind():
    assert code(rules.check_leg_liquidity(quote(bid=None), P)) == "NO_QUOTE"
    assert code(rules.check_leg_liquidity(quote(ask=0.0), P)) == "NO_QUOTE"
    assert code(rules.check_leg_liquidity(quote(iv=None), P)) == "NO_QUOTE"


def test_wide_percentage_spread_is_rejected():
    assert code(rules.check_leg_liquidity(quote(bid=10.0, ask=10.5), P)) == "WIDE_SPREAD"


def test_one_tick_is_always_allowed_on_a_cheap_contract():
    """A 5-paise spread on a ~₹2 option is 2.5 %, but it is one tick: it cannot be tighter."""
    cheap = quote(bid=1.95, ask=2.00, tick=0.05)
    assert rules.check_leg_liquidity(cheap, P) is None


def test_the_tick_allowance_uses_the_contracts_own_tick():
    """On a 1-paisa-tick contract the same 5-paise spread is five ticks wide, so it fails."""
    finer = quote(bid=1.95, ask=2.00, tick=0.01)
    assert code(rules.check_leg_liquidity(finer, P)) == "WIDE_SPREAD"


def test_bid_ask_limit_is_the_larger_of_percent_and_ticks():
    assert rules.bid_ask_limit(mid=100.0, tick=0.05, policy=P) == 1.5
    assert rules.bid_ask_limit(mid=2.0, tick=0.05, policy=P) == 0.05


def test_reward_risk_floor_depends_on_the_regime():
    assert code(rules.check_reward_risk(2.4, LOW_VOL, P)) == "LOW_REWARD_RISK"
    assert rules.check_reward_risk(2.5, LOW_VOL, P) is None
    # The transitional band asks for conviction: 1:3.0.
    assert code(rules.check_reward_risk(2.9, TRANSITIONAL, P)) == "LOW_REWARD_RISK"
    assert rules.check_reward_risk(3.0, TRANSITIONAL, P) is None


def test_pop_floor_differs_for_debit_and_credit():
    assert code(rules.check_pop(0.29, "DEBIT", P)) == "LOW_POP"
    assert rules.check_pop(0.30, "DEBIT", P) is None
    assert code(rules.check_pop(0.64, "CREDIT", P)) == "LOW_POP"
    assert rules.check_pop(0.65, "CREDIT", P) is None


def test_credit_must_be_a_quarter_of_the_width():
    assert code(rules.check_credit(credit=2.4, width=10.0, policy=P)) == "LOW_CREDIT"
    assert rules.check_credit(credit=2.5, width=10.0, policy=P) is None


def test_the_regime_constant_for_high_vol_is_exported():
    assert HIGH_VOL


# ── A hand-built vertical, checked against the same rules ────────────────────────────────────────

_EXP = dt.date(2026, 11, 26)


def _leg(action, option_type, strike, premium, lots=1):
    return Leg(action, option_type, strike, premium, lots, 100, _EXP)


class TestVerticalRuleBreach:
    def test_an_at_the_money_debit_spread_near_one_to_one_breaks_the_reward_risk_rule(self):
        legs = [
            _leg("BUY", "CE", 1000, 50.0),
            _leg("SELL", "CE", 1050, 25.0),
        ]  # pays 25 for 25: 1:1
        breach = vertical_rule_breach(legs)
        assert breach is not None and breach.code == "LOW_REWARD_RISK"

    def test_a_cheap_debit_spread_passes(self):
        legs = [
            _leg("BUY", "CE", 1020, 30.0),
            _leg("SELL", "CE", 1100, 10.0),
        ]  # pays 20 for 60: 1:3
        assert vertical_rule_breach(legs) is None

    def test_a_thin_credit_spread_breaks_the_credit_rule(self):
        legs = [
            _leg("BUY", "PE", 940, 8.0),
            _leg("SELL", "PE", 980, 12.0),
        ]  # collects 4 on a 40 width: 10%
        breach = vertical_rule_breach(legs)
        assert breach is not None and breach.code == "LOW_CREDIT"

    def test_a_rich_credit_spread_passes(self):
        legs = [
            _leg("BUY", "PE", 940, 5.0),
            _leg("SELL", "PE", 980, 17.0),
        ]  # collects 12 on 40: 30%
        assert vertical_rule_breach(legs) is None

    def test_baskets_that_are_not_verticals_are_left_alone(self):
        fly = [
            _leg("BUY", "CE", 1000, 50.0),
            _leg("SELL", "CE", 1050, 25.0, lots=2),
            _leg("BUY", "CE", 1100, 10.0),
        ]
        straddle = [_leg("BUY", "CE", 1000, 50.0), _leg("BUY", "PE", 1000, 45.0)]
        mixed_lots = [_leg("BUY", "CE", 1000, 50.0), _leg("SELL", "CE", 1050, 25.0, lots=2)]
        same_strike = [_leg("BUY", "CE", 1000, 50.0), _leg("SELL", "CE", 1000, 50.0)]
        for basket in (fly, straddle, mixed_lots, same_strike, [_leg("BUY", "CE", 1000, 50.0)]):
            assert vertical_rule_breach(basket) is None

    def test_the_order_of_the_legs_does_not_matter(self):
        legs = [_leg("SELL", "CE", 1050, 25.0), _leg("BUY", "CE", 1000, 50.0)]
        assert vertical_rule_breach(legs).code == "LOW_REWARD_RISK"
