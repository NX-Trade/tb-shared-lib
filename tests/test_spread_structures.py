"""A structure is data: new shapes reuse the engine, and the spec refuses an unsafe leg order."""

import pytest
from test_spread_engine import NOW, RELAXED, fresh, make_chain

from tb_utils.options.spread_engine import build_spread, build_vertical_spread
from tb_utils.options.spread_policy import HIGH_VOL, LOW_VOL, SpreadPolicy
from tb_utils.options.spread_structures import LegSpec, StructureSpec, choose_vertical
from tb_utils.options.spread_types import BUY, CREDIT, DEBIT, SELL

POLICY = SpreadPolicy()


def spec(*legs, key="test", family=DEBIT):
    return StructureSpec(
        key, family, legs, strike_order=lambda strikes: True, rules=(), rank=lambda s: (s.max_loss,)
    )


# ── The spec guards the entry sequence ───────────────────────────────────────


def test_bought_legs_must_come_before_sold_legs():
    """The sold leg earns margin relief only after its hedge is in, so the order is not optional."""
    with pytest.raises(ValueError, match="bought legs must come before sold"):
        spec(LegSpec(SELL, "CE", (0.1, 0.2)), LegSpec(BUY, "CE", (0.3, 0.4)))


def test_a_valid_order_is_accepted():
    assert spec(LegSpec(BUY, "CE", (0.3, 0.4)), LegSpec(SELL, "CE", (0.1, 0.2))).key == "test"


# ── The four verticals are plain data ────────────────────────────────────────


@pytest.mark.parametrize(
    ("action", "regime", "key", "family", "kind"),
    [
        ("BUY", LOW_VOL, "bull_call_spread", DEBIT, "CE"),
        ("SELL", LOW_VOL, "bear_put_spread", DEBIT, "PE"),
        ("BUY", HIGH_VOL, "bull_put_spread", CREDIT, "PE"),
        ("SELL", HIGH_VOL, "bear_call_spread", CREDIT, "CE"),
    ],
)
def test_the_chooser_returns_the_expected_vertical(action, regime, key, family, kind):
    chosen = choose_vertical(action, regime, POLICY)
    assert (chosen.key, chosen.family) == (key, family)
    assert [leg.action for leg in chosen.legs] == [BUY, SELL]
    assert {leg.option_type for leg in chosen.legs} == {kind}


def test_bands_come_from_the_policy_not_the_structure():
    policy = SpreadPolicy(debit_long_delta=(0.1, 0.2), debit_short_delta=(0.05, 0.1))
    bought, sold = choose_vertical("BUY", LOW_VOL, policy).legs
    assert bought.delta_band == (0.1, 0.2) and sold.delta_band == (0.05, 0.1)


def test_the_vertical_wrapper_is_the_engine_with_the_vertical_chooser():
    a = build_vertical_spread(fresh(), "BUY", NOW, RELAXED)
    b = build_spread(fresh(), "BUY", NOW, RELAXED, choose_vertical)
    assert a == b


# ── Reuse: a butterfly is data, not a new engine ─────────────────────────────


def butterfly_chooser(action, regime, policy):  # pylint: disable=unused-argument
    """A long call butterfly: buy both wings, sell two at the body (bought legs listed first)."""
    return StructureSpec(
        key="call_butterfly",
        family=DEBIT,
        legs=(
            LegSpec(BUY, "CE", (0.50, 0.62)),  # lower wing
            LegSpec(BUY, "CE", (0.18, 0.25)),  # upper wing
            LegSpec(SELL, "CE", (0.33, 0.42), lots=2),  # body
        ),
        # strikes arrive in leg order: lower wing, upper wing, body. Body between, wings equal.
        strike_order=lambda k: k[0] < k[2] < k[1] and abs((k[2] - k[0]) - (k[1] - k[2])) < 1e-9,
        rules=(),
        rank=lambda s: (s.max_loss,),
    )


def test_a_three_leg_butterfly_runs_through_the_same_engine():
    result = build_spread(fresh(), "BUY", NOW, RELAXED, butterfly_chooser)
    assert result.skip is None, result.skip
    spread = result.spread
    assert spread.structure == "call_butterfly" and len(spread.legs) == 3
    assert [leg.action for leg in spread.legs] == [BUY, BUY, SELL]  # hedges first
    assert [leg.lots for leg in spread.legs] == [1, 1, 2]
    lower, upper, body = (leg.strike for leg in spread.legs)
    assert lower < body < upper and body - lower == upper - body
    assert 0 < spread.max_loss < float("inf") and spread.max_profit > 0  # defined risk both ways
    assert spread.width == upper - lower


def test_the_butterfly_gets_the_same_filters_and_skips_as_a_vertical():
    illiquid = build_spread(fresh(make_chain(oi=100)), "BUY", NOW, RELAXED, butterfly_chooser)
    assert illiquid.skip.code == "NO_LIQUID_STRIKES"
    near = build_spread(fresh(make_chain(expiries=())), "BUY", NOW, RELAXED, butterfly_chooser)
    assert near.skip.code == "NO_CHAIN"


def test_a_skip_carries_what_was_learned_before_it():
    """Regime and straddle are measured before the legs are screened, and the skip keeps them."""
    result = build_spread(fresh(make_chain(oi=100)), "BUY", NOW, RELAXED, butterfly_chooser)
    assert result.regime == LOW_VOL and result.straddle_pct is not None
    assert {r.code for r in result.rejections} == {"LOW_OI"}
