"""Pydantic schemas for Instruments."""

from datetime import datetime
from typing import Optional

from .base import BaseSchema


class InstrumentResponse(BaseSchema):
    instrument_id: int
    isin: str
    symbol: str
    ib_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    is_fno: int = 0
    is_index: int = 0
    is_nifty_50: int = 0
    is_nifty_100: int = 0
    is_nifty_500: int = 0
    created_at: datetime
    updated_at: datetime


class InstrumentCreate(BaseSchema):
    isin: str
    symbol: str
    ib_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    is_fno: int = 0
    is_index: int = 0
    is_nifty_50: int = 0
    is_nifty_100: int = 0
    is_nifty_500: int = 0


class InstrumentUpdate(BaseSchema):
    isin: Optional[str] = None
    symbol: Optional[str] = None
    ib_symbol: Optional[str] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    is_fno: Optional[int] = None
    is_index: Optional[int] = None
    is_nifty_50: Optional[int] = None
    is_nifty_100: Optional[int] = None
    is_nifty_500: Optional[int] = None
