"""Custom exceptions for the tb_utils package.

This module contains all custom exceptions used throughout the library.
These exceptions provide more specific error handling than standard Python exceptions.
"""

from enum import Enum
from typing import Any, Optional

from tb_utils.http.errors import (
    CircuitOpen,
    ExternalApiError,
    NxTradeError,
)


class TbErrorCode(Enum):
    INVALID_SECURITY = "INVALID_SECURITY"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"


class DataUnavailable(NxTradeError):
    """Raised when expected data (e.g. OHLCV, ticks, regimes) is missing in DB or cache."""

    code = "DATA_UNAVAILABLE"


class TradingBotAPIException(NxTradeError):
    """General TradingBot API exception.

    Base exception class for all API-related errors in the library.
    """

    code = "TRADING_BOT_API_ERROR"

    def __init__(self, message: str, status_code: Optional[int] = None, **details: Any):
        super().__init__(message, status_code=status_code, **details)
        self.error_code: Optional[TbErrorCode] = None
        self.status_code = status_code


class InvalidSecurityError(TradingBotAPIException):
    """Invalid security exception.

    Raised when an operation is attempted with an invalid security identifier.
    """

    code = "INVALID_SECURITY"

    def __init__(self, message: str = "Invalid security identifier", **details: Any):
        super().__init__(message, status_code=400, **details)
        self.error_code = TbErrorCode.INVALID_SECURITY


class DuplicateRecordError(TradingBotAPIException):
    """Duplicate record exception.

    Raised when attempting to insert a record that already exists in the database.
    """

    code = "DUPLICATE_RECORD"

    def __init__(self, message: str = "Record already exists", **details: Any):
        super().__init__(message, status_code=409, **details)
        self.error_code = TbErrorCode.DUPLICATE_RECORD


class ValidationError(TradingBotAPIException):
    """Validation error exception.

    Raised when data validation fails.
    """

    code = "VALIDATION_FAILED"

    def __init__(self, message: str = "Validation failed", **details: Any):
        super().__init__(message, status_code=400, **details)
        self.error_code = TbErrorCode.VALIDATION_FAILED


__all__ = [
    "CircuitOpen",
    "DataUnavailable",
    "DuplicateRecordError",
    "ExternalApiError",
    "InvalidSecurityError",
    "NxTradeError",
    "TbErrorCode",
    "TradingBotAPIException",
    "ValidationError",
]
