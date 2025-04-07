"""Equity Related Schema."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, validator

from ...utils.common import validate_quantity
from ...utils.dtu import parse_timestamp
from .common import ChartDataBaseSchema


class EquitySchema(ChartDataBaseSchema):
    """Equity Schema."""

    id: Optional[str] = None
    security: Optional[str] = None
    identifier: Optional[str] = None
    series: Optional[str] = None
    total_traded_volume: int = 0
    total_traded_value: Optional[float] = None
    year_high: Optional[float] = None
    year_low: Optional[float] = None
    ffmc: Optional[float] = None
    on_date: date
    last_update_time: datetime
    # Fields coming from `meta`
    company_name: Optional[str] = None
    industry: Optional[str] = ""
    active_series: List[str] = []
    debt_series: List[str] = []
    temp_suspended_series: List[str] = []
    is_fno_sec: Optional[bool] = None
    is_ca_sec: Optional[bool] = None
    is_slb_sec: Optional[bool] = None
    is_debt_sec: Optional[bool] = None
    is_suspended: Optional[bool] = None
    is_etf_Sec: Optional[bool] = None
    is_delisted: Optional[bool] = None
    isin: Optional[str] = None
    is_municipal_bond: Optional[bool] = None

    @validator("total_traded_volume", pre=True)
    @classmethod
    def validate_volume(cls, v):
        return validate_quantity(v)

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "EquitySchema":
        """Create a model from NSE data format.

        Args:
            in_data: Dictionary containing NSE data
        """
        if not in_data.get("is_nse", False):
            return cls(**in_data)

        # Get common data from base class
        common_data = ChartDataBaseSchema.parse_nse_common_data(in_data)

        # Add equity-specific fields
        equity_data = {
            "series": in_data["series"],
            "company_name": in_data["companyName"],
            "industry": in_data.get("industry") or "",
            "active_series": in_data["activeSeries"],
            "debt_series": in_data["debtSeries"],
            "temp_suspended_series": in_data["tempSuspendedSeries"],
            "is_fno_sec": in_data["isFNOSec"],
            "is_ca_sec": in_data["isCASec"],
            "is_slb_sec": in_data["isSLBSec"],
            "is_debt_sec": in_data["isDebtSec"],
            "is_suspended": in_data["isSuspended"],
            "is_etf_Sec": in_data["isETFSec"],
            "is_delisted": in_data["isDelisted"],
            "isin": in_data["isin"],
            "is_municipal_bond": in_data["isMunicipalBond"],
        }

        # Merge common and equity-specific data
        all_data = {**common_data, **equity_data}

        return cls(**all_data)


class EquityResponseSchema(BaseModel):
    """Equity Response Schema."""

    equity: bool = True
    possible_keys: List[str] = []
    total_items: int
    items: List[EquitySchema] = []


class EquityRequestSchema(BaseModel):
    """Equity Request Schema."""

    security: Optional[str] = None


class AdvanceDeclineSchema(BaseModel):
    """Advance Decline Schema."""

    id: Optional[str] = None
    advances: Optional[int] = None
    declines: Optional[int] = None
    unchanged: Optional[int] = None
    timestamp: datetime
    on_date: date

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "AdvanceDeclineSchema":
        """Create a model from NSE data format.

        Args:
            in_data: Dictionary containing NSE data
        """
        timestamp: datetime = parse_timestamp(in_data["timestamp"])

        return cls(**in_data, on_date=timestamp.date(), timestamp=timestamp)


class AdvanceDeclineResponseSchema(BaseModel):
    """Advance Decline Response Schema."""

    advance_decline: bool = True
    total_items: int
    items: List[AdvanceDeclineSchema] = []


class EquityMetaSchema(BaseModel):
    """Static Equity Schema."""

    id: Optional[str] = None
    security: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    isin: Optional[str] = None
    series: Optional[str] = None
    is_fno: bool = False
    is_nifty_50: bool = False
    is_nifty_100: bool = False
    is_nifty_500: bool = False


class EquityMetaResponseSchema(BaseModel):
    """Equity Meta Response Schema."""

    equity_meta: bool = True
    total_items: int
    items: List[EquityMetaSchema] = []
