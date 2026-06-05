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


class IndiaVIXResponse(BaseSchema):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    prev_close: Optional[float] = None
    change: Optional[float] = None
    pct_change: Optional[float] = None


class FuturesOIResponse(BaseSchema):
    timestamp: datetime
    symbol: str
    expiry_date: date
    open_interest: int
    change_in_oi: int
    volume: int
    close: float


class ParticipantOIResponse(BaseSchema):
    trade_date: date
    category: str
    source: str
    futures_idx_long: int
    futures_idx_short: int
    futures_idx_net: int
    futures_idx_outstanding: int
    futures_stk_long: int
    futures_stk_short: int
    futures_stk_net: int
    futures_stk_outstanding: int
    option_call_long_oi: int
    option_call_long_oi_change: int
    option_call_short_oi: int
    option_call_short_oi_change: int
    option_call_net_oi: int
    option_call_net_oi_change: int
    option_put_long_oi: int
    option_put_long_oi_change: int
    option_put_short_oi: int
    option_put_short_oi_change: int
    option_put_net_oi: int
    option_put_net_oi_change: int
    option_overall_net_oi: int
    option_overall_net_oi_change: int
    nifty_fut_net_oi: int
    banknifty_fut_net_oi: int
    finnifty_fut_net_oi: int
    midcpnifty_fut_net_oi: int
    niftynxt50_fut_net_oi: int
    futures_net_view: Optional[str] = None
    futures_net_action: Optional[str] = None
    futures_stk_net_view: Optional[str] = None
    futures_stk_net_action: Optional[str] = None
    options_net_view: Optional[str] = None
    options_net_action: Optional[str] = None
    nifty_close: Optional[float] = None
    banknifty_close: Optional[float] = None
    extras: Optional[dict] = None
    created_at: datetime


class DeliveryDataResponse(BaseSchema):
    timestamp: datetime
    symbol: str
    traded_qty: int
    deliverable_qty: int
    delivery_pct: float
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


class BlockDealResponse(BaseSchema):
    id: int
    date: date
    symbol: str
    security_name: Optional[str] = None
    client_name: Optional[str] = None
    buy_sell: Optional[str] = None
    quantity_traded: Optional[int] = None
    trade_price: Optional[float] = None
    remarks: Optional[str] = None
    created_at: datetime


class BulkDealResponse(BaseSchema):
    id: int
    date: date
    symbol: str
    security_name: Optional[str] = None
    client_name: Optional[str] = None
    buy_sell: Optional[str] = None
    quantity_traded: Optional[int] = None
    trade_price: Optional[float] = None
    remarks: Optional[str] = None
    created_at: datetime


class Nifty500SmaBreadthResponse(BaseSchema):
    trade_date: date
    total_stocks: int
    above_20_sma: int
    above_50_sma: int
    above_200_sma: int
