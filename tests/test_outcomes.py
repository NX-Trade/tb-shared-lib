# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.outcomes — settling an idea and judging its odds."""

import datetime as dt

import pytest

from tb_utils.options.outcomes import (
    MIN_RELIABLE_SAMPLE,
    PricePoint,
    calibration_report,
    settle_idea,
)
from tb_utils.options.payoff import Leg

EXPIRY = dt.date(2026, 11, 26)
LOT = 100


def _leg(action, option_type, strike, premium, lots=1):
    return Leg(action, option_type, strike, premium, lots, LOT, EXPIRY, 25.0)


@pytest.fixture
def bull_call_spread():
    """Buy 1000 CE @ 30, sell 1040 CE @ 12: debit 18, max profit 22, max loss 18 per share."""
    return [_leg("BUY", "CE", 1000, 30.0), _leg("SELL", "CE", 1040, 12.0)]


def _path(highs=(1010, 1030, 1050), lows=(990, 1000, 1020)):
    days = [dt.date(2026, 11, 20) + dt.timedelta(days=i) for i in range(len(highs))]
    return [PricePoint(d, h, l) for d, h, l in zip(days, highs, lows, strict=True)]  # noqa: E741


def _settle(legs, spot, **kwargs):
    base = {
        "bias": "BULLISH",
        "entry": 1000.0,
        "target": 1040.0,
        "path": _path(),
        "max_loss": 1800.0,
    }
    return settle_idea(legs, settle_spot=spot, **{**base, **kwargs})


class TestSettleIdea:
    def test_a_win_above_the_short_strike_earns_the_max_profit(self, bull_call_spread):
        outcome = _settle(bull_call_spread, 1060.0)
        assert outcome.pnl == pytest.approx((40 - 18) * LOT)
        assert outcome.win and outcome.pnl_vs_max_loss == pytest.approx(2200 / 1800)

    def test_below_the_long_strike_loses_the_whole_debit(self, bull_call_spread):
        outcome = _settle(bull_call_spread, 950.0)
        assert outcome.pnl == pytest.approx(-18 * LOT)
        assert not outcome.win and outcome.pnl_vs_max_loss == pytest.approx(-1.0)

    def test_between_the_strikes_is_priced_exactly(self, bull_call_spread):
        assert _settle(bull_call_spread, 1020.0).pnl == pytest.approx((20 - 18) * LOT)

    def test_exactly_at_breakeven_is_not_a_win(self, bull_call_spread):
        outcome = _settle(bull_call_spread, 1018.0)
        assert outcome.pnl == pytest.approx(0.0) and not outcome.win

    def test_a_bullish_view_is_right_when_the_price_settles_above_entry(self, bull_call_spread):
        assert _settle(bull_call_spread, 1001.0).direction_correct
        assert not _settle(bull_call_spread, 999.0).direction_correct

    def test_a_bearish_view_is_right_when_the_price_settles_below_entry(self):
        legs = [_leg("BUY", "PE", 1000, 30.0), _leg("SELL", "PE", 960, 12.0)]
        outcome = _settle(
            legs, 940.0, bias="BEARISH", target=960.0, path=_path((1005, 990, 970), (980, 950, 935))
        )
        assert outcome.direction_correct and outcome.win

    def test_the_target_counts_as_reached_if_touched_before_settling(self, bull_call_spread):
        # touched 1050 mid-path, then fell back to settle at 1010
        outcome = _settle(bull_call_spread, 1010.0)
        assert outcome.target_reached and outcome.best_move_pct == pytest.approx(5.0)

    def test_a_bearish_target_is_reached_by_the_low(self):
        legs = [_leg("BUY", "PE", 1000, 30.0), _leg("SELL", "PE", 960, 12.0)]
        path = _path((1005, 990, 985), (990, 955, 970))
        assert _settle(legs, 975.0, bias="BEARISH", target=960.0, path=path).target_reached
        assert not _settle(legs, 975.0, bias="BEARISH", target=940.0, path=path).target_reached

    def test_no_target_means_not_reached(self, bull_call_spread):
        assert not _settle(bull_call_spread, 1060.0, target=None).target_reached

    def test_an_empty_path_falls_back_to_the_settlement_price(self, bull_call_spread):
        outcome = _settle(bull_call_spread, 1045.0, path=[])
        assert outcome.target_reached  # 1045 >= 1040
        assert outcome.best_move_pct == pytest.approx(4.5)

    @pytest.mark.parametrize("kwargs", [{"spot": 0.0}, {"spot": 1000.0, "entry": 0.0}])
    def test_rejects_non_positive_prices(self, bull_call_spread, kwargs):
        with pytest.raises(ValueError):
            _settle(bull_call_spread, kwargs.pop("spot"), **kwargs)

    def test_a_ratio_leg_is_settled_with_its_lots(self):
        legs = [_leg("BUY", "CE", 1000, 30.0), _leg("SELL", "CE", 1040, 12.0, lots=2)]
        assert _settle(legs, 1080.0).pnl == pytest.approx((80 - 2 * 40 - 6) * LOT)


def _row(pop_view=0.5, win=True, **over):
    row = {
        "pop_view": pop_view, "pop_market": 0.4, "ev_view": 100.0, "pnl": 150.0 if win else -80.0,
        "win": win, "direction_correct": win, "target_reached": win,
        "template": "bull_call_spread", "shape": "vertical", "role": "BALANCED", "bias": "BULLISH",
    }  # fmt: skip
    return {**row, **over}


class TestCalibrationReport:
    def test_nothing_settled_yet_says_so(self):
        assert calibration_report([]) == {
            "n": 0,
            "reliable": False,
            "min_reliable": MIN_RELIABLE_SAMPLE,
        }

    def test_basic_rates_and_means(self):
        report = calibration_report(
            [_row(0.6, True), _row(0.6, True), _row(0.6, False), _row(0.6, False)]
        )
        assert report["n"] == 4 and report["win_rate"] == 0.5
        assert report["mean_pop_view"] == 0.6
        assert report["mean_pnl"] == pytest.approx((150 + 150 - 80 - 80) / 4)
        assert report["total_pnl"] == pytest.approx(140.0)

    def test_a_small_sample_is_flagged_unreliable(self):
        assert not calibration_report([_row()] * (MIN_RELIABLE_SAMPLE - 1))["reliable"]
        assert calibration_report([_row()] * MIN_RELIABLE_SAMPLE)["reliable"]

    def test_brier_score_rewards_the_better_probability(self):
        rows = [_row(0.9, True, pop_market=0.5), _row(0.1, False, pop_market=0.5)]
        report = calibration_report(rows)
        assert report["brier_view"] == pytest.approx(0.01)  # confident and right both times
        assert report["brier_market"] == pytest.approx(0.25)  # a coin flip
        assert report["brier_view"] < report["brier_market"]

    def test_a_confident_wrong_probability_scores_badly(self):
        report = calibration_report([_row(0.9, False)])
        assert report["brier_view"] == pytest.approx(0.81)

    def test_ev_error_is_negative_when_the_ideas_flattered_themselves(self):
        report = calibration_report(
            [_row(win=False, ev_view=500.0), _row(win=False, ev_view=500.0)]
        )
        assert report["ev_error"] == pytest.approx(-80.0 - 500.0)

    def test_buckets_compare_predicted_to_realised(self):
        rows = [_row(0.1, False), _row(0.15, False), _row(0.85, True), _row(1.0, True)]
        buckets = {(b["low"], b["high"]): b for b in calibration_report(rows)["buckets"]}
        assert buckets[(0.0, 0.2)]["n"] == 2 and buckets[(0.0, 0.2)]["realised"] == 0.0
        assert buckets[(0.8, 1.0)]["n"] == 2 and buckets[(0.8, 1.0)]["realised"] == 1.0
        assert buckets[(0.4, 0.6)]["n"] == 0 and buckets[(0.4, 0.6)]["realised"] is None

    def test_a_pop_of_exactly_one_lands_in_the_top_bucket(self):
        buckets = calibration_report([_row(1.0, True)])["buckets"]
        assert buckets[-1]["n"] == 1

    def test_breaks_down_by_template_role_and_bias(self):
        rows = [
            _row(template="bull_call_spread", role="CONSERVATIVE", win=True),
            _row(template="call_butterfly", role="TARGETED", win=False),
            _row(template="call_butterfly", role="TARGETED", win=False),
        ]
        report = calibration_report(rows)
        assert report["by_template"]["call_butterfly"]["n"] == 2
        assert report["by_template"]["call_butterfly"]["win_rate"] == 0.0
        assert set(report["by_role"]) == {"CONSERVATIVE", "TARGETED"}
        assert report["by_bias"]["BULLISH"]["n"] == 3

    def test_direction_and_target_rates(self):
        rows = [_row(win=True), _row(win=False, direction_correct=True, target_reached=False)]
        report = calibration_report(rows)
        assert report["direction_rate"] == 1.0 and report["target_rate"] == 0.5
