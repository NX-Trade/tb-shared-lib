"""Pydantic schemas for Fundamental Data."""

from datetime import datetime

from .base import BaseSchema


class FundamentalDataResponse(BaseSchema):
    """Response schema for instrument fundamental data."""

    fundamental_id: int
    instrument_id: int | None = None
    symbol: str
    pe_ratio: float | None = None
    beta: float | None = None
    dividend_yield: float | None = None
    market_cap: int | None = None
    eps: float | None = None
    roe: float | None = None
    report_xml: str | None = None
    fetched_at: datetime
    updated_at: datetime
