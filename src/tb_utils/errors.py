"""Custom exceptions for the tb_utils package.

This module contains all custom exceptions used throughout the library.
These exceptions provide more specific error handling than standard Python exceptions.
"""

from enum import Enum
from typing import Optional


class TbErrorCode(str, Enum):
    INVALID_SECURITY = "INVALID_SECURITY"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"


class TradingBotAPIException(Exception):
    """General TradingBot API exception.

    Base exception class for all API-related errors in the library.

    Attributes:
        message: The error message
        status_code: HTTP status code associated with the error (optional)
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.error_code: Optional[TbErrorCode] = None
        self.status_code = status_code
        super().__init__(self.message)


class InvalidSecurityError(TradingBotAPIException):
    """Invalid security exception.

    Raised when an operation is attempted with an invalid security identifier.
    """

    def __init__(self, message: str = "Invalid security identifier"):
        super().__init__(message, status_code=400)
        self.error_code = TbErrorCode.INVALID_SECURITY


class DuplicateRecordError(TradingBotAPIException):
    """Duplicate record exception.

    Raised when attempting to insert a record that already exists in the database.
    """

    def __init__(self, message: str = "Record already exists"):
        super().__init__(message, status_code=409)
        self.error_code = "DUPLICATE_RECORD"


class ValidationError(TradingBotAPIException):
    """Validation error exception.

    Raised when data validation fails.
    """

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400)
        self.error_code = TbErrorCode.VALIDATION_FAILED
