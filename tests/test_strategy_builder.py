"""Unit tests for tb_utils.options.strategy_builder.build_vertical_spread_strategy."""

# stdlib
import datetime as dt
from collections import namedtuple
from unittest.mock import MagicMock

# internal
from tb_utils.options.strategy_builder import (
    MIN_POSITIONAL_DTE,
    MIN_SPREAD_OPEN_INTEREST,
    BuiltOptionStrategy,
    build_vertical_spread_strategy,
)

Row = namedtuple(
    "Row",
    [
        "expiry_date",
        "strike_price",
        "option_type",
        "ltp",
        "implied_vol",
        "open_interest",
        "volume",
        "underlying_value",
        "dte",
    ],
)


def _mock_db(rows):
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = rows
    return db


def test_build_bull_call_spread_success():
    """Test successful construction of a Bull Call Spread."""
    expiry = dt.date.today() + dt.timedelta(days=15)
    rows = [
        # ATM Call (Strike 1000 <= Entry 1000)
        Row(
            expiry_date=expiry,
            strike_price=1000.0,
            option_type="CE",
            ltp=30.0,
            implied_vol=18.0,
            open_interest=MIN_SPREAD_OPEN_INTEREST + 500,
            volume=1000,
            underlying_value=1000.0,
            dte=15,
        ),
        # OTM Call near Target 1050
        Row(
            expiry_date=expiry,
            strike_price=1050.0,
            option_type="CE",
            ltp=10.0,
            implied_vol=18.0,
            open_interest=MIN_SPREAD_OPEN_INTEREST + 300,
            volume=800,
            underlying_value=1000.0,
            dte=15,
        ),
    ]
    db = _mock_db(rows)

    strategy = build_vertical_spread_strategy(
        db=db,
        symbol="NIFTY",
        action="BUY",
        entry_price=1000.0,
        target_price=1050.0,
        stop_loss=970.0,
        lot_size=50,
        min_dte=MIN_POSITIONAL_DTE,
    )

    assert strategy is not None
    assert isinstance(strategy, BuiltOptionStrategy)
    assert strategy.strategy_type == "BULL_CALL_SPREAD"
    assert strategy.spread_type == "DEBIT"
    assert strategy.underlying_symbol == "NIFTY"
    assert strategy.expiry_date == expiry
    assert strategy.net_premium == 20.0  # 30 - 10
    assert strategy.max_profit == 30.0  # 50 width - 20 debit
    assert strategy.max_loss == 20.0  # 20 debit
    assert strategy.risk_reward_ratio == 1.50  # 30 / 20 = 1.5 >= 1.20

    # Validate sequenced legs
    assert len(strategy.legs) == 2
    leg1, leg2 = strategy.legs

    # Leg 1: BUY Hedge Leg (execution_order 1)
    assert leg1.execution_order == 1
    assert leg1.action == "BUY"
    assert leg1.option_type == "CE"
    assert leg1.strike_price == 1000.0
    assert leg1.is_hedge is True
    assert leg1.delta is not None
    assert leg1.theta is not None

    # Leg 2: SELL Short Leg (execution_order 2)
    assert leg2.execution_order == 2
    assert leg2.action == "SELL"
    assert leg2.option_type == "CE"
    assert leg2.strike_price == 1050.0
    assert leg2.is_hedge is False
    assert leg2.delta is not None
    assert leg2.theta is not None


def test_build_bear_put_spread_success():
    """Test successful construction of a Bear Put Spread."""
    expiry = dt.date.today() + dt.timedelta(days=15)
    rows = [
        # ATM Put (Strike 1000 >= Entry 1000)
        Row(
            expiry_date=expiry,
            strike_price=1000.0,
            option_type="PE",
            ltp=32.0,
            implied_vol=20.0,
            open_interest=MIN_SPREAD_OPEN_INTEREST + 500,
            volume=1000,
            underlying_value=1000.0,
            dte=15,
        ),
        # OTM Put near Target 950
        Row(
            expiry_date=expiry,
            strike_price=950.0,
            option_type="PE",
            ltp=12.0,
            implied_vol=20.0,
            open_interest=MIN_SPREAD_OPEN_INTEREST + 400,
            volume=900,
            underlying_value=1000.0,
            dte=15,
        ),
    ]
    db = _mock_db(rows)

    strategy = build_vertical_spread_strategy(
        db=db,
        symbol="NIFTY",
        action="SELL",
        entry_price=1000.0,
        target_price=950.0,
        stop_loss=1030.0,
        lot_size=50,
        min_dte=MIN_POSITIONAL_DTE,
    )

    assert strategy is not None
    assert isinstance(strategy, BuiltOptionStrategy)
    assert strategy.strategy_type == "BEAR_PUT_SPREAD"
    assert strategy.spread_type == "DEBIT"
    assert strategy.net_premium == 20.0  # 32 - 12
    assert strategy.max_profit == 30.0  # 50 width - 20 debit
    assert strategy.max_loss == 20.0

    leg1, leg2 = strategy.legs
    assert leg1.execution_order == 1
    assert leg1.action == "BUY"
    assert leg1.strike_price == 1000.0
    assert leg1.is_hedge is True

    assert leg2.execution_order == 2
    assert leg2.action == "SELL"
    assert leg2.strike_price == 950.0
    assert leg2.is_hedge is False


def test_build_strategy_invalid_prices():
    """Invalid or zero price inputs return None."""
    db = _mock_db([])
    strat = build_vertical_spread_strategy(
        db=db,
        symbol="NIFTY",
        action="BUY",
        entry_price=0.0,
        target_price=1050.0,
        stop_loss=970.0,
    )
    assert strat is None


def test_build_strategy_insufficient_liquid_strikes():
    """Fewer than 2 liquid strikes returns None."""
    expiry = dt.date.today() + dt.timedelta(days=15)
    rows = [
        Row(
            expiry_date=expiry,
            strike_price=1000.0,
            option_type="CE",
            ltp=30.0,
            implied_vol=18.0,
            open_interest=MIN_SPREAD_OPEN_INTEREST - 10,  # Below threshold
            volume=10,
            underlying_value=1000.0,
            dte=15,
        ),
    ]
    db = _mock_db(rows)
    strat = build_vertical_spread_strategy(
        db=db,
        symbol="NIFTY",
        action="BUY",
        entry_price=1000.0,
        target_price=1050.0,
        stop_loss=970.0,
    )
    assert strat is None


def test_build_strategy_filters_low_dte_expiry():
    """Expiry below min_dte is skipped in favor of a subsequent valid expiry."""
    low_expiry = dt.date.today() + dt.timedelta(days=2)
    valid_expiry = dt.date.today() + dt.timedelta(days=16)

    rows = [
        # Low DTE expiry (DTE=2 < 6)
        Row(
            expiry_date=low_expiry,
            strike_price=1000.0,
            option_type="CE",
            ltp=15.0,
            implied_vol=18.0,
            open_interest=5000,
            volume=1000,
            underlying_value=1000.0,
            dte=2,
        ),
        Row(
            expiry_date=low_expiry,
            strike_price=1050.0,
            option_type="CE",
            ltp=5.0,
            implied_vol=18.0,
            open_interest=5000,
            volume=1000,
            underlying_value=1000.0,
            dte=2,
        ),
        # Valid DTE expiry (DTE=16 >= 6)
        Row(
            expiry_date=valid_expiry,
            strike_price=1000.0,
            option_type="CE",
            ltp=30.0,
            implied_vol=18.0,
            open_interest=5000,
            volume=1000,
            underlying_value=1000.0,
            dte=16,
        ),
        Row(
            expiry_date=valid_expiry,
            strike_price=1050.0,
            option_type="CE",
            ltp=10.0,
            implied_vol=18.0,
            open_interest=5000,
            volume=1000,
            underlying_value=1000.0,
            dte=16,
        ),
    ]
    db = _mock_db(rows)
    strat = build_vertical_spread_strategy(
        db=db,
        symbol="NIFTY",
        action="BUY",
        entry_price=1000.0,
        target_price=1050.0,
        stop_loss=970.0,
        min_dte=6,
    )
    assert strat is not None
    assert strat.expiry_date == valid_expiry
    assert strat.dte == 16
