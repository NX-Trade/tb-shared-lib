"""Pydantic schemas for Market Data."""

from datetime import date, datetime

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
    net_action: str | None = None
    net_view: str | None = None
    net_view_strength: str | None = None
    created_at: datetime


class FiiDiiDerivativesResponse(BaseSchema):
    id: int
    trade_date: date
    source: str
    instrument_type: str
    category: str
    net_oi: float | None = None
    outstanding_oi: float | None = None
    net_action: str | None = None
    net_view: str | None = None
    net_view_strength: str | None = None
    stock_net_oi: float | None = None
    stock_outstanding_oi: float | None = None
    stock_net_action: str | None = None
    stock_net_view: str | None = None
    stock_net_view_strength: str | None = None
    options_net_oi: float | None = None
    options_net_oi_change: float | None = None
    options_net_oi_change_action: str | None = None
    options_net_oi_change_view: str | None = None
    options_net_oi_change_view_strength: str | None = None
    nifty: float | None = None
    nifty_change_pct: float | None = None
    banknifty: float | None = None
    banknifty_change_pct: float | None = None
    extras: dict | None = None
    created_at: datetime


class NewsResponse(BaseSchema):
    news_id: int
    headline: str
    summary: str | None = None
    url: str | None = None
    source: str | None = None
    category: str | None = None
    symbols: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime


class MarketBreadthResponse(BaseSchema):
    ts: datetime
    exchange: str
    advances: int
    declines: int
    unchanged: int
    advance_volume: int | None = None
    decline_volume: int | None = None
    ad_ratio: float | None = None
