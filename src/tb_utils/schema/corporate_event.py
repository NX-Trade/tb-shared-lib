"""Pydantic schemas for Corporate Events and Trading Holidays."""

from datetime import datetime

from .base import BaseSchema


class CorporateEventResponse(BaseSchema):
    event_id: int
    symbol: str
    company_name: str | None = None
    event_type: str
    event_date: datetime
    ex_date: datetime | None = None
    record_date: datetime | None = None
    description: str | None = None
    subject: str | None = None
    isin: str | None = None
    created_at: datetime
    updated_at: datetime


class TradingHolidayResponse(BaseSchema):
    holiday_id: int
    holiday_date: datetime
    holiday_name: str
    holiday_type: str
    week_day: str | None = None
    created_at: datetime
