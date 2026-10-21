# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.ideas — the generator over a synthetic, fairly priced chain."""

import datetime as dt
from dataclasses import replace

import pytest

from tb_utils.greeks import black_scholes_price
from tb_utils.options.ideas import (
    ROLE_BALANCED,
    ROLE_CONSERVATIVE,
    ROLE_TARGETED,
    ChainData,
    DirectionalView,
    Idea,
    IdeaConfig,
    Quote,
    _assign_roles,
    _select,
    generate_ideas,
)
from tb_utils.time import IST

SPOT = 1000.0
IV = 25.0
LOT = 100
NOW = dt.datetime(2026, 10, 22, 19, 0, tzinfo=IST)
EXPIRY = dt.date(2026, 11, 26)  # 35 days out
STRIKES = [float(k) for k in range(800, 1201, 20)]
HALF_SPREAD = 0.25


def _quote(strike, option_type, expiry=EXPIRY, *, oi=5000, volume=1000, iv=IV, two_sided=True):
    days = (expiry - NOW.date()).days
    fair = float(black_scholes_price(SPOT, strike, days, IV, option_type))
    mid = max(fair, 0.5)
    return Quote(
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        bid=round(mid - HALF_SPREAD, 2) if two_sided else None,
        ask=round(mid + HALF_SPREAD, 2) if two_sided else None,
        ltp=round(mid, 2),
        open_interest=oi,
        volume=volume,
        iv=iv,
    )


def _chain(quotes=None, ts=NOW - dt.timedelta(hours=3), spot=SPOT):
    quotes = quotes or [_quote(k, t) for k in STRIKES for t in ("CE", "PE")]
    return ChainData("ACME", ts, spot, LOT, False, quotes)


def _view(bias="BULLISH", target=1060.0, conviction=0.7, **kwargs):
    base = {
        "underlying": "ACME",
        "bias": bias,
        "conviction": conviction,
        "horizon_days": 10,
        "entry": SPOT,
        "target": target,
        "stop": 950.0,
        "source": "RESEARCH_CONFLUENCE",
        "as_of": NOW - dt.timedelta(hours=3),
    }
    return DirectionalView(**{**base, **kwargs})


@pytest.fixture
def bullish():
    return generate_ideas(_view(), _chain(), NOW)


@pytest.fixture
def bearish():
    return generate_ideas(_view("BEARISH", 940.0), _chain(), NOW)


class TestIdeasForAView:
    def test_returns_up_to_three_ideas_with_no_skip(self, bullish):
        assert bullish.skip is None
        assert 1 <= len(bullish.ideas) <= 3

    def test_each_idea_is_a_different_shape(self, bullish):
        shapes = [i.shape for i in bullish.ideas]
        assert len(shapes) == len(set(shapes))

    def test_every_idea_has_defined_risk_and_a_positive_expected_value_at_the_view(self, bullish):
        for idea in bullish.ideas:
            assert idea.max_loss > 0 and idea.max_profit > 0
            assert idea.ev_view > 0
            assert 0 < idea.pop_view < 1

    def test_the_view_makes_the_idea_look_better_than_the_market_does(self, bullish):
        """EV at the market is only a cost check; the view is what lifts it."""
        for idea in bullish.ideas:
            assert idea.ev_view > idea.ev_market

    def test_legs_use_listed_strikes_and_pay_the_spread(self, bullish):
        for idea in bullish.ideas:
            for leg in idea.legs:
                assert leg.strike in STRIKES
                assert leg.premium == (leg.ask if leg.action == "BUY" else leg.bid)
                assert leg.premium_basis == ("ask" if leg.action == "BUY" else "bid")

    def test_every_short_leg_is_covered(self, bullish):
        for idea in bullish.ideas:
            longs = sum(l.lots for l in idea.legs if l.action == "BUY")  # noqa: E741
            shorts = sum(l.lots for l in idea.legs if l.action == "SELL")  # noqa: E741
            assert longs >= shorts

    def test_two_to_four_legs(self, bullish):
        assert all(2 <= len(i.legs) <= 4 for i in bullish.ideas)

    def test_roles_are_unique_and_conservative_has_the_best_pop(self, bullish):
        roles = [i.role for i in bullish.ideas]
        assert len(roles) == len(set(roles))
        conservative = next(i for i in bullish.ideas if i.role == ROLE_CONSERVATIVE)
        assert conservative.pop_view == max(i.pop_view for i in bullish.ideas)

    def test_carries_a_curve_a_rationale_and_provenance(self, bullish):
        idea = bullish.ideas[0]
        assert len(idea.curve) == 41 and idea.rationale
        assert idea.sigma_source == "ATM_IV" and idea.sigma_pct == IV
        assert idea.expiry == EXPIRY and idea.dte == 35

    def test_margin_estimate_is_attached(self, bullish):
        assert all(i.margin_estimate is not None and i.margin_estimate > 0 for i in bullish.ideas)

    def test_every_idea_leans_the_way_of_the_view(self, bullish, bearish):
        assert bullish.ideas and all(i.net_delta > 0 for i in bullish.ideas)
        assert bearish.ideas and all(i.net_delta < 0 for i in bearish.ideas)

    def test_is_deterministic(self):
        first = generate_ideas(_view(), _chain(), NOW)
        second = generate_ideas(_view(), _chain(), NOW)
        assert [(i.template, i.score) for i in first.ideas] == [
            (i.template, i.score) for i in second.ideas
        ]

    def test_a_stronger_conviction_lifts_the_expected_value(self):
        weak = generate_ideas(_view(conviction=0.5), _chain(), NOW).ideas
        strong = generate_ideas(_view(conviction=1.0), _chain(), NOW).ideas
        by_template = {i.template: i.ev_view for i in weak}
        shared = [i for i in strong if i.template in by_template]
        assert shared and all(i.ev_view > by_template[i.template] for i in shared)


class TestSkips:
    @pytest.mark.parametrize(
        "view,code",
        [
            (_view("NEUTRAL"), "NO_VIEW"),
            (_view(conviction=0.2), "LOW_CONVICTION"),
            (_view(target=None), "NO_TARGET"),
            (_view(target=950.0), "TARGET_WRONG_SIDE"),
            (_view("BEARISH", 1050.0), "TARGET_WRONG_SIDE"),
        ],
    )
    def test_a_missing_or_unusable_view_gives_no_ideas_and_says_why(self, view, code):
        result = generate_ideas(view, _chain(), NOW)
        assert not result.ideas and result.skip.code == code and result.skip.message

    def test_a_stale_chain_gives_no_ideas(self):
        result = generate_ideas(_view(), _chain(ts=NOW - dt.timedelta(days=3)), NOW)
        assert result.skip.code == "STALE_CHAIN"

    def test_no_chain(self):
        result = generate_ideas(_view(), ChainData("ACME", NOW, SPOT, LOT, False, []), NOW)
        assert result.skip.code == "NO_CHAIN"

    def test_no_expiry_far_enough_out(self):
        assert generate_ideas(_view(horizon_days=60), _chain(), NOW).skip.code == "NO_EXPIRY"

    def test_never_picks_expiry_week(self):
        near = dt.date(2026, 10, 27)  # 5 days out
        quotes = [_quote(k, t, near) for k in STRIKES for t in ("CE", "PE")]
        assert generate_ideas(_view(), _chain(quotes), NOW).skip.code == "NO_EXPIRY"

    def test_picks_the_nearest_expiry_that_is_far_enough(self):
        near, far = dt.date(2026, 10, 27), dt.date(2026, 11, 26)
        quotes = [_quote(k, t, e) for e in (near, far) for k in STRIKES for t in ("CE", "PE")]
        result = generate_ideas(_view(), _chain(quotes), NOW)
        assert result.ideas and all(i.expiry == far for i in result.ideas)

    def test_no_iv_on_the_expiry(self):
        quotes = [_quote(k, t, iv=None) for k in STRIKES for t in ("CE", "PE")]
        assert generate_ideas(_view(), _chain(quotes), NOW).skip.code == "NO_IV"

    def test_an_illiquid_chain_is_reported_as_illiquid_not_dropped(self):
        quotes = [_quote(k, t, oi=10) for k in STRIKES for t in ("CE", "PE")]
        result = generate_ideas(_view(), _chain(quotes), NOW)
        assert not result.ideas and result.skip.code == "ALL_REJECTED"
        assert "illiquid" in result.skip.message
        assert result.rejections and all(
            "illiquid" in r.reason for r in result.rejections if "outside" not in r.reason
        )

    def test_a_one_sided_book_is_rejected_not_guessed(self):
        quotes = [_quote(k, t, two_sided=False) for k in STRIKES for t in ("CE", "PE")]
        result = generate_ideas(_view(), _chain(quotes), NOW)
        assert result.skip.code == "ALL_REJECTED" and "two-sided" in result.skip.message

    def test_wide_markets_fail_the_slippage_cap(self):
        wide = [
            replace(q, bid=round(q.ltp * 0.6, 2), ask=round(q.ltp * 1.4, 2))
            for q in (_quote(k, t) for k in STRIKES for t in ("CE", "PE"))
        ]
        result = generate_ideas(_view(), _chain(wide), NOW)
        assert not result.ideas and result.skip.code == "ALL_REJECTED"
        assert all("slippage" in r.reason or "no profit" in r.reason for r in result.rejections)

    def test_a_target_beyond_the_listed_strikes_rejects_the_target_structures(self):
        result = generate_ideas(_view(target=1300.0, conviction=1.0), _chain(), NOW)
        fly = [r for r in result.rejections if r.template == "call_butterfly"]
        assert fly and all("outside the listed range" in r.reason for r in fly)

    def test_a_rejection_names_the_template_width_and_reason(self):
        result = generate_ideas(_view(), _chain(), NOW)
        assert result.rejections
        assert all(r.template and r.width in (1, 2) and r.reason for r in result.rejections)


class TestFamilyPreference:
    def _score(self, template, iv_rank):
        ideas = generate_ideas(_view(), _chain(), NOW, iv_rank=iv_rank).ideas
        return next((i.score for i in ideas if i.template == template), None)

    def test_low_iv_rank_rewards_debit_structures(self):
        base, low = self._score("bull_call_spread", None), self._score("bull_call_spread", 10.0)
        assert base is not None and low == pytest.approx(base + IdeaConfig().family_bonus)

    def test_high_iv_rank_rewards_credit_structures_and_not_debit_ones(self):
        base, high = self._score("bullish_iron_fly", None), self._score("bullish_iron_fly", 90.0)
        assert base is not None and high == pytest.approx(base + IdeaConfig().family_bonus)
        assert self._score("bull_call_spread", 90.0) == self._score("bull_call_spread", None)

    def test_mid_iv_rank_changes_nothing(self):
        assert self._score("bull_call_spread", 45.0) == self._score("bull_call_spread", None)


class TestSelection:
    def _idea(self, shape, score, pop=0.5, ror=0.1, profit=1000.0, premium=-500.0):
        return Idea(
            "ACME", shape, shape, shape, "DEBIT", EXPIRY, 35, LOT, (), premium, profit, 500.0, (),
            0.5, 0.0, pop, 10.0, ror, 0.0, 0.0, None, 25.0, "ATM_IV", score, "", (),
        )  # fmt: skip

    def test_one_per_shape_best_first(self):
        picked = _select(
            [self._idea("vertical", 0.9), self._idea("vertical", 0.8), self._idea("fly", 0.5)], 3
        )
        assert [(i.shape, i.score) for i in picked] == [("vertical", 0.9), ("fly", 0.5)]

    def test_respects_the_limit(self):
        shapes = ["vertical", "fly", "condor", "butterfly"]
        assert len(_select([self._idea(s, 1.0 - i / 10) for i, s in enumerate(shapes)], 3)) == 3

    def test_roles_follow_pop_return_and_payoff_per_cost(self):
        safe = self._idea("vertical", 0.5, pop=0.8, ror=0.05)
        value = self._idea("condor", 0.6, pop=0.6, ror=0.30)
        long_shot = self._idea("fly", 0.4, pop=0.2, ror=0.10, profit=9000.0, premium=-300.0)
        roles = {i.shape: i.role for i in _assign_roles([safe, value, long_shot])}
        assert roles == {
            "vertical": ROLE_CONSERVATIVE,
            "condor": ROLE_BALANCED,
            "fly": ROLE_TARGETED,
        }

    def test_fewer_than_three_gets_the_first_roles(self):
        roles = [
            i.role
            for i in _assign_roles(
                [self._idea("vertical", 0.5, pop=0.9), self._idea("fly", 0.4, ror=0.4)]
            )
        ]
        assert roles == [ROLE_CONSERVATIVE, ROLE_BALANCED]
