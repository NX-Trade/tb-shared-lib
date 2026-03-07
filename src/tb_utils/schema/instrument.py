"""Pydantic schemas for Instruments."""

from datetime import datetime

from .base import BaseSchema


class InstrumentResponse(BaseSchema):
    instrument_id: int
    isin: str
    symbol: str
    ib_symbol: str
    company_name: str | None = None
    sector: str | None = None
    is_fno: int = 0
    is_index: int = 0
    is_nifty_50: int = 0
    is_nifty_100: int = 0
    is_nifty_500: int = 0
    created_at: datetime
    updated_at: datetime
