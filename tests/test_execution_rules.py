# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
"""Tests for tb_utils.options.execution_rules — the rules that decide how a strategy is run."""

import datetime as dt

import pytest

from tb_utils.options.execution_rules import (
    EXIT_EXPIRY,
    EXIT_TARGET,
    ORDER_TAG_PREFIX,
    LegState,
    can_send_sell_legs,
    closing_side,
    entry_complete,
    entry_sequence,
    exit_reason,
    exit_sequence,
    expiry_exit_due,
    last_session_before,
    legs_to_unwind,
    marketable_limit,
    open_pnl,
    order_tag,
    profit_target,
    realized_pnl,
    risk_from_fills,
    target_reachable,
    unsupported_broker_reason,
)

EXPIRY = dt.date(2026, 11, 26)  # a Thursday
LOT = 600


def weekend_only(day: dt.date) -> bool:
    return day.weekday() >= 5


def leg(order, action, strike, *, option_type="CE", lots=1, entry=None, filled=None, **kw):
    quantity = lots * LOT
    return LegState(
        order, action, option_type, strike, EXPIRY, lots, quantity,
        entry_price=entry, entry_filled=quantity if filled is None else filled, **kw,
    )  # fmt: skip


@pytest.fixture
def butterfly():
    """TechM 1x2x1 call butterfly, filled at the design doc's prices (debit 7.45 a share)."""
    return [
        leg(1, "BUY", 1800, entry=22.40),
        leg(2, "SELL", 1840, lots=2, entry=11.55),
        leg(3, "BUY", 1860, entry=8.15),
    ]


class TestOrdering:
    def test_entry_sends_every_buy_before_any_sell(self, butterfly):
        assert [(x.action, x.strike) for x in entry_sequence(butterfly)] == [
            ("BUY", 1800),
            ("BUY", 1860),
            ("SELL", 1840),
        ]

    def test_entry_keeps_each_groups_own_order(self):
        legs = [
            leg(4, "SELL", 1900),
            leg(1, "BUY", 1700),
            leg(3, "SELL", 1880),
            leg(2, "BUY", 1720),
        ]
        assert [x.leg_order for x in entry_sequence(legs)] == [1, 2, 3, 4]

    def test_exit_covers_the_sold_legs_before_closing_the_bought_ones(self, butterfly):
        assert [(x.action, x.strike) for x in exit_sequence(butterfly)] == [
            ("SELL", 1840),
            ("BUY", 1800),
            ("BUY", 1860),
        ]

    def test_a_sold_leg_is_bought_back_and_a_bought_leg_is_sold(self):
        assert closing_side("SELL") == "BUY" and closing_side("BUY") == "SELL"

    def test_the_input_is_not_reordered_in_place(self, butterfly):
        before = list(butterfly)
        entry_sequence(butterfly)
        exit_sequence(butterfly)
        assert butterfly == before


class TestEntryGate:
    def test_complete_only_when_every_leg_is_filled_in_full(self, butterfly):
        assert entry_complete(butterfly)
        assert not entry_complete([*butterfly[:2], leg(3, "BUY", 1860, entry=8.15, filled=300)])
        assert not entry_complete([])

    def test_sell_legs_wait_for_every_buy_leg(self):
        both = [
            leg(1, "BUY", 1800, entry=22.4),
            leg(2, "BUY", 1860, entry=8.15),
            leg(3, "SELL", 1840, entry=11.5, filled=0),
        ]
        assert can_send_sell_legs(both)
        half = [
            leg(1, "BUY", 1800, entry=22.4),
            leg(2, "BUY", 1860, filled=0),
            leg(3, "SELL", 1840, filled=0),
        ]
        assert not can_send_sell_legs(half)

    def test_a_partly_filled_buy_leg_does_not_unlock_the_sells(self):
        legs = [leg(1, "BUY", 1800, entry=22.4, filled=300), leg(2, "SELL", 1840, filled=0)]
        assert not can_send_sell_legs(legs)

    def test_a_basket_with_no_buys_is_never_unlocked_by_accident(self):
        # A pure-sell basket is not a strategy we run; the rule still must not raise.
        assert can_send_sell_legs([leg(1, "SELL", 1840, filled=0)])


class TestRollback:
    def test_two_buys_filled_and_no_sells_unwinds_just_the_buys(self):
        legs = [
            leg(1, "BUY", 1800, entry=22.4),
            leg(2, "BUY", 1860, entry=8.15),
            leg(3, "SELL", 1840, filled=0),
        ]
        assert [x.strike for x in legs_to_unwind(legs)] == [1800, 1860]

    def test_filled_shorts_are_covered_before_the_longs_are_sold(self):
        legs = [
            leg(1, "BUY", 1800, entry=22.4),
            leg(2, "BUY", 1860, entry=8.15),
            leg(3, "SELL", 1840, lots=2, entry=11.55),
            leg(4, "SELL", 1900, entry=3.0, filled=0),
        ]
        assert [(x.action, x.strike) for x in legs_to_unwind(legs)] == [
            ("SELL", 1840),
            ("BUY", 1800),
            ("BUY", 1860),
        ]

    def test_a_partly_filled_leg_unwinds_only_what_filled(self):
        legs = [leg(1, "BUY", 1800, entry=22.4, filled=250)]
        (only,) = legs_to_unwind(legs)
        assert only.open_quantity == 250

    def test_nothing_filled_means_nothing_to_unwind(self):
        assert legs_to_unwind([leg(1, "BUY", 1800, filled=0), leg(2, "SELL", 1840, filled=0)]) == []

    def test_a_leg_already_closed_is_not_unwound_again(self, butterfly):
        closed = [leg(1, "BUY", 1800, entry=22.4, exit_price=20.0, exit_filled=LOT), *butterfly[1:]]
        assert [x.strike for x in legs_to_unwind(closed)] == [1840, 1860]

    def test_open_quantity_never_goes_negative(self):
        assert (
            leg(1, "BUY", 1800, entry=1.0, exit_price=1.0, exit_filled=LOT * 3).open_quantity == 0
        )


class TestPnl:
    def test_a_long_gains_when_its_price_rises_and_a_short_when_it_falls(self):
        assert open_pnl([leg(1, "BUY", 1800, entry=20.0, mark=25.0)]) == pytest.approx(5 * LOT)
        assert open_pnl([leg(1, "SELL", 1840, entry=20.0, mark=15.0)]) == pytest.approx(5 * LOT)
        assert open_pnl([leg(1, "SELL", 1840, entry=20.0, mark=25.0)]) == pytest.approx(-5 * LOT)

    def test_a_ratio_leg_is_counted_with_its_lots(self):
        marked = [
            leg(1, "BUY", 1800, entry=22.40, mark=30.0),
            leg(2, "SELL", 1840, lots=2, entry=11.55, mark=14.0),
            leg(3, "BUY", 1860, entry=8.15, mark=9.0),
        ]
        expected = (30.0 - 22.40) * LOT + (11.55 - 14.0) * 2 * LOT + (9.0 - 8.15) * LOT
        assert open_pnl(marked) == pytest.approx(expected)

    def test_a_leg_with_no_price_withholds_the_total_instead_of_understating_it(self):
        assert (
            open_pnl([leg(1, "BUY", 1800, entry=20.0, mark=25.0), leg(2, "SELL", 1840, entry=10.0)])
            is None
        )

    def test_closed_legs_no_longer_need_a_price(self):
        closed = leg(1, "BUY", 1800, entry=20.0, exit_price=22.0, exit_filled=LOT)
        assert open_pnl([closed, leg(2, "SELL", 1840, entry=10.0, mark=9.0)]) == pytest.approx(
            1.0 * LOT
        )

    def test_a_partial_fill_is_marked_on_the_shares_it_holds(self):
        assert open_pnl([leg(1, "BUY", 1800, entry=20.0, filled=200, mark=21.0)]) == pytest.approx(
            200.0
        )

    def test_realized_pnl_counts_what_exits_locked_in(self):
        legs = [
            leg(1, "BUY", 1800, entry=22.0, exit_price=25.0, exit_filled=LOT),
            leg(2, "SELL", 1840, entry=11.0, exit_price=14.0, exit_filled=LOT),
        ]
        assert realized_pnl(legs) == pytest.approx((25 - 22) * LOT + (11 - 14) * LOT)

    def test_realized_pnl_ignores_legs_that_have_not_exited(self, butterfly):
        assert realized_pnl(butterfly) == 0.0


class TestRiskAndTarget:
    def test_max_loss_and_entry_net_come_from_the_prices_filled(self, butterfly):
        max_loss, entry_net = risk_from_fills(butterfly, LOT)
        assert max_loss == pytest.approx(4470.0)
        assert entry_net == pytest.approx(-4470.0)

    def test_a_worse_fill_raises_the_max_loss(self, butterfly):
        worse = [leg(1, "BUY", 1800, entry=23.40), *butterfly[1:]]
        assert risk_from_fills(worse, LOT)[0] == pytest.approx(5070.0)

    def test_a_credit_spread_reports_a_credit_and_its_defined_loss(self):
        legs = [
            leg(1, "BUY", 1760, option_type="PE", entry=5.0),
            leg(2, "SELL", 1800, option_type="PE", entry=12.0),
        ]
        max_loss, entry_net = risk_from_fills(legs, LOT)
        assert entry_net == pytest.approx(7.0 * LOT)
        assert max_loss == pytest.approx((40 - 7.0) * LOT)

    def test_an_uncapped_structure_is_refused(self):
        with pytest.raises(ValueError, match="uncapped"):
            risk_from_fills([leg(1, "SELL", 1800, entry=20.0)], LOT)

    def test_no_filled_legs_is_refused(self):
        with pytest.raises(ValueError, match="no filled legs"):
            risk_from_fills([leg(1, "BUY", 1800, filled=0)], LOT)

    def test_the_target_is_a_multiple_of_the_max_loss_defaulting_to_twice(self):
        assert profit_target(4470.0) == pytest.approx(8940.0)
        assert profit_target(1000.0, 3.0) == pytest.approx(3000.0)

    @pytest.mark.parametrize(
        "max_profit,max_loss,multiple,expected",
        [
            (19530, 4470, 2, True),
            (3425, 6575, 2, False),
            (8960, 4480, 2, True),
            (8959, 4480, 2, False),
            (100, 0, 2, False),
        ],
    )
    def test_whether_the_best_case_can_ever_reach_the_target(
        self, max_profit, max_loss, multiple, expected
    ):
        assert target_reachable(max_profit, max_loss, multiple) is expected


class TestExpiry:
    def test_the_last_session_before_expiry_is_the_day_before_when_it_trades(self):
        assert last_session_before(EXPIRY, weekend_only) == dt.date(2026, 11, 25)

    def test_it_skips_weekends_and_holidays(self):
        monday = dt.date(2026, 11, 23)
        assert last_session_before(monday, weekend_only) == dt.date(2026, 11, 20)  # the Friday
        holidays = {dt.date(2026, 11, 25)}
        assert last_session_before(EXPIRY, lambda d: weekend_only(d) or d in holidays) == dt.date(
            2026, 11, 24
        )

    def _at(self, day, hour, minute=0):
        return dt.datetime(day.year, day.month, day.day, hour, minute)

    def test_not_due_before_the_cutoff_on_the_last_session(self):
        assert not expiry_exit_due(self._at(dt.date(2026, 11, 25), 14, 59), EXPIRY, weekend_only)

    def test_due_from_the_cutoff_on_the_last_session(self):
        assert expiry_exit_due(self._at(dt.date(2026, 11, 25), 15, 0), EXPIRY, weekend_only)
        assert expiry_exit_due(self._at(dt.date(2026, 11, 25), 15, 20), EXPIRY, weekend_only)

    def test_due_at_any_time_once_that_session_has_passed(self):
        assert expiry_exit_due(self._at(EXPIRY, 9, 20), EXPIRY, weekend_only)

    def test_not_due_days_before(self):
        assert not expiry_exit_due(self._at(dt.date(2026, 11, 20), 15, 25), EXPIRY, weekend_only)


class TestExitReason:
    NOW = dt.datetime(2026, 11, 12, 11, 0)

    def test_the_target_exits_when_profit_reaches_it(self):
        assert exit_reason(8940.0, 8940.0, self.NOW, EXPIRY, weekend_only) == EXIT_TARGET
        assert exit_reason(12000.0, 8940.0, self.NOW, EXPIRY, weekend_only) == EXIT_TARGET

    def test_below_the_target_it_holds(self):
        assert exit_reason(8939.0, 8940.0, self.NOW, EXPIRY, weekend_only) is None
        assert exit_reason(-3000.0, 8940.0, self.NOW, EXPIRY, weekend_only) is None

    def test_no_price_means_hold_not_exit(self):
        assert exit_reason(None, 8940.0, self.NOW, EXPIRY, weekend_only) is None

    def test_a_zero_or_missing_target_never_fires(self):
        assert exit_reason(5000.0, 0.0, self.NOW, EXPIRY, weekend_only) is None
        assert exit_reason(5000.0, None, self.NOW, EXPIRY, weekend_only) is None

    def test_expiry_outranks_the_target(self):
        late = dt.datetime(2026, 11, 25, 15, 5)
        assert exit_reason(99999.0, 8940.0, late, EXPIRY, weekend_only) == EXIT_EXPIRY

    def test_expiry_exits_a_losing_position_too(self):
        late = dt.datetime(2026, 11, 25, 15, 5)
        assert exit_reason(-4000.0, 8940.0, late, EXPIRY, weekend_only) == EXIT_EXPIRY


class TestMarketableLimit:
    def test_a_buy_is_priced_above_the_last_price_and_rounded_up_to_the_tick(self):
        assert marketable_limit("BUY", 101.3) == 103.35

    def test_a_sell_is_priced_below_it_and_rounded_down(self):
        assert marketable_limit("SELL", 101.3) == 99.25

    def test_it_never_prices_below_one_tick(self):
        assert marketable_limit("SELL", 0.05) == 0.05
        assert marketable_limit("SELL", 0.1) >= 0.05

    def test_the_price_is_always_on_the_tick(self):
        for side in ("BUY", "SELL"):
            for price in (0.35, 7.7, 12.45, 122.55, 987.65):
                limit = marketable_limit(side, price)
                assert round(limit / 0.05) * 0.05 == pytest.approx(limit)

    def test_a_buy_crosses_the_market_and_a_sell_does_too(self):
        assert marketable_limit("SELL", 50.0) < 50.0 < marketable_limit("BUY", 50.0)

    @pytest.mark.parametrize("price", [0, -1.0])
    def test_rejects_a_non_positive_price(self, price):
        with pytest.raises(ValueError):
            marketable_limit("BUY", price)


def test_order_tag_marks_an_execution_orders():
    assert order_tag(42) == "optexec:42"
    assert order_tag(42).startswith(ORDER_TAG_PREFIX)


def test_only_verified_brokers_run_option_strategies_live():
    assert unsupported_broker_reason("UPSTOX", False) is None
    assert unsupported_broker_reason("upstox", False) is None
    assert unsupported_broker_reason("ANGELONE", True) is None  # paper never reaches the broker
    assert "ANGELONE" in unsupported_broker_reason("ANGELONE", False)
