# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.ideas — the generator over a synthetic, fairly priced chain."""

import datetime as dt
from dataclasses import replace

import pytest

from tb_utils.greeks import black_scholes_price
from tb_utils.options.ideas import (
    ChainData,
    DirectionalView,
    IdeaConfig,
    Quote,
    suggest_strategies,
)
from tb_utils.time import IST

SPOT = 1000.0
IV = 25.0
LOT = 100
NOW = dt.datetime(2026, 10, 22, 19, 0, tzinfo=IST)
EXPIRY = dt.date(2026, 11, 26)  # 35 days out
STRIKES = [float(k) for k in range(800, 1201, 20)]
HALF_SPREAD = 0.25


def _quote(
    strike,
    option_type,
    expiry=EXPIRY,
    *,
    oi=5000,
    volume=1000,
    iv=IV,
    two_sided=True,
    half=HALF_SPREAD,
):
    days = (expiry - NOW.date()).days
    fair = float(black_scholes_price(SPOT, strike, days, IV, option_type))
    mid = max(fair, 0.5)
    return Quote(
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        bid=round(mid - half, 2) if two_sided else None,
        ask=round(mid + half, 2) if two_sided else None,
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


class TestRequestedExpiry:
    """The expiry picked in the UI is the one strategies are built on."""

    NEAR = dt.date(2026, 10, 27)  # 5 days out: inside the default "not expiry week" cut-off
    FAR = dt.date(2026, 12, 31)

    def _two_expiries(self):
        quotes = [
            _quote(k, t, e) for e in (self.NEAR, EXPIRY) for k in STRIKES for t in ("CE", "PE")
        ]
        return _chain(quotes)

    def test_defaults_to_the_nearest_expiry_with_enough_days(self):
        assert suggest_strategies(self._two_expiries(), NOW).expiry == EXPIRY

    def test_builds_on_the_requested_expiry_even_inside_the_default_cutoff(self):
        found = suggest_strategies(self._two_expiries(), NOW, expiry=self.NEAR)
        assert found.expiry == self.NEAR
        assert found.ideas
        assert {i.expiry for i in found.ideas} == {self.NEAR}

    def test_an_expiry_with_no_stored_chain_says_so(self):
        found = suggest_strategies(self._two_expiries(), NOW, expiry=self.FAR)
        assert found.skip.code == "NO_EXPIRY"
        assert not found.ideas

    def test_an_expiry_that_is_today_is_refused(self):
        found = suggest_strategies(self._two_expiries(), NOW, expiry=NOW.date())
        assert found.skip.code == "NO_EXPIRY"


class TestSuggestStrategies:
    """Strategies straight from the chain: no research signal, no target, both leans."""

    @pytest.fixture
    def found(self):
        return suggest_strategies(_chain(), NOW)

    def test_returns_bullish_and_bearish_strategies_from_the_chain_alone(self, found):
        assert found.skip is None
        biases = {i.bias for i in found.ideas}
        assert biases == {"BULLISH", "BEARISH"}
        assert len([i for i in found.ideas if i.bias == "BULLISH"]) >= 2
        assert len([i for i in found.ideas if i.bias == "BEARISH"]) >= 2

    def test_bullish_come_first_then_bearish_best_score_first_within_each(self, found):
        order = [i.bias for i in found.ideas]
        assert order == sorted(order, key=("BULLISH", "BEARISH").index)
        for bias in ("BULLISH", "BEARISH"):
            scores = [i.score for i in found.ideas if i.bias == bias]
            assert scores == sorted(scores, reverse=True)

    def test_every_strategy_pays_off_on_the_side_it_leans(self, found):
        """A lean is where the payoff lies, not the sign of today's delta: a bullish broken-wing
        butterfly has a body above spot and a slightly negative delta right now."""
        for idea in found.ideas:
            above = [
                pnl for spot, pnl in idea.curve if SPOT < spot <= SPOT + 0.7 * found.expected_move
            ]
            below = [
                pnl for spot, pnl in idea.curve if SPOT - 0.7 * found.expected_move <= spot < SPOT
            ]
            up, down = sum(above) / len(above), sum(below) / len(below)
            assert (up > down) == (idea.bias == "BULLISH"), (idea.template, idea.bias, up, down)

    def test_there_is_no_view_so_no_view_figures(self, found):
        assert all(
            i.pop_view is None and i.ev_view is None and i.return_on_risk is None
            for i in found.ideas
        )

    def test_each_carries_everything_a_payoff_card_needs(self, found):
        for idea in found.ideas:
            assert idea.max_loss > 0 and idea.max_profit > 0
            assert idea.reward_risk == pytest.approx(idea.max_profit / idea.max_loss, abs=0.01)
            assert 0 < idea.pop_market < 1 and idea.breakevens
            assert len(idea.curve) == 41 and idea.margin_estimate and idea.legs
            assert idea.width in (1, 2) and idea.rationale

    def test_market_expected_value_is_shown_but_never_used_to_reject(self, found):
        """A fairly priced basket's EV at market odds is about minus its cost; it must not gate."""
        assert any(i.ev_market < 0 for i in found.ideas)
        assert all("expected value" not in r.reason for r in found.rejections)

    def test_reports_the_expiry_and_the_expected_move_it_used(self, found):
        assert found.expiry == EXPIRY and found.dte == 35 and found.atm_iv == IV
        assert found.expected_move == pytest.approx(SPOT * IV / 100 * (35.2 / 365) ** 0.5, rel=0.02)

    def test_a_butterfly_body_sits_half_an_expected_move_from_spot_on_its_side(self, found):
        move = found.expected_move
        for bias, sign in (("BULLISH", 1), ("BEARISH", -1)):
            fly = next(
                i for i in found.ideas if i.bias == bias and i.template.endswith("butterfly")
            )
            body = next(leg for leg in fly.legs if leg.action == "SELL").strike
            assert abs(body - (SPOT + sign * 0.5 * move)) <= 20  # within one strike step

    def test_both_widths_are_offered(self, found):
        assert {i.width for i in found.ideas} == {1, 2}

    def test_every_strategy_has_defined_risk_and_covered_shorts(self, found):
        for idea in found.ideas:
            longs = sum(leg.lots for leg in idea.legs if leg.action == "BUY")
            shorts = sum(leg.lots for leg in idea.legs if leg.action == "SELL")
            assert longs >= shorts and 2 <= len(idea.legs) <= 4

    def test_legs_use_listed_strikes_and_pay_the_spread(self, found):
        for idea in found.ideas:
            for leg in idea.legs:
                assert leg.strike in STRIKES
                assert leg.premium == (leg.ask if leg.action == "BUY" else leg.bid)

    def test_the_underlying_name_comes_from_the_chain(self, found):
        assert found.underlying == "ACME" and all(i.underlying == "ACME" for i in found.ideas)

    def test_a_low_iv_rank_rewards_debit_structures_in_the_ordering(self):
        base = {i.template: i.score for i in suggest_strategies(_chain(), NOW).ideas}
        low = {i.template: i.score for i in suggest_strategies(_chain(), NOW, iv_rank=10.0).ideas}
        assert low["call_butterfly"] == pytest.approx(
            base["call_butterfly"] + IdeaConfig().family_bonus
        )


class TestSuggestSkips:
    """Why an underlying gets no strategies, in the same words the user will read."""

    def test_a_wide_market_is_filtered_and_the_reason_kept(self):
        wide = [
            replace(q, bid=round(q.ltp * 0.6, 2), ask=round(q.ltp * 1.4, 2))
            for q in (_quote(k, t) for k in STRIKES for t in ("CE", "PE"))
        ]
        found = suggest_strategies(_chain(wide), NOW)
        assert not found.ideas and found.skip.code == "ALL_REJECTED"
        assert found.rejections and found.expiry == EXPIRY

    def test_a_one_sided_book_is_rejected_not_guessed(self):
        quotes = [_quote(k, t, two_sided=False) for k in STRIKES for t in ("CE", "PE")]
        found = suggest_strategies(_chain(quotes), NOW)
        assert not found.ideas and "two-sided" in found.skip.message

    def test_a_rejection_names_the_template_width_and_reason(self):
        found = suggest_strategies(_chain(), NOW)
        assert found.rejections
        assert all(
            r.template and r.width in (0, 1, 2) and r.reason for r in found.rejections
        )  # 0: a delta-built vertical

    def test_an_illiquid_chain_says_illiquid(self):
        quotes = [_quote(k, t, oi=10) for k in STRIKES for t in ("CE", "PE")]
        found = suggest_strategies(_chain(quotes), NOW)
        assert not found.ideas and "illiquid" in found.skip.message

    @pytest.mark.parametrize(
        "kwargs,code",
        [({"horizon_days": 90}, "NO_EXPIRY")],
    )
    def test_no_usable_expiry(self, kwargs, code):
        assert suggest_strategies(_chain(), NOW, **kwargs).skip.code == code

    def test_no_iv_on_the_expiry(self):
        quotes = [_quote(k, t, iv=None) for k in STRIKES for t in ("CE", "PE")]
        assert suggest_strategies(_chain(quotes), NOW).skip.code == "NO_IV"

    def test_no_chain(self):
        assert (
            suggest_strategies(ChainData("ACME", NOW, SPOT, LOT, False, []), NOW).skip.code
            == "NO_CHAIN"
        )

    def test_an_old_chain_is_refused_unless_the_caller_allows_it(self):
        old = _chain(ts=NOW - dt.timedelta(days=3))
        assert suggest_strategies(old, NOW).skip.code == "STALE_CHAIN"
        allowed = IdeaConfig(max_chain_age=dt.timedelta(days=10))
        assert suggest_strategies(old, NOW, config=allowed).ideas

    def test_picks_the_nearest_expiry_that_is_far_enough_never_expiry_week(self):
        near, far = dt.date(2026, 10, 27), dt.date(2026, 11, 26)
        quotes = [_quote(k, t, e) for e in (near, far) for k in STRIKES for t in ("CE", "PE")]
        found = suggest_strategies(_chain(quotes), NOW)
        assert found.expiry == far and all(i.expiry == far for i in found.ideas)


class TestSuggestWithAView:
    def test_a_view_adds_probability_and_ev_at_the_view_and_keeps_only_its_side(self):
        found = suggest_strategies(_chain(), NOW, view=_view())
        assert found.ideas and {i.bias for i in found.ideas} == {"BULLISH"}
        for idea in found.ideas:
            assert idea.pop_view is not None and idea.ev_view > 0 and idea.return_on_risk > 0
            assert idea.ev_view > idea.ev_market

    def test_a_view_rejects_structures_worth_nothing_even_if_it_plays_out(self):
        found = suggest_strategies(_chain(), NOW, view=_view())
        assert any("negative expected value at the view" in r.reason for r in found.rejections)

    def test_a_view_ranks_by_its_score_best_first(self):
        scores = [i.score for i in suggest_strategies(_chain(), NOW, view=_view()).ideas]
        assert scores == sorted(scores, reverse=True)

    def test_a_bearish_view_returns_bearish_strategies(self):
        found = suggest_strategies(_chain(), NOW, view=_view("BEARISH", 940.0))
        assert found.ideas and {i.bias for i in found.ideas} == {"BEARISH"}

    def test_a_view_with_the_target_on_the_wrong_side_says_so(self):
        found = suggest_strategies(_chain(), NOW, view=_view(target=900.0))
        assert not found.ideas and found.skip.code == "TARGET_WRONG_SIDE"

    def test_a_view_below_the_conviction_floor_is_refused(self):
        assert (
            suggest_strategies(_chain(), NOW, view=_view(conviction=0.1)).skip.code
            == "LOW_CONVICTION"
        )

    def test_a_view_is_deterministic(self):
        first = suggest_strategies(_chain(), NOW, view=_view())
        second = suggest_strategies(_chain(), NOW, view=_view())
        assert [(i.template, i.width, i.score) for i in first.ideas] == [
            (i.template, i.width, i.score) for i in second.ideas
        ]

    def test_a_stronger_conviction_lifts_the_expected_value_at_the_view(self):
        weak = suggest_strategies(_chain(), NOW, view=_view(conviction=0.5)).ideas
        strong = suggest_strategies(_chain(), NOW, view=_view(conviction=1.0)).ideas
        by_key = {(i.template, i.width): i.ev_view for i in weak}
        shared = [i for i in strong if (i.template, i.width) in by_key]
        assert shared and all(i.ev_view > by_key[(i.template, i.width)] for i in shared)

    @pytest.mark.parametrize(
        "view,code",
        [
            (_view("NEUTRAL"), "NO_VIEW"),
            (_view(target=None), "NO_TARGET"),
            (_view("BEARISH", 1050.0), "TARGET_WRONG_SIDE"),
        ],
    )
    def test_an_unusable_view_gives_no_strategies_and_says_why(self, view, code):
        found = suggest_strategies(_chain(), NOW, view=view)
        assert not found.ideas and found.skip.code == code and found.skip.message

    def test_a_view_on_a_stale_chain_is_refused(self):
        found = suggest_strategies(_chain(ts=NOW - dt.timedelta(days=3)), NOW, view=_view())
        assert found.skip.code == "STALE_CHAIN"

    def test_a_target_beyond_the_listed_strikes_rejects_the_target_structures(self):
        found = suggest_strategies(_chain(), NOW, view=_view(target=1300.0, conviction=1.0))
        fly = [r for r in found.rejections if r.template == "call_butterfly"]
        assert fly and all("outside the listed range" in r.reason for r in fly)

    def test_a_low_iv_rank_rewards_debit_structures_at_a_view(self):
        base = {i.template: i.score for i in suggest_strategies(_chain(), NOW, view=_view()).ideas}
        low = {
            i.template: i.score
            for i in suggest_strategies(_chain(), NOW, view=_view(), iv_rank=10.0).ideas
        }
        assert low["call_butterfly"] == pytest.approx(
            base["call_butterfly"] + IdeaConfig().family_bonus
        )


class TestMinimumRewardToRisk:
    """A floor on max profit over max loss: strategies under it are dropped, reason kept."""

    def _with(self, minimum):
        config = IdeaConfig(min_reward_risk=minimum)
        return suggest_strategies(_chain(), NOW, config=config)

    def test_the_default_keeps_everything(self):
        assert IdeaConfig().min_reward_risk == 0.0
        assert any(i.reward_risk < 1 for i in self._with(0.0).ideas)

    def test_a_floor_keeps_only_strategies_at_or_above_it(self):
        found = self._with(4.0)
        assert found.ideas and all(i.reward_risk >= 4.0 for i in found.ideas)

    def test_a_floor_drops_the_high_probability_structures_and_keeps_the_long_shots(self):
        everything, floored = self._with(0.0), self._with(4.0)
        assert len(floored.ideas) < len(everything.ideas)
        assert {i.shape for i in floored.ideas} <= {"butterfly", "fly"}
        assert max(i.pop_market for i in everything.ideas) > max(
            i.pop_market for i in floored.ideas
        )

    def test_every_strategy_the_floor_removes_is_counted_under_one_reason(self):
        everything, floored = self._with(0.0), self._with(4.0)
        removed = len(everything.ideas) - len(floored.ideas)
        counted = [
            r for r in floored.rejections if r.reason == "reward-to-risk is below the minimum"
        ]
        # The floor is checked before slippage, so it may also claim candidates that would have
        # failed that later filter anyway; it can never claim fewer than it removed.
        assert len(counted) >= removed > 0

    def test_a_floor_no_strategy_can_meet_says_so(self):
        found = self._with(1000.0)
        assert not found.ideas and found.skip.code == "ALL_REJECTED"
        assert "reward-to-risk" in found.skip.message

    def test_the_floor_also_applies_with_a_view(self):
        config = IdeaConfig(min_reward_risk=4.0)
        found = suggest_strategies(_chain(), NOW, view=_view(), config=config)
        assert all(i.reward_risk >= 4.0 for i in found.ideas)


# ── Verticals follow the spec, not the strike-offset templates ──────────────────────────────────
#
# The templates buy the at-the-money strike and sell one or two strikes away: a debit spread built
# that way costs about half its width, so its reward:risk is about 1:1 and the spec's 1:2.5 can
# never
# be met (30 Oct 2026). Verticals now come from the spread engine's delta bands and rules.


def _liquid_chain():
    quotes = [
        _quote(k, t, oi=20000, volume=50000, half=0.05) for k in STRIKES for t in ("CE", "PE")
    ]
    return _chain(quotes)


def _verticals(found):
    return [i for i in found.ideas if i.shape == "vertical"]


class TestVerticalsFollowTheSpec:
    def test_no_vertical_is_drawn_at_the_old_one_to_one(self):
        for floor in (0.0, 4.0):
            found = suggest_strategies(
                _liquid_chain(), NOW, config=IdeaConfig(min_reward_risk=floor)
            )
            for idea in _verticals(found):
                if idea.family == "DEBIT":
                    assert idea.reward_risk >= 2.5 - 1e-9

    def test_a_credit_vertical_collects_at_least_a_quarter_of_its_width(self):
        found = suggest_strategies(_liquid_chain(), NOW)
        credit_ideas = [i for i in _verticals(found) if i.family == "CREDIT"]
        assert credit_ideas
        for idea in credit_ideas:
            width = max(leg.strike for leg in idea.legs) - min(leg.strike for leg in idea.legs)
            assert idea.net_premium / idea.lot_size >= 0.25 * width - 1e-6

    def test_the_generic_floor_does_not_remove_a_vertical_the_rules_accept(self):
        loose = _verticals(
            suggest_strategies(_liquid_chain(), NOW, config=IdeaConfig(min_reward_risk=0.0))
        )
        strict = _verticals(
            suggest_strategies(_liquid_chain(), NOW, config=IdeaConfig(min_reward_risk=4.0))
        )
        assert [i.template for i in strict] == [i.template for i in loose]

    def test_bought_legs_come_first(self):
        for idea in _verticals(suggest_strategies(_liquid_chain(), NOW)):
            actions = [leg.action for leg in idea.legs]
            assert actions == sorted(actions, key=lambda a: a != "BUY")

    def test_a_vertical_the_rules_refuse_is_reported_with_the_reason_not_drawn(self):
        found = suggest_strategies(_liquid_chain(), NOW)
        refused = [r for r in found.rejections if r.width == 0]
        assert refused and all(r.reason for r in refused)
        built = {i.template for i in _verticals(found)}
        assert not built & {r.template for r in refused}

    def test_an_illiquid_chain_yields_no_vertical_rather_than_a_one_to_one(self):
        assert not _verticals(
            suggest_strategies(_chain(), NOW)
        )  # default test chain: volume 1,000 < 10,000

    def test_the_other_structures_are_unchanged(self):
        shapes = {i.shape for i in suggest_strategies(_liquid_chain(), NOW).ideas}
        assert shapes - {"vertical"}  # butterflies and the rest still come from the templates

    def test_a_requested_expiry_is_the_one_the_vertical_is_built_on(self):
        found = suggest_strategies(_liquid_chain(), NOW, expiry=EXPIRY)
        assert all(i.expiry == EXPIRY for i in found.ideas)
