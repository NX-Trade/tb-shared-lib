"""Pydantic schemas for Trading."""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import Field, field_validator, model_validator

from .base import BaseSchema


class TradingSignalCreate(BaseSchema):
    instrument_id: Optional[int] = None
    strategy_name: str
    strategy_cluster: Optional[str] = None
    instrument_type: Optional[str] = None  # EQUITY, FUT, CE, PE
    strategy_type: Optional[str] = None  # LONG_BUILDUP, PCR_REVERSAL, …
    strike_price: Optional[float] = None
    expiry_date: Optional[date] = None
    action: str
    timeframe: str
    entry_price: float
    target_price: float
    stop_loss: float
    confidence: float = Field(..., ge=0, le=1)
    reason: Optional[str] = None
    indicators: Optional[dict[str, Any]] = None
    metadata_: Optional[dict[str, Any]] = Field(
        default=None,
        serialization_alias="metadata",
    )
    status: Optional[str] = "ACTIVE"
    exit_price: Optional[float] = None
    outcome_time: Optional[datetime] = None
    pnl_pct: Optional[float] = None
    duration_minutes: Optional[int] = None
    duration_days: Optional[int] = None

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata_(cls, v: Any) -> Any:
        if type(v).__name__ == "MetaData":
            return None
        return v

    @model_validator(mode="before")
    @classmethod
    def resolve_orm(cls, data: Any) -> Any:
        if hasattr(data, "__table__"):
            d = {}
            for col in data.__table__.columns.keys():
                if col == "metadata":
                    d["metadata_"] = getattr(data, "metadata_", None) or {}
                else:
                    d[col] = getattr(data, col, None)
            indicators = getattr(data, "indicators", {}) or {}
            if isinstance(indicators, dict) and "symbol" in indicators and "symbol" not in d:
                d["symbol"] = indicators["symbol"]
            return d
        return data


class TradingSignalResponse(TradingSignalCreate):
    signal_id: int
    is_executed: bool
    created_at: datetime
    symbol: Optional[str] = None


class TradingOrderCreate(BaseSchema):
    instrument_id: Optional[int] = None
    strategy_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    broker_id: int
    symbol: Optional[str] = None
    trading_symbol: Optional[str] = None
    instrument_type: Optional[str] = "EQUITY"
    strike_price: Optional[float] = None
    expiry_date: Optional[date] = None
    side: str
    order_type: str
    quantity: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_stop_price: Optional[float] = None
    status: str
    parent_order_id: Optional[int] = None
    product: Optional[str] = "D"
    signal_id: Optional[int] = None


class TradingOrderResponse(TradingOrderCreate):
    order_id: int
    filled_quantity: int
    avg_fill_price: Optional[float] = None
    commission: float
    error_message: Optional[str] = None
    filled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class HoldingResponse(BaseSchema):
    holding_id: int
    broker_id: int
    account_id: Optional[int] = None
    trading_symbol: str
    underlying_symbol: Optional[str] = None
    isin: Optional[str] = None
    quantity: int
    authorized_quantity: Optional[int] = 0
    average_price: float
    last_price: Optional[float] = None
    close_price: Optional[float] = None
    pnl: Optional[float] = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PositionResponse(BaseSchema):
    trade_id: int
    broker_id: int
    account_id: Optional[int] = None
    trading_symbol: str
    underlying_symbol: Optional[str] = None
    instrument_type: Optional[str] = "EQUITY"
    product: Optional[str] = "I"
    strike_price: Optional[float] = None
    expiry_date: Optional[date] = None
    is_algo: bool = True
    quantity: int
    entry_price: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_price: Optional[float] = None
    entry_time: Optional[datetime] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    symbol: Optional[str] = None


class TradeResponse(BaseSchema):
    trade_id: int
    strategy_id: Optional[str] = None
    signal_id: Optional[int] = None
    is_algo: bool = True
    broker_id: int
    account_id: Optional[int] = None
    trading_symbol: str
    underlying_symbol: Optional[str] = None
    instrument_type: Optional[str] = None
    strike_price: Optional[float] = None
    expiry_date: Optional[date] = None
    product: str = "I"
    entry_order_id: Optional[int] = None
    exit_order_id: Optional[int] = None
    stop_order_id: Optional[int] = None
    side: str
    quantity: int
    entry_price: float
    exit_price: Optional[float] = None
    last_price: Optional[float] = None
    entry_time: datetime
    exit_time: Optional[datetime] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    unrealized_pnl: Optional[float] = 0.0
    realized_pnl: Optional[float] = None
    net_pnl: Optional[float] = None
    commission: float = 0.0
    slippage: float = 0.0
    status: str
    exit_reason: Optional[str] = None


class OptionStrategyLegCreate(BaseSchema):
    execution_order: int
    action: str  # BUY, SELL
    option_type: str  # CE, PE
    strike_price: float
    symbol: str
    entry_premium: float
    target_premium: Optional[float] = None
    stop_loss_premium: Optional[float] = None
    delta: Optional[float] = None
    theta: Optional[float] = None
    iv: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    is_hedge: bool = False


class OptionStrategyLegResponse(OptionStrategyLegCreate):
    id: int
    strategy_signal_id: int
    created_at: datetime


class OptionStrategyCreate(BaseSchema):
    signal_id: Optional[int] = None
    strategy_type: str  # BULL_CALL_SPREAD, BEAR_PUT_SPREAD, etc.
    spread_type: str  # DEBIT, CREDIT
    underlying_symbol: str
    expiry_date: date
    dte: Optional[int] = None
    lot_size: int = 1
    net_premium: float
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    breakeven_price: Optional[float] = None
    underlying_entry_price: float
    underlying_target_price: Optional[float] = None
    underlying_stop_loss: Optional[float] = None
    margin_required_approx: Optional[float] = None
    status: str = "ACTIVE"
    metadata_: Optional[dict[str, Any]] = Field(default=None, serialization_alias="metadata")
    legs: list[OptionStrategyLegCreate] = []

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata_(cls, v: Any) -> Any:
        if type(v).__name__ == "MetaData":
            return None
        return v


class OptionStrategyResponse(OptionStrategyCreate):
    id: int
    created_at: datetime
    legs: list[OptionStrategyLegResponse] = []
