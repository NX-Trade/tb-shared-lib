"""Pydantic schemas for Historical Data."""

from datetime import datetime
from typing import Optional

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
    shares_traded: Optional[int] = None
    turnover_cr: Optional[float] = None
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
    vwap: Optional[float] = None
    source: str


class OptionChainResponse(BaseSchema):
    ts: datetime
    symbol: str
    expiry_date: datetime
    strike_price: float
    option_type: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    ltp: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    change_in_oi: Optional[int] = None
    implied_vol: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    bid_qty: Optional[int] = None
    ask_qty: Optional[int] = None
    underlying_value: Optional[float] = None
    source: str


class OptionChainMetrics(BaseSchema):
    max_ce_oi: float
    max_pe_oi: float
    max_ce_chg_oi: float
    max_pe_chg_oi: float
    ce_itm_oi: float
    pe_itm_oi: float
    max_pain_strike: float
    max_ce_strike: float
    max_pe_strike: float


class StrikeDataPoint(BaseSchema):
    strike: float
    pcr: float
    pain: float
    ce: Optional[OptionChainResponse] = None
    pe: Optional[OptionChainResponse] = None


class PcrHistoryPoint(BaseSchema):
    timestamp: str
    pcr: float
    put_oi: float
    call_oi: float


class OptionChainAnalysisResponse(BaseSchema):
    expiries: list[str]
    selected_expiry: str
    spot_price: float
    metrics: Optional[OptionChainMetrics] = None
    strikes_data: list[StrikeDataPoint]
    pcr_history: list[PcrHistoryPoint]
