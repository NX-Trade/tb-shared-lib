"""Pydantic schemas for Trading."""

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import BaseSchema


class TradingSignalCreate(BaseSchema):
    instrument_id: int
    strategy_name: str
    action: str
    timeframe: str
    entry_price: float
    target_price: float
    stop_loss: float
    confidence: float = Field(..., ge=0, le=1)
    reason: str | None = None
    indicators: dict[str, Any] | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")


class TradingSignalResponse(TradingSignalCreate):
    signal_id: int
    is_executed: bool
    created_at: datetime


class TradingOrderCreate(BaseSchema):
    instrument_id: int
    strategy_id: str | None = None
    broker_order_id: str | None = None
    broker_id: int
    symbol: str | None = None
    side: str
    order_type: str
    quantity: int
    limit_price: float | None = None
    stop_price: float | None = None
    trail_stop_price: float | None = None
    status: str
    parent_order_id: int | None = None


class TradingOrderResponse(TradingOrderCreate):
    order_id: int
    filled_quantity: int
    avg_fill_price: float | None = None
    commission: float
    filled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PositionResponse(BaseSchema):
    position_id: int
    instrument_id: int
    broker_id: int
    net_quantity: int
    average_price: float
    realized_pnl: float
    unrealized_pnl: float
    last_updated_at: datetime


class TradeResponse(BaseSchema):
    trade_id: int
    strategy_id: str | None = None
    instrument_id: int
    broker_id: int
    entry_order_id: int | None = None
    exit_order_id: int | None = None
    side: str
    quantity: int
    entry_price: float
    exit_price: float | None = None
    entry_time: datetime
    exit_time: datetime | None = None
    realized_pnl: float | None = None
    commission: float
    slippage: float
    status: str
