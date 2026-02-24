"""Pydantic schemas for Market Data."""

from datetime import date, datetime
from typing import Optional

from .base import BaseSchema


class FiiDiiResponse(BaseSchema):
    fiidii_id: int
    trade_date: date
    category: str
    segment: str
    buy_value: float
    sell_value: float
    net_value: float
    created_at: datetime


class NewsResponse(BaseSchema):
    news_id: int
    headline: str
    summary: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    symbols: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime


class MarketBreadthResponse(BaseSchema):
    ts: datetime
    exchange: str
    advances: int
    declines: int
    unchanged: int
    advance_volume: Optional[int] = None
    decline_volume: Optional[int] = None
    ad_ratio: Optional[float] = None
