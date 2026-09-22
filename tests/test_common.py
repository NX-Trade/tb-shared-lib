"""Unit tests for tb_utils.utils.common."""

from unittest.mock import MagicMock

from tb_utils.utils.common import get_instrument_map, resolve_instrument_id


def test_get_instrument_map_and_index_aliases():
    """Verify get_instrument_map correctly maps symbols and auto-injects index aliases."""
    mock_session = MagicMock()
    # Mock instruments: RELIANCE, NIFTY50, BANKNIFTY, FINNIFTY
    mock_inst_rel = MagicMock(instrument_id=101, symbol="RELIANCE", ib_symbol="RELIANCE-EQ")
    mock_inst_nifty = MagicMock(instrument_id=1001, symbol="NIFTY50", ib_symbol="NIFTY50")
    mock_inst_bank = MagicMock(instrument_id=1002, symbol="BANKNIFTY", ib_symbol="BANKNIFTY")
    mock_inst_fin = MagicMock(instrument_id=1003, symbol="FINNIFTY", ib_symbol="FINNIFTY")

    mock_session.query.return_value.all.return_value = [
        mock_inst_rel,
        mock_inst_nifty,
        mock_inst_bank,
        mock_inst_fin,
    ]

    inst_map = get_instrument_map(mock_session)

    # Standard equity
    assert resolve_instrument_id("RELIANCE", inst_map) == 101
    assert resolve_instrument_id("RELIANCE.NS", inst_map) == 101
    assert resolve_instrument_id("RELIANCE-EQ", inst_map) == 101

    # NIFTY 50 aliases
    assert resolve_instrument_id("NIFTY50", inst_map) == 1001
    assert resolve_instrument_id("NIFTY", inst_map) == 1001
    assert resolve_instrument_id("NIFTY 50", inst_map) == 1001
    assert resolve_instrument_id("nifty 50", inst_map) == 1001
    assert resolve_instrument_id("NSE_INDEX|Nifty 50", inst_map) == 1001

    # BANK NIFTY aliases
    assert resolve_instrument_id("BANKNIFTY", inst_map) == 1002
    assert resolve_instrument_id("NIFTYBANK", inst_map) == 1002
    assert resolve_instrument_id("NIFTY BANK", inst_map) == 1002
    assert resolve_instrument_id("bank nifty", inst_map) == 1002
    assert resolve_instrument_id("NSE_INDEX|Nifty Bank", inst_map) == 1002

    # FIN NIFTY aliases
    assert resolve_instrument_id("FINNIFTY", inst_map) == 1003
    assert resolve_instrument_id("NIFTY FIN SERVICE", inst_map) == 1003
    assert resolve_instrument_id("FIN NIFTY", inst_map) == 1003

    # Unknown symbol
    assert resolve_instrument_id("UNKNOWN_SYM", inst_map) is None
    assert resolve_instrument_id(None, inst_map) is None
