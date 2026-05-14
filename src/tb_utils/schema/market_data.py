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


class NewsCreate(BaseSchema):
    """Schema for creating a news headline."""

    headline: str
    summary: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    symbols: Optional[str] = None
    published_at: Optional[datetime] = None


class NewsUpdate(BaseSchema):
    """Schema for partial-updating a news headline."""

    headline: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    symbols: Optional[str] = None
    published_at: Optional[datetime] = None


class MarketBreadthResponse(BaseSchema):
    ts: datetime
    exchange: str
    advances: int
    declines: int
    unchanged: int
    advance_volume: Optional[int] = None
    decline_volume: Optional[int] = None
    ad_ratio: Optional[float] = None


# ── Live Redis Responses ─────────────────────────────────────────────────


class SpotPriceResponse(BaseSchema):
    """Response schema for real-time spot price fetched from Redis."""

    symbol: str
    price: float
    change: Optional[float] = None
    p_change: Optional[float] = None
    updated_at: datetime


class DerivativeMetricsResponse(BaseSchema):
    """Response schema for Options calculated metrics fetched from Redis."""

    symbol: str
    spot_price: float
    pcr: Optional[float] = None
    max_pain: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    total_ce_oi: float = 0.0
    total_pe_oi: float = 0.0
    updated_at: datetime


class MarketBreadthLiveResponse(BaseSchema):
    """Response schema for live Market Breadth fetched from Redis."""

    exchange: str
    advances: int
    declines: int
    unchanged: int
    ad_ratio: Optional[float] = None
    updated_at: datetime


class DerivativeTickResponse(BaseSchema):
    """Response schema for high-frequency tick data."""

    id: int
    timestamp: datetime
    symbol: str
    contract_type: str
    strike: Optional[float] = None
    expiry: date
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    implied_vol: Optional[float] = None
    created_at: datetime
