"""Pydantic schemas for Market Data."""

from datetime import date, datetime
from typing import Optional

from .base import BaseSchema


class FiiDiiResponse(BaseSchema):
    fiidii_id: int
    trade_date: date
    source: str
    category: str
    segment: str
    buy_value: float
    sell_value: float
    net_value: float
    net_action: Optional[str] = None
    net_view: Optional[str] = None
    net_view_strength: Optional[str] = None
    created_at: datetime


class FiiDiiDerivativesResponse(BaseSchema):
    id: int
    trade_date: date
    source: str
    instrument_type: str
    category: str
    net_oi: Optional[float] = None
    outstanding_oi: Optional[float] = None
    net_action: Optional[str] = None
    net_view: Optional[str] = None
    net_view_strength: Optional[str] = None
    stock_net_oi: Optional[float] = None
    stock_outstanding_oi: Optional[float] = None
    stock_net_action: Optional[str] = None
    stock_net_view: Optional[str] = None
    stock_net_view_strength: Optional[str] = None
    options_net_oi: Optional[float] = None
    options_net_oi_change: Optional[float] = None
    options_net_oi_change_action: Optional[str] = None
    options_net_oi_change_view: Optional[str] = None
    options_net_oi_change_view_strength: Optional[str] = None
    nifty: Optional[float] = None
    nifty_change_pct: Optional[float] = None
    banknifty: Optional[float] = None
    banknifty_change_pct: Optional[float] = None
    extras: Optional[dict] = None
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
