"""Pydantic schemas for Historical Data."""

from datetime import datetime

from .base import BaseSchema


class HistoricalEquityDataResponse(BaseSchema):
    historical_equity_data_id: int
    instrument_id: int
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int
    source_id: int  # SourceEnum can be ICICI, IB, NSE


class HistoricalIndexDataResponse(BaseSchema):
    historical_index_data_id: int
    instrument_id: int
    symbol: str
    timeframe: str
    timestamp: datetime
    index_name: str
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    source_id: int  # SourceEnum can be ICICI, IB, NSE


class CandleResponse(BaseSchema):
    ts: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None
    source: str


class OptionChainResponse(BaseSchema):
    ts: datetime
    symbol: str
    expiry_date: datetime
    strike_price: float
    option_type: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    ltp: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    change_in_oi: int | None = None
    implied_vol: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    bid_qty: int | None = None
    ask_qty: int | None = None
    source: str
