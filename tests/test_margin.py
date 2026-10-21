"""Tests for tb_utils.options.margin.

Premiums are priced with the same Black-Scholes the margin engine uses, so a basket's entry
premium and its model value agree, as they do for a real chain snapshot.
"""

# pylint: disable=redefined-outer-name

import datetime as dt
import math

import pytest

from tb_utils.greeks import black_scholes_price
from tb_utils.options.margin import (
    ASSUMPTIONS,
    INDEX,
    INDEX_PARAMS,
    STOCK,
    STOCK_PARAMS,
    Sigma,
    estimate_margin,
    ewma_daily_vol,
    exposure_margin,
    net_short_shares,
    price_scan_range,
    scan_risk,
    sigma_from_iv,
    span_scenarios,
    vol_scan_points,
)
from tb_utils.options.payoff import Leg

TODAY = dt.date(2026, 10, 21)
EXPIRY = dt.date(2026, 10, 28)  # 7 days out
NIFTY, NIFTY_LOT, NIFTY_IV = 24500.0, 65, 13.0
SIGMA = Sigma(daily=0.0085, source="EWMA_COMPUTED")


def leg(
    action, strike, option_type="CE", lots=1, expiry=EXPIRY, spot=NIFTY, lot=NIFTY_LOT, iv=NIFTY_IV
):
    price = black_scholes_price(spot, strike, (expiry - TODAY).days, iv, option_type)
    return Leg(action, option_type, strike, round(price, 2), lots, lot, expiry, iv)


def margin(legs, sigma=SIGMA, kind=INDEX, spot=NIFTY):
    return estimate_margin(legs, spot, sigma, kind, TODAY)


# ── Volatility ───────────────────────────────────────────────────────────────


class TestVolatility:
    def test_ewma_recovers_a_steady_daily_move(self):
        closes = [100.0]
        for i in range(120):
            closes.append(closes[-1] * (1.01 if i % 2 == 0 else 1 / 1.01))
        assert ewma_daily_vol(closes) == pytest.approx(math.log(1.01), rel=0.02)

    def test_ewma_reacts_to_a_recent_shock(self):
        calm = [100.0 + 0.01 * i for i in range(100)]
        shocked = calm + [calm[-1] * 1.05]
        assert ewma_daily_vol(shocked) > 3 * ewma_daily_vol(calm)

    def test_too_little_history_is_none_not_a_guess(self):
        assert ewma_daily_vol([100.0 + i for i in range(20)]) is None

    def test_iv_fallback_is_labelled(self):
        sigma = sigma_from_iv(16.0)
        assert sigma.source == "IV_FALLBACK"
        assert sigma.daily == pytest.approx(0.16 / math.sqrt(365))

    def test_annualised_uses_sqrt_365(self):
        assert Sigma(0.01, "x").annual_pct == pytest.approx(1.0 * math.sqrt(365))


class TestScanRanges:
    def test_index_floor_binds_when_vol_is_low(self):
        assert price_scan_range(Sigma(0.005, "x"), INDEX_PARAMS) == pytest.approx(0.093)

    def test_scan_range_grows_with_vol_above_the_floor(self):
        sigma = Sigma(0.02, "x")
        assert price_scan_range(sigma, INDEX_PARAMS) == pytest.approx(6 * 0.02 * math.sqrt(2))
        assert price_scan_range(sigma, INDEX_PARAMS) > 0.093

    def test_stocks_scan_wider_than_indices(self):
        assert price_scan_range(SIGMA, STOCK_PARAMS) > price_scan_range(SIGMA, INDEX_PARAMS)

    def test_vol_scan_has_a_floor_and_a_proportional_part(self):
        assert vol_scan_points(Sigma(0.002, "x"), INDEX_PARAMS) == 4.0
        assert vol_scan_points(Sigma(0.02, "x"), INDEX_PARAMS) == pytest.approx(
            0.25 * 0.02 * math.sqrt(365) * 100
        )


class TestScenarios:
    def test_there_are_sixteen_and_the_last_two_are_extreme(self):
        scenarios = span_scenarios(INDEX_PARAMS)
        assert len(scenarios) == 16
        assert [s.weight for s in scenarios[:14]] == [1.0] * 14
        assert [(s.price_frac, s.vol_dir, s.weight) for s in scenarios[14:]] == [
            (3.0, 0, 0.35),
            (-3.0, 0, 0.35),
        ]

    def test_regular_scenarios_cover_both_directions_and_both_vol_moves(self):
        pairs = {(round(s.price_frac, 3), s.vol_dir) for s in span_scenarios(INDEX_PARAMS)[:14]}
        assert len(pairs) == 14
        assert (0.0, 1) in pairs and (0.0, -1) in pairs
        assert (round(-2 / 3, 3), -1) in pairs and (1.0, 1) in pairs


# ── Margin by structure ──────────────────────────────────────────────────────


class TestLongOnly:
    def test_margin_is_the_premium_and_nothing_else(self):
        legs = [leg("BUY", 24500, "CE"), leg("BUY", 24500, "PE")]
        m = margin(legs)
        assert m.span == 0 and m.exposure == 0 and m.short_option_min == 0
        assert m.worst_scenario is None
        assert m.total == pytest.approx(sum(lg.premium * lg.lots * lg.lot_size for lg in legs))


class TestNakedShort:
    def test_total_is_span_plus_exposure_with_no_benefit(self):
        m = margin([leg("SELL", 24500)])
        assert m.total == pytest.approx(m.span + m.exposure + m.premium)
        assert m.spread_benefit == 0
        assert m.span > 0 and m.exposure > 0

    def test_exposure_is_the_documented_percentage_of_notional(self):
        m = margin([leg("SELL", 24500, lots=2)])
        assert m.exposure == pytest.approx(2 * NIFTY_LOT * NIFTY * 0.03 * math.sqrt(2))

    def test_span_is_never_below_the_short_option_minimum(self):
        far = leg("SELL", 27500)  # deep out of the money: scan risk is small
        m = margin([far])
        assert m.short_option_min == pytest.approx(NIFTY_LOT * NIFTY * 0.05)
        assert m.span >= m.short_option_min

    def test_a_deep_otm_short_is_hurt_most_by_the_extreme_up_move(self):
        scan = scan_risk([leg("SELL", 26000)], NIFTY, SIGMA, INDEX, TODAY)
        assert scan.worst_scenario == 15

    def test_a_short_put_is_hurt_by_the_extreme_down_move(self):
        scan = scan_risk([leg("SELL", 23000, "PE")], NIFTY, SIGMA, INDEX, TODAY)
        assert scan.worst_scenario == 16

    def test_margin_scales_with_lots(self):
        one = margin([leg("SELL", 24500, lots=1)])
        three = margin([leg("SELL", 24500, lots=3)])
        assert three.total == pytest.approx(3 * one.total, rel=1e-9)


class TestHedgedStructures:
    def test_a_credit_spread_needs_a_fraction_of_the_naked_short(self):
        naked = margin([leg("SELL", 24500)])
        spread = margin([leg("SELL", 24500), leg("BUY", 24700)])
        assert spread.exposure == 0
        assert spread.total < 0.1 * naked.total
        assert spread.span <= 200 * NIFTY_LOT  # cannot lose more than the width

    def test_a_credit_spread_reports_its_benefit_against_the_legs_alone(self):
        legs = [leg("SELL", 24500), leg("BUY", 24700)]
        m = margin(legs)
        assert m.spread_benefit == pytest.approx(m.standalone - m.total)
        assert m.spread_benefit > 0.9 * m.standalone

    def test_a_debit_spread_costs_about_its_net_debit(self):
        legs = [leg("BUY", 24500), leg("SELL", 24700)]
        m = margin(legs)
        net_debit = -sum(-lg.direction * lg.lots * lg.lot_size * lg.premium for lg in legs)
        assert m.exposure == 0
        assert m.span == pytest.approx(0, abs=net_debit * 0.02)
        assert m.total == pytest.approx(net_debit, rel=0.02)

    def test_adding_a_hedge_never_raises_span(self):
        short = [leg("SELL", 24500)]
        near = short + [leg("BUY", 24700)]
        far = short + [leg("BUY", 25200)]
        spans = [margin(b).span for b in (short, far, near)]
        assert spans[0] >= spans[1] >= spans[2]

    def test_a_closer_hedge_helps_more_than_a_farther_one(self):
        assert (
            margin([leg("SELL", 24500), leg("BUY", 24700)]).total
            < margin([leg("SELL", 24500), leg("BUY", 25200)]).total
        )

    def test_a_put_credit_spread_is_hedged_the_same_way(self):
        m = margin([leg("SELL", 24300, "PE"), leg("BUY", 24100, "PE")])
        assert m.exposure == 0
        assert m.span <= 200 * NIFTY_LOT

    def test_a_ratio_spread_pays_exposure_only_on_the_uncovered_short(self):
        legs = [leg("BUY", 24500), leg("SELL", 24700, lots=2)]
        assert net_short_shares(legs) == 1 * NIFTY_LOT
        assert exposure_margin(legs, NIFTY, SIGMA, INDEX) == pytest.approx(
            NIFTY_LOT * NIFTY * 0.03 * math.sqrt(2)
        )

    def test_a_call_does_not_cover_a_short_put(self):
        assert net_short_shares([leg("SELL", 24500, "PE"), leg("BUY", 24700, "CE")]) == NIFTY_LOT


class TestTechmButterfly:
    """The design doc's fixture: BUY 1800, SELL 2 x 1840, BUY 1860 CE, lot 600."""

    def test_it_costs_its_debit_and_pays_no_exposure(self):
        sigma = Sigma(0.018, "EWMA_COMPUTED")
        legs = [
            Leg("BUY", "CE", 1800, 22.40, 1, 600, dt.date(2026, 10, 28), 24.5),
            Leg("SELL", "CE", 1840, 11.55, 2, 600, dt.date(2026, 10, 28), 24.5),
            Leg("BUY", "CE", 1860, 8.15, 1, 600, dt.date(2026, 10, 28), 24.5),
        ]
        m = estimate_margin(legs, 1767.0, sigma, STOCK, dt.date(2026, 10, 13))
        assert m.premium == pytest.approx(4470.0)
        assert m.exposure == 0
        assert m.total == pytest.approx(4470.0, rel=0.05)
        assert m.standalone > 50 * m.total


# ── Edges ────────────────────────────────────────────────────────────────────


class TestEdges:
    def test_stock_exposure_uses_the_higher_of_five_percent_and_one_and_a_half_sigma(self):
        calm = exposure_margin(
            [leg("SELL", 1800, spot=1767, lot=600)], 1767.0, Sigma(0.01, "x"), STOCK
        )
        wild = exposure_margin(
            [leg("SELL", 1800, spot=1767, lot=600)], 1767.0, Sigma(0.05, "x"), STOCK
        )
        assert calm == pytest.approx(600 * 1767 * 0.05 * math.sqrt(2))
        assert wild == pytest.approx(600 * 1767 * 1.5 * 0.05 * math.sqrt(2))

    def test_an_expiry_day_leg_is_valued_at_intrinsic(self):
        today_expiry = Leg("SELL", "CE", 24500, 80.0, 1, NIFTY_LOT, TODAY, NIFTY_IV)
        assert margin([today_expiry]).span > 0

    def test_validated_is_always_false_until_reconciled_with_a_broker(self):
        assert margin([leg("SELL", 24500)]).validated is False

    def test_the_breakdown_names_its_volatility_source_and_scan_ranges(self):
        m = margin([leg("SELL", 24500)])
        assert m.sigma_source == "EWMA_COMPUTED"
        assert m.price_scan_pct == pytest.approx(9.3)
        assert m.vol_scan_points >= 4.0

    def test_assumptions_are_stated(self):
        assert any("exposure" in a.lower() for a in ASSUMPTIONS)
        assert any("not yet checked" in a.lower() for a in ASSUMPTIONS)

    def test_a_missing_iv_is_an_error_not_a_guess(self):
        no_iv = Leg("SELL", "CE", 24500, 150.0, 1, NIFTY_LOT, EXPIRY, None)
        with pytest.raises(ValueError, match="implied volatility"):
            margin([no_iv])

    def test_futures_legs_are_refused(self):
        fut = Leg("BUY", "FUT", 24500, 0.0, 1, NIFTY_LOT, EXPIRY, None)
        with pytest.raises(ValueError, match="futures"):
            scan_risk([fut], NIFTY, SIGMA, INDEX, TODAY)

    def test_unknown_instrument_kind_is_refused(self):
        with pytest.raises(ValueError, match="kind"):
            estimate_margin([leg("SELL", 24500)], NIFTY, SIGMA, "COMMODITY", TODAY)
