"""Equity Related Schema."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, validator

from ...utils.common import validate_quantity
from ...utils.dtu import parse_timestamp, str_to_date
from ...utils.enums import DateFormatEnum
from .common import ChartDataBaseSchema


class IndexSchema(ChartDataBaseSchema):
    """Index Schema."""

    id: Optional[str] = None
    security: str
    identifier: str
    ffmc: Optional[float] = None
    year_high: Optional[float] = None
    year_low: Optional[float] = None
    total_traded_volume: int = 0
    total_traded_value: Optional[float] = None

    last_update_time: datetime
    on_date: date

    @validator("total_traded_volume", pre=True)
    @classmethod
    def validate_volume(cls, v):
        return validate_quantity(v)

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "IndexSchema":
        """Create a model from NSE data format.

        Args:
            in_data: Dictionary containing NSE data
        """
        if not in_data.get("is_nse", False):
            return cls(**in_data)

        timestamp: datetime = parse_timestamp(in_data["timestamp"])
        last_update_time: datetime = parse_timestamp(in_data["lastUpdateTime"])

        date_30d_ago_obj = str_to_date(
            in_data["date30dAgo"], DateFormatEnum.NSE_DATE.value
        )
        date_365d_ago_obj = str_to_date(
            in_data["date365dAgo"], DateFormatEnum.NSE_DATE.value
        )

        return cls(
            security=in_data["symbol"],
            identifier=in_data["identifier"],
            open=float(in_data["open"]),
            day_high=float(in_data["dayHigh"]),
            day_low=float(in_data["dayLow"]),
            last_price=float(in_data["lastPrice"]),
            previous_close=float(in_data["previousClose"]),
            change=float(in_data["change"]),
            p_change=float(in_data["pChange"]),
            ffmc=float(in_data["ffmc"]),
            year_high=float(in_data["yearHigh"]),
            year_low=float(in_data["yearLow"]),
            total_traded_volume=int(in_data["totalTradedVolume"]),
            total_traded_value=float(in_data["totalTradedValue"]),
            near_weak_high=float(in_data["nearWkHigh"]),
            near_weak_low=float(in_data["nearWkLow"]),
            per_change_30d=float(in_data["perChange30d"]),
            per_change_365d=float(in_data["perChange365d"]),
            chart_30d_path=in_data["chart30dPath"],
            chart_today_path=in_data["chartTodayPath"],
            chart_365d_path=in_data["chart365dPath"],
            date_30d_ago=date_30d_ago_obj,
            date_365d_ago=date_365d_ago_obj,
            timestamp=timestamp,
            last_update_time=last_update_time,
            on_date=timestamp.date(),
        )


class IndexResponseSchema(BaseModel):
    """Index Response Schema."""

    index: bool = True
    possible_keys: List[str] = []
    total_items: int
    items: List[IndexSchema] = []


class IndexRequestSchema(BaseModel):
    """Index Request Schema."""

    security: Optional[str] = None
