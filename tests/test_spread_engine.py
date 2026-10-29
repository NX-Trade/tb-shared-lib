"""The spread engine: a fresh chain in, one defined-risk vertical (or a reasoned skip) out."""

import dataclasses
import datetime as dt
import inspect
import math
from pathlib import Path

import pytest

from tb_utils.greeks import black_scholes_price
from tb_utils.options import spread_engine as engine
from tb_utils.options.ideas import ChainData, Quote
from tb_utils.options.spread_engine import (
    FreshChain,
    StaleChainError,
    build_vertical_spread,
)
from tb_utils.options.spread_policy import HIGH_VOL, LOW_VOL, SpreadPolicy
from tb_utils.time import IST

NOW = dt.datetime(2026, 10, 29, 10, 30, tzinfo=IST)
EXPIRY = dt.date(2026, 11, 26)
SPOT = 1000.0
LOT = 500

# Rules that are not under test are opened wide so a test exercises one behaviour at a time.
RELAXED = SpreadPolicy(
    min_reward_risk=0.0, transitional_min_reward_risk=0.0, min_pop_debit=0.0,
    min_pop_credit=0.0, min_credit_pct_of_width=0.0,
)  # fmt: skip


def _tte_days(expiry: dt.date) -> float:
    close = dt.datetime.combine(expiry, dt.time(15, 30), tzinfo=IST)
    return (close - NOW).total_seconds() / 86400.0


def _quote(expiry, strike, kind, iv, oi, volume, tick=0.05):
    price = black_scholes_price(SPOT, strike, _tte_days(expiry), iv, kind)
    if price is None or price < 0.5:
        return None
    # A tight market: one tick wide. Wider quotes are a liquidity problem, tested separately.
    bid = math.floor(price / tick) * tick
    ask = bid + tick
    return Quote(
        expiry, float(strike), kind, round(bid, 2), round(ask, 2), round(price, 2),
        oi, volume, iv, tick,
    )  # fmt: skip


def make_chain(iv=15.0, expiries=(EXPIRY,), oi=20_000, volume=50_000, ts=NOW, step=10):
    quotes = []
    for expiry in expiries:
        for strike in range(700, 1301, step):
            for kind in ("CE", "PE"):
                q = _quote(expiry, strike, kind, iv, oi, volume)
                if q:
                    quotes.append(q)
    return ChainData("TESTCO", ts, SPOT, LOT, False, quotes)


def fresh(chain=None, requested_at=NOW):
    return FreshChain(chain or make_chain(), requested_at)


# ── Freshness contract ───────────────────────────────────────────────────────


def test_a_chain_older_than_the_request_cannot_be_wrapped():
    stale = make_chain(ts=NOW - dt.timedelta(minutes=1))
    with pytest.raises(StaleChainError):
        FreshChain(stale, requested_at=NOW)


def test_a_chain_stored_at_or_after_the_request_is_accepted():
    assert FreshChain(make_chain(ts=NOW), requested_at=NOW).chain.ts == NOW
    later = FreshChain(make_chain(ts=NOW + dt.timedelta(seconds=3)), requested_at=NOW)
    assert later.chain.ts > NOW


def test_the_engine_takes_no_cached_chain_and_no_io():
    source = Path(engine.__file__).read_text(encoding="utf-8")
    assert "get_cached_option_chain" not in source
    for banned in ("redis", "sqlalchemy", "requests", "httpx"):
        assert banned not in source.lower().replace("redis_", ""), banned


def test_the_signature_needs_no_target_price():
    names = list(inspect.signature(build_vertical_spread).parameters)
    assert names == ["fresh", "action", "now", "policy"]


# ── Direction and regime pick the structure ──────────────────────────────────


@pytest.mark.parametrize(
    ("iv", "action", "structure", "family", "kind", "regime"),
    [
        (15.0, "BUY", "bull_call_spread", "DEBIT", "CE", LOW_VOL),
        (15.0, "SELL", "bear_put_spread", "DEBIT", "PE", LOW_VOL),
        (30.0, "BUY", "bull_put_spread", "CREDIT", "PE", HIGH_VOL),
        (30.0, "SELL", "bear_call_spread", "CREDIT", "CE", HIGH_VOL),
    ],
)
def test_structure_follows_direction_and_volatility(iv, action, structure, family, kind, regime):
    result = build_vertical_spread(fresh(make_chain(iv=iv)), action, NOW, RELAXED)
    assert result.skip is None, result.skip
    spread = result.spread
    assert (spread.structure, spread.family, spread.regime) == (structure, family, regime)
    assert {leg.option_type for leg in spread.legs} == {kind}
    assert result.regime == regime and result.straddle_pct is not None


def test_an_unknown_action_is_skipped():
    result = build_vertical_spread(fresh(), "HOLD", NOW, RELAXED)
    assert result.spread is None and result.skip.code == "BAD_ACTION"


# ── Legs, pricing and sequencing ─────────────────────────────────────────────


def test_bought_leg_comes_first_and_is_priced_at_the_ask_and_bid():
    spread = build_vertical_spread(fresh(), "BUY", NOW, RELAXED).spread
    first, second = spread.legs
    assert (first.action, second.action) == ("BUY", "SELL")  # hedge before short, always
    assert first.premium == first.ask and first.premium_basis == "ask"
    assert second.premium == second.bid and second.premium_basis == "bid"
    assert first.lots == second.lots == 1
    assert spread.lot_size == LOT


def test_a_debit_is_negative_rupees_for_the_whole_position():
    spread = build_vertical_spread(fresh(), "BUY", NOW, RELAXED).spread
    long_leg, short_leg = spread.legs
    expected = -(long_leg.premium - short_leg.premium) * LOT
    assert spread.net_premium == pytest.approx(expected, abs=0.01)
    assert spread.net_premium < 0
    assert spread.max_loss == pytest.approx(-spread.net_premium, abs=0.01)  # a debit is the risk


def test_a_credit_is_positive_and_max_profit_is_the_credit():
    spread = build_vertical_spread(fresh(make_chain(iv=30.0)), "BUY", NOW, RELAXED).spread
    assert spread.family == "CREDIT" and spread.net_premium > 0
    assert spread.max_profit == pytest.approx(spread.net_premium, abs=0.01)
    assert spread.max_loss == pytest.approx(spread.width * LOT - spread.net_premium, abs=0.01)


def test_strikes_are_ordered_correctly_for_each_structure():
    cases = {
        ("BUY", 15.0): lambda bought, sold: sold > bought,  # bull call: sell the higher call
        ("SELL", 15.0): lambda bought, sold: sold < bought,  # bear put: sell the lower put
        ("BUY", 30.0): lambda bought, sold: sold > bought,  # bull put: sell the higher put
        ("SELL", 30.0): lambda bought, sold: sold < bought,  # bear call: sell the lower call
    }
    for (action, iv), ok in cases.items():
        legs = build_vertical_spread(fresh(make_chain(iv=iv)), action, NOW, RELAXED).spread.legs
        bought = next(leg.strike for leg in legs if leg.action == "BUY")
        sold = next(leg.strike for leg in legs if leg.action == "SELL")
        assert ok(bought, sold), (action, iv, bought, sold)


def test_deltas_land_inside_the_policy_bands():
    p = RELAXED
    spread = build_vertical_spread(fresh(), "BUY", NOW, p).spread
    long_leg, short_leg = spread.legs
    assert p.debit_long_delta[0] <= abs(long_leg.delta) <= p.debit_long_delta[1]
    assert p.debit_short_delta[0] <= abs(short_leg.delta) <= p.debit_short_delta[1]


def test_the_best_debit_spread_is_the_one_with_the_least_rupee_risk():
    result = build_vertical_spread(fresh(), "BUY", NOW, RELAXED)
    assert len(result.alternatives) >= 1
    assert result.spread == result.alternatives[0]
    risks = [s.max_loss for s in result.alternatives]
    assert risks == sorted(risks)


def test_the_best_credit_spread_is_the_one_with_the_highest_credit_yield():
    result = build_vertical_spread(fresh(make_chain(iv=30.0)), "BUY", NOW, RELAXED)
    yields = [s.net_premium / (s.width * LOT) for s in result.alternatives]
    assert yields == sorted(yields, reverse=True)


# ── Filters ──────────────────────────────────────────────────────────────────


def test_illiquid_strikes_are_purged_before_any_candidate_is_built():
    result = build_vertical_spread(fresh(make_chain(oi=100)), "BUY", NOW, RELAXED)
    assert result.spread is None and result.skip.code == "NO_LIQUID_STRIKES"
    assert {r.code for r in result.rejections} == {"LOW_OI"}


def test_a_candidate_failing_reward_risk_is_rejected_with_a_code():
    strict = dataclasses.replace(RELAXED, min_reward_risk=50.0)
    result = build_vertical_spread(fresh(), "BUY", NOW, strict)
    assert result.spread is None and result.skip.code == "ALL_REJECTED"
    assert "LOW_REWARD_RISK" in {r.code for r in result.rejections}


def test_pop_is_computed_and_can_reject():
    spread = build_vertical_spread(fresh(), "BUY", NOW, RELAXED).spread
    assert 0.0 < spread.pop < 1.0
    strict = dataclasses.replace(RELAXED, min_pop_debit=0.99)
    result = build_vertical_spread(fresh(), "BUY", NOW, strict)
    assert result.spread is None and "LOW_POP" in {r.code for r in result.rejections}


def test_default_policy_applies_every_spec_rule():
    """Whatever the default policy lets through must satisfy every spec number."""
    result = build_vertical_spread(fresh(), "BUY", NOW)
    if result.spread is not None:
        assert result.spread.reward_risk >= 2.5 and result.spread.pop >= 0.30
    else:
        assert result.skip.code in {"ALL_REJECTED", "NO_CANDIDATE"}


# ── Expiry (physical-settlement protection) ──────────────────────────────────


def test_an_expiry_under_four_days_away_is_skipped_for_the_next_one():
    near, far = NOW.date() + dt.timedelta(days=2), EXPIRY
    result = build_vertical_spread(fresh(make_chain(expiries=(near, far))), "BUY", NOW, RELAXED)
    assert result.spread.expiry == far and result.spread.dte >= 4


def test_only_a_near_expiry_means_no_trade():
    near = NOW.date() + dt.timedelta(days=3)
    result = build_vertical_spread(fresh(make_chain(expiries=(near,))), "BUY", NOW, RELAXED)
    assert result.spread is None and result.skip.code == "NO_EXPIRY"


def test_an_empty_chain_is_a_skip_not_a_crash():
    empty = ChainData("TESTCO", NOW, SPOT, LOT, False, [])
    result = build_vertical_spread(FreshChain(empty, NOW), "BUY", NOW, RELAXED)
    assert result.spread is None and result.skip.code == "NO_CHAIN"
