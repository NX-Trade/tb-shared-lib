"""A Spread becomes a saved strategy and per-account executions the existing executor can run."""

# pylint: disable=redefined-outer-name
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from test_spread_engine import NOW, RELAXED, fresh, make_chain

from tb_utils.options import execution_rules as rules
from tb_utils.options import spread_persistence as sp
from tb_utils.options.contracts import option_contract_symbol
from tb_utils.options.spread_engine import build_vertical_spread


def spread_of(action="BUY", iv=15.0):
    return build_vertical_spread(fresh(make_chain(iv=iv)), action, NOW, RELAXED).spread


@pytest.fixture
def debit():
    return spread_of("BUY", 15.0)


@pytest.fixture
def credit():
    return spread_of("BUY", 30.0)


def strategy_of(spread, **kw):
    kw = {"signal_id": 7, "entry_price": 1000.0, "stop_loss": 995.0, **kw}
    return sp.strategy_from_spread(spread, **kw)


# ── The strategy row ─────────────────────────────────────────────────────────


def test_the_row_carries_the_spreads_identity_and_economics(debit):
    row = strategy_of(debit)
    assert (row.strategy_type, row.spread_type) == ("BULL_CALL_SPREAD", "DEBIT")
    assert (row.underlying_symbol, row.expiry_date, row.dte, row.lot_size) == (
        "TESTCO",
        debit.expiry,
        debit.dte,
        debit.lot_size,
    )
    assert row.net_premium == abs(debit.net_premium)  # rupees for the whole position, positive
    assert (row.max_profit, row.max_loss) == (debit.max_profit, debit.max_loss)
    assert row.breakeven_price == debit.breakevens[0]
    assert row.risk_reward_ratio == debit.reward_risk


def test_the_row_links_back_to_the_signal_that_caused_it(debit):
    row = strategy_of(debit, signal_id=42, entry_price=1001.5, stop_loss=996.5)
    assert row.signal_id == 42
    assert (row.underlying_entry_price, row.underlying_stop_loss) == (1001.5, 996.5)
    assert row.underlying_target_price is None  # STC has no target; it exits dynamically


def test_a_system_strategy_is_marked_by_its_source(debit):
    row = strategy_of(debit, source="STC")
    assert row.source == "STC" and row.status == "ACTIVE"
    assert "TESTCO" in row.name and "BULL CALL SPREAD" in row.name


def test_the_legs_are_in_entry_order_with_our_symbols(debit):
    row = strategy_of(debit)
    assert [leg.execution_order for leg in row.legs] == [1, 2]
    assert [leg.action for leg in row.legs] == ["BUY", "SELL"]  # hedge first
    for leg, source in zip(row.legs, debit.legs, strict=True):
        expected = option_contract_symbol("TESTCO", debit.expiry, source.strike, source.option_type)
        assert leg.symbol == expected
        assert (leg.entry_premium, leg.lots, leg.strike_price) == (
            source.premium,
            source.lots,
            source.strike,
        )
    assert [leg.is_hedge for leg in row.legs] == [True, False]


def test_the_leg_carries_what_the_engine_knew_about_it(debit):
    leg = strategy_of(debit).legs[0]
    source = debit.legs[0]
    assert (leg.delta, leg.iv, leg.open_interest, leg.volume) == (
        source.delta,
        source.iv,
        source.open_interest,
        source.volume,
    )


def test_the_audit_trail_is_kept_in_the_metadata(debit):
    row = strategy_of(debit, metadata={"chain": {"age_at_decision_s": 3.2}})
    meta = row.metadata_
    assert meta["chain"] == {"age_at_decision_s": 3.2}
    assert meta["engine"]["regime"] == debit.regime
    assert meta["engine"]["straddle_pct"] == debit.straddle_pct
    assert meta["engine"]["regime_straddle_pct"] == debit.regime_straddle_pct
    assert meta["engine"]["pop"] == debit.pop and meta["engine"]["delta_miss"] == debit.delta_miss


# ── Exit parameters decided at creation ──────────────────────────────────────


def test_the_profit_target_is_a_share_of_max_profit_expressed_as_the_executors_multiple(debit):
    """The executor's target is max_loss x multiple; 57.5% of max profit is that, rescaled."""
    multiple = sp.profit_target_multiple(debit, capture_pct=0.575)
    assert multiple * debit.max_loss == pytest.approx(0.575 * debit.max_profit, rel=0.05)
    assert strategy_of(debit, capture_pct=0.575).profit_target_multiple == pytest.approx(multiple)


def test_a_credit_spreads_target_is_below_one_times_its_loss(credit):
    """Credit spreads win small and lose big: 55% of the credit is far below 1x the risk."""
    multiple = sp.profit_target_multiple(credit, capture_pct=0.55)
    assert 0 < multiple < 1
    assert multiple * credit.max_loss == pytest.approx(0.55 * credit.max_profit, rel=0.05)


def test_the_multiple_is_never_zero(debit):
    assert sp.profit_target_multiple(debit, capture_pct=0.0) >= 0.01


def test_a_debit_stop_is_the_whole_debit(debit):
    assert sp.stop_loss_amount(debit) == debit.max_loss


def test_a_credit_stop_is_one_and_three_quarters_times_the_credit(credit):
    assert sp.stop_loss_amount(credit) == pytest.approx(1.75 * credit.net_premium, rel=0.001)


def test_a_credit_stop_never_exceeds_the_max_loss(credit):
    assert sp.stop_loss_amount(credit, credit_multiple=100.0) == credit.max_loss


def test_the_exit_parameters_are_stored_for_the_monitor(debit):
    exit_meta = strategy_of(debit, capture_pct=0.6).metadata_["exit"]
    assert exit_meta["capture_pct"] == 0.6
    assert exit_meta["stop_loss_amount"] == sp.stop_loss_amount(debit)


# ── Executions ───────────────────────────────────────────────────────────────


def test_an_execution_has_a_pending_leg_per_strategy_leg_in_whole_lots(debit):
    row = strategy_of(debit)
    execution = sp.new_execution(row, account_id=3, order_type="MARKETABLE_LIMIT")
    assert (execution.account_id, execution.status, execution.order_type) == (
        3,
        rules.PENDING,
        "MARKETABLE_LIMIT",
    )
    legs = [(leg.leg_order, leg.action, leg.status) for leg in execution.legs]
    assert legs == [(1, "BUY", "PENDING"), (2, "SELL", "PENDING")]
    assert all(leg.quantity == leg.lots * debit.lot_size for leg in execution.legs)
    assert [leg.broker_symbol for leg in execution.legs] == [leg.symbol for leg in row.legs]
    assert execution.profit_target_multiple == row.profit_target_multiple


def test_creating_saves_the_strategy_once_then_one_execution_per_account(debit):
    db = MagicMock()
    created = sp.create_executions(db, strategy_of(debit), [1, 2], "MARKETABLE_LIMIT")
    assert [e.account_id for e in created] == [1, 2]
    assert db.add.call_count >= 1 and db.commit.called


def test_an_account_already_running_it_is_skipped_not_fatal(debit):
    """The unique active index refuses a second run on the same account; the rest must still go."""
    db = MagicMock()
    # commits: the strategy, then account 1, account 2 (refused as a duplicate), account 3
    db.commit.side_effect = [None, None, IntegrityError("x", {}, Exception("dup")), None]
    created = sp.create_executions(db, strategy_of(debit), [1, 2, 3], "MARKETABLE_LIMIT")
    assert [e.account_id for e in created] == [1, 3]
    assert db.rollback.called


def test_no_accounts_creates_nothing(debit):
    db = MagicMock()
    assert not sp.create_executions(db, strategy_of(debit), [], "MARKETABLE_LIMIT")
