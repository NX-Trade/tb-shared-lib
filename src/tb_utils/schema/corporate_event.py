"""Pydantic schemas for Corporate Events and Trading Holidays."""

from datetime import datetime
from typing import Optional
from .base import BaseSchema


class CorporateEventResponse(BaseSchema):
    event_id: int
    symbol: str
    company_name: Optional[str] = None
    event_type: str
    event_date: datetime
    ex_date: Optional[datetime] = None
    record_date: Optional[datetime] = None
    description: Optional[str] = None
    subject: Optional[str] = None
    isin: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TradingHolidayResponse(BaseSchema):
    holiday_id: int
    holiday_date: datetime
    holiday_name: str
    holiday_type: str
    week_day: Optional[str] = None
    created_at: datetime
