"""Pydantic schemas for NSE Reference Data."""

from datetime import date, datetime
from typing import Optional

from .base import BaseSchema


class NseIndexResponse(BaseSchema):
    id: int
    category: str
    index_name: str
    index_symbol: str
    constituent_url: Optional[str] = None
    factsheet_url: Optional[str] = None
    is_active: int
    created_at: datetime


class IndexConstituentResponse(BaseSchema):
    id: int
    index_category: str
    index_name: str
    symbol: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    isin: Optional[str] = None
    series: Optional[str] = None
    as_of_date: date
    created_at: datetime


class FnoExpiryResponse(BaseSchema):
    id: int
    instrument_type: str
    underlying_symbol: Optional[str] = None
    expiry_date: date
    is_active: int
    created_at: datetime


class FnoBanListResponse(BaseSchema):
    id: int
    trade_date: date
    symbol: str
    created_at: datetime

