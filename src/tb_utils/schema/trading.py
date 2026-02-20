"""Pydantic schemas for Trading."""

from datetime import datetime
from typing import Optional, Any
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
    reason: Optional[str] = None
    indicators: Optional[dict[str, Any]] = None
    metadata_: Optional[dict[str, Any]] = Field(default=None, alias="metadata")


class TradingSignalResponse(TradingSignalCreate):
    signal_id: int
    is_executed: bool
    created_at: datetime


class TradingOrderCreate(BaseSchema):
    instrument_id: int
    strategy_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    broker_id: int
    symbol: Optional[str] = None
    side: str
    order_type: str
    quantity: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_stop_price: Optional[float] = None
    status: str
    parent_order_id: Optional[int] = None


class TradingOrderResponse(TradingOrderCreate):
    order_id: int
    filled_quantity: int
    avg_fill_price: Optional[float] = None
    commission: float
    filled_at: Optional[datetime] = None
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
    strategy_id: Optional[str] = None
    instrument_id: int
    broker_id: int
    entry_order_id: Optional[int] = None
    exit_order_id: Optional[int] = None
    side: str
    quantity: int
    entry_price: float
    exit_price: Optional[float] = None
    entry_time: datetime
    exit_time: Optional[datetime] = None
    realized_pnl: Optional[float] = None
    commission: float
    slippage: float
    status: str
