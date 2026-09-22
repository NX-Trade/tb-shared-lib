"""Unit tests for tb_utils.utils.symbol_parser."""

import datetime as dt
from unittest.mock import MagicMock

from tb_utils.utils.enums import InstrumentTypeEnum
from tb_utils.utils.symbol_parser import (
    parse_trading_symbol,
    resolve_underlying_instrument_id,
)


def test_parse_trading_symbol_equity():
    parsed = parse_trading_symbol("RELIANCE")
    assert parsed.underlying_symbol == "RELIANCE"
    assert parsed.instrument_type == InstrumentTypeEnum.EQUITY
    assert parsed.trading_symbol == "RELIANCE"
    assert parsed.expiry_date is None
    assert parsed.strike_price is None
    assert parsed.option_type is None


def test_parse_trading_symbol_option_call():
    parsed = parse_trading_symbol("SONACOMS26SEP820CE")
    assert parsed.underlying_symbol == "SONACOMS"
    assert parsed.instrument_type == InstrumentTypeEnum.CE
    assert parsed.trading_symbol == "SONACOMS26SEP820CE"
    assert parsed.strike_price == 820.0
    assert parsed.option_type == "CE"
    assert parsed.expiry_date == dt.date(2026, 9, 30)


def test_parse_trading_symbol_option_put():
    parsed = parse_trading_symbol("NIFTY26SEP24000PE")
    assert parsed.underlying_symbol == "NIFTY"
    assert parsed.instrument_type == InstrumentTypeEnum.PE
    assert parsed.trading_symbol == "NIFTY26SEP24000PE"
    assert parsed.strike_price == 24000.0
    assert parsed.option_type == "PE"
    assert parsed.expiry_date == dt.date(2026, 9, 30)


def test_parse_trading_symbol_future():
    parsed = parse_trading_symbol("NIFTY26SEPFUT")
    assert parsed.underlying_symbol == "NIFTY"
    assert parsed.instrument_type == InstrumentTypeEnum.FUT
    assert parsed.trading_symbol == "NIFTY26SEPFUT"
    assert parsed.expiry_date == dt.date(2026, 9, 30)
    assert parsed.strike_price is None


def test_resolve_underlying_exact_match():
    db = MagicMock()
    mock_row = MagicMock()
    mock_row.instrument_id = 42
    db.query.return_value.filter.return_value.first.return_value = mock_row

    inst_id = resolve_underlying_instrument_id(db, "RELIANCE")
    assert inst_id == 42


def test_resolve_underlying_prefix_fallback():
    db = MagicMock()
    # First query (exact match) returns None, second (prefix) returns row
    mock_row = MagicMock()
    mock_row.instrument_id = 99
    db.query.return_value.filter.return_value.first.side_effect = [None, mock_row]

    inst_id = resolve_underlying_instrument_id(db, "SONACOMS")
    assert inst_id == 99


def test_resolve_underlying_not_found():
    db = MagicMock()
    # exact, alias map query, prefix all fail
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.all.return_value = []

    inst_id = resolve_underlying_instrument_id(db, "UNKNOWN")
    assert inst_id is None


def test_parse_trading_symbol_weekly_option():
    """Verify weekly options format like NIFTY2692223400PE parse correctly."""
    parsed = parse_trading_symbol("NIFTY2692223400PE")
    assert parsed.underlying_symbol == "NIFTY"
    assert parsed.instrument_type == InstrumentTypeEnum.PE
    assert parsed.trading_symbol == "NIFTY2692223400PE"
    assert parsed.strike_price == 23400.0
    assert parsed.option_type == "PE"
    assert parsed.expiry_date == dt.date(2026, 9, 22)

    parsed_ce = parse_trading_symbol("BANKNIFTY26O0851000CE")
    assert parsed_ce.underlying_symbol == "BANKNIFTY"
    assert parsed_ce.instrument_type == InstrumentTypeEnum.CE
    assert parsed_ce.trading_symbol == "BANKNIFTY26O0851000CE"
    assert parsed_ce.strike_price == 51000.0
    assert parsed_ce.option_type == "CE"
    assert parsed_ce.expiry_date == dt.date(2026, 10, 8)


def test_resolve_underlying_index_alias():
    """Verify NIFTY resolves to NIFTY50 instrument_id via instrument map aliases."""
    db = MagicMock()
    # Exact match for "NIFTY" returns None
    db.query.return_value.filter.return_value.first.return_value = None

    # But get_instrument_map returns NIFTY50 instrument
    mock_nifty50 = MagicMock(instrument_id=1001, symbol="NIFTY50", ib_symbol="NIFTY50")
    db.query.return_value.all.return_value = [mock_nifty50]

    inst_id = resolve_underlying_instrument_id(db, "NIFTY")
    assert inst_id == 1001

