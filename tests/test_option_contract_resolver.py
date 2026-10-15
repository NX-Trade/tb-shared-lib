"""Unit tests for tb_utils.options.resolver.resolve_option_contract."""

import datetime as dt
from collections import namedtuple
from unittest.mock import MagicMock

from tb_utils.options import (
    MIN_DTE_DAYS,
    MIN_OPEN_INTEREST,
    MIN_VOLUME,
    ResolvedContract,
    resolve_option_contract,
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


def test_resolve_option_contract_picks_closest_to_target_delta():
    """Among several liquid CE strikes, the one nearest the target delta wins."""
    expiry = dt.date.today() + dt.timedelta(days=7)
    rows = [
        # Deep ITM -- delta close to 1, should be skipped in favour of a more moderate delta.
        Row(expiry, 100.0, "CE", 500.0, 20.0, 5000, 1000, 1000.0, MIN_DTE_DAYS + 5),
        # Roughly ATM -- delta near 0.5, closest to TARGET_DELTA=0.45.
        Row(expiry, 1000.0, "CE", 25.0, 20.0, 5000, 1000, 1000.0, MIN_DTE_DAYS + 5),
        # Deep OTM -- delta close to 0, should be skipped in favour of ATM.
        Row(expiry, 2000.0, "CE", 2.0, 20.0, 5000, 1000, 1000.0, MIN_DTE_DAYS + 5),
    ]
    db = _mock_db(rows)

    contract = resolve_option_contract(db, "TESTSYM", "BUY")

    assert contract is not None
    assert isinstance(contract, ResolvedContract)
    assert contract.strike_price == 1000.0
    assert contract.option_type == "CE"
    assert contract.entry_premium == 25.0
    assert contract.target_premium > contract.entry_premium
    assert contract.stop_premium < contract.entry_premium


def test_resolve_option_contract_filters_illiquid_strikes():
    """Strikes below the OI/volume liquidity floor are excluded."""
    expiry = dt.date.today() + dt.timedelta(days=7)
    rows = [
        Row(
            expiry,
            1000.0,
            "PE",
            25.0,
            20.0,
            MIN_OPEN_INTEREST - 1,
            MIN_VOLUME - 1,
            1000.0,
            MIN_DTE_DAYS + 5,
        ),
    ]
    db = _mock_db(rows)

    contract = resolve_option_contract(db, "TESTSYM", "SELL")

    assert contract is None


def test_resolve_option_contract_filters_low_dte_expiries():
    """Expiries below MIN_DTE_DAYS are excluded even if liquid."""
    expiry = dt.date.today() + dt.timedelta(days=1)
    rows = [
        Row(expiry, 1000.0, "CE", 25.0, 20.0, 5000, 1000, 1000.0, 1),
    ]
    db = _mock_db(rows)

    contract = resolve_option_contract(db, "TESTSYM", "BUY")

    assert contract is None


def test_resolve_option_contract_no_data_returns_none():
    """No option_chain rows at all -> None, not an exception."""
    db = _mock_db([])

    contract = resolve_option_contract(db, "TESTSYM", "BUY")

    assert contract is None


def test_resolve_option_contract_from_redis_cache():
    """When Redis has fresh option chain records, resolve_option_contract uses Redis."""
    expiry = dt.date.today() + dt.timedelta(days=7)
    cached_records = [
        {
            "symbol": "TESTSYM",
            "expiry_date": str(expiry),
            "strike_price": 1000.0,
            "option_type": "CE",
            "ltp": 25.0,
            "implied_vol": 20.0,
            "open_interest": 5000,
            "volume": 1000,
            "underlying_value": 1000.0,
        }
    ]

    mock_store = MagicMock()
    mock_store.get_cached_option_chain.return_value = cached_records

    # DB should not even be queried
    db = MagicMock()

    contract = resolve_option_contract(db, "TESTSYM", "BUY", redis_store=mock_store)

    assert contract is not None
    assert contract.symbol == "TESTSYM"
    assert contract.strike_price == 1000.0
    assert contract.option_type == "CE"
    assert contract.entry_premium == 25.0
    db.execute.assert_not_called()


def test_resolve_option_contract_resolves_index_aliases():
    """When called with NIFTY or BANKNIFTY aliases, resolver checks all canonical aliases."""
    expiry = dt.date.today() + dt.timedelta(days=7)
    cached_records = [
        {
            "symbol": "NIFTY50",
            "expiry_date": str(expiry),
            "strike_price": 25000.0,
            "option_type": "CE",
            "ltp": 150.0,
            "implied_vol": 14.0,
            "open_interest": 50000,
            "volume": 20000,
            "underlying_value": 25000.0,
        }
    ]

    mock_store = MagicMock()

    # Cache hit on NIFTY50 when asked for NIFTY
    def get_cache(s):
        if s == "NIFTY50":
            return cached_records
        return None

    mock_store.get_cached_option_chain.side_effect = get_cache

    db = MagicMock()
    contract = resolve_option_contract(db, "NIFTY", "BUY", redis_store=mock_store)

    assert contract is not None
    assert contract.strike_price == 25000.0
    assert contract.option_type == "CE"
    assert contract.entry_premium == 150.0


def test_resolve_option_contract_next_month_preference():
    """expiry_preference='next_month' skips the near expiry for a later month's one."""
    today = dt.date.today()
    near = today + dt.timedelta(days=5)
    far = (today.replace(day=1) + dt.timedelta(days=62)).replace(day=15)
    rows = [
        Row(near, 1000.0, "PE", 25.0, 20.0, 5000, 1000, 1000.0, 5),
        Row(far, 1000.0, "PE", 60.0, 20.0, 5000, 1000, 1000.0, (far - today).days),
    ]

    default = resolve_option_contract(_mock_db(rows), "NIFTY50", "SELL")
    hedge = resolve_option_contract(
        _mock_db(rows), "NIFTY50", "SELL", expiry_preference="next_month"
    )

    assert default.expiry_date == near
    assert hedge.expiry_date == far


def test_resolve_option_contract_next_month_falls_back_to_nearest():
    """With no later-month expiry listed, next_month still resolves the nearest."""
    near = dt.date.today() + dt.timedelta(days=1)
    rows = [Row(near, 1000.0, "PE", 25.0, 20.0, 5000, 1000.0, 1000.0, MIN_DTE_DAYS + 5)]

    contract = resolve_option_contract(
        _mock_db(rows), "NIFTY50", "SELL", expiry_preference="next_month"
    )

    assert contract is not None
    assert contract.expiry_date == near


def test_cached_chain_too_close_to_expiry_falls_through_to_db():
    """A cached near expiry below MIN_DTE_DAYS must not stop the DB's next expiry."""
    today = dt.date.today()
    expiring = today + dt.timedelta(days=1)
    next_expiry = today + dt.timedelta(days=30)
    cached = [
        {
            "expiry_date": expiring.isoformat(),
            "strike_price": 1000.0,
            "option_type": "CE",
            "ltp": 25.0,
            "implied_vol": 20.0,
            "open_interest": 5000,
            "volume": 1000,
            "underlying_value": 1000.0,
        }
    ]
    store = MagicMock()
    store.get_cached_option_chain.return_value = cached
    rows = [Row(next_expiry, 1000.0, "CE", 40.0, 20.0, 5000, 1000, 1000.0, 30)]

    contract = resolve_option_contract(_mock_db(rows), "TESTSYM", "BUY", redis_store=store)

    assert contract is not None
    assert contract.expiry_date == next_expiry
