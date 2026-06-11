"""Pydantic schemas for Historical Data."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import field_validator, model_validator

from .base import BaseSchema

IST = timezone(timedelta(hours=5, minutes=30))


def to_ist(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


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
    adj_close: Optional[float] = None
    volume: int
    source_id: int  # SourceEnum can be ICICI, IB, NSE

    @field_validator("timestamp", mode="before")
    @classmethod
    def localize_timestamp(cls, v: Any) -> Any:
        if isinstance(v, datetime):
            return to_ist(v)
        if isinstance(v, str):
            try:
                dt = datetime.fromisoformat(v)
                return to_ist(dt)
            except ValueError:
                pass
        return v


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
    adj_close: Optional[float] = None
    shares_traded: Optional[int] = None
    # Map shares_traded to volume for index charts compatibility on the frontend
    volume: Optional[int] = None
    turnover_cr: Optional[float] = None
    source_id: int  # SourceEnum can be ICICI, IB, NSE

    @field_validator("timestamp", mode="before")
    @classmethod
    def localize_timestamp(cls, v: Any) -> Any:
        if isinstance(v, datetime):
            return to_ist(v)
        if isinstance(v, str):
            try:
                dt = datetime.fromisoformat(v)
                return to_ist(dt)
            except ValueError:
                pass
        return v

    @model_validator(mode="after")
    def populate_volume(self) -> "HistoricalIndexDataResponse":
        # Ensure volume is set to shares_traded for frontend charts
        if self.volume is None and self.shares_traded is not None:
            self.volume = self.shares_traded
        return self


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
