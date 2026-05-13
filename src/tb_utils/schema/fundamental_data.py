"""Pydantic schemas for Fundamental Data."""

from datetime import datetime
from typing import Optional

from .base import BaseSchema


class FundamentalDataResponse(BaseSchema):
    """Response schema for instrument fundamental data."""

    fundamental_id: int
    instrument_id: Optional[int] = None
    symbol: str
    pe_ratio: Optional[float] = None
    beta: Optional[float] = None
    dividend_yield: Optional[float] = None
    market_cap: Optional[int] = None
    eps: Optional[float] = None
    roe: Optional[float] = None
    report_xml: Optional[str] = None
    fetched_at: datetime
    updated_at: datetime
