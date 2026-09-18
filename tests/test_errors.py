"""Unit tests for tb_utils.errors exception hierarchy."""

from tb_utils.errors import (
    CircuitOpen,
    DataUnavailable,
    DuplicateRecordError,
    ExternalApiError,
    InvalidSecurityError,
    NxTradeError,
    TbErrorCode,
    TradingBotAPIException,
    ValidationError,
)


def test_nxtrade_error_base() -> None:
    err = NxTradeError("Something went wrong", symbol="NIFTY", attempt=3)
    assert str(err) == "Something went wrong (symbol=NIFTY attempt=3)"
    assert err.code == "NX_ERROR"
    assert err.retryable is False
    assert err.alert is False
    assert err.details == {"symbol": "NIFTY", "attempt": 3}


def test_data_unavailable() -> None:
    err = DataUnavailable("No regime rows found for date", as_of="2026-09-18")
    assert isinstance(err, NxTradeError)
    assert err.code == "DATA_UNAVAILABLE"
    assert err.details["as_of"] == "2026-09-18"


def test_external_api_error_attributes() -> None:
    err = ExternalApiError(
        "NSE request failed",
        provider="NSE",
        endpoint="/api/option-chain",
        status_code=502,
    )
    assert isinstance(err, NxTradeError)
    assert err.provider == "NSE"
    assert err.endpoint == "/api/option-chain"
    assert err.status_code == 502
    assert err.code == "EXTERNAL_API_ERROR"


def test_circuit_open_error() -> None:
    err = CircuitOpen("Circuit breaker is OPEN", provider="UPSTOX", cooldown_seconds=60.0)
    assert isinstance(err, ExternalApiError)
    assert err.code == "CIRCUIT_OPEN"
    assert err.retryable is False  # Callers should degrade rather than hammering open breaker
    assert err.details["cooldown_seconds"] == 60.0


def test_legacy_api_exceptions_inherit_from_nxtrade_error() -> None:
    inv = InvalidSecurityError("Unknown symbol FOOBAR")
    assert isinstance(inv, NxTradeError)
    assert isinstance(inv, TradingBotAPIException)
    assert inv.status_code == 400
    assert inv.error_code == TbErrorCode.INVALID_SECURITY

    dup = DuplicateRecordError("Signal already exists")
    assert isinstance(dup, NxTradeError)
    assert dup.status_code == 409
    assert dup.error_code == TbErrorCode.DUPLICATE_RECORD

    val = ValidationError("Invalid quantity")
    assert isinstance(val, NxTradeError)
    assert val.status_code == 400
    assert val.error_code == TbErrorCode.VALIDATION_FAILED
