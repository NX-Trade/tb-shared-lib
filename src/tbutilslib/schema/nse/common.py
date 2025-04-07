"""Common schema models for NSE data.

This module contains common schema models that are shared across
multiple NSE data types to reduce code duplication.
"""

from datetime import date, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel

from ...utils.dtu import parse_timestamp, str_to_date
from ...utils.enums import DateFormatEnum


class PriceDataBaseSchema(BaseModel):
    """Base schema for price data common to equity and indexes."""

    open: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    last_price: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    p_change: Optional[float] = None


class ChartDataBaseSchema(PriceDataBaseSchema):
    """Base schema for chart data common to equity and indexes."""

    near_weak_high: Optional[float] = None
    near_weak_low: Optional[float] = None
    per_change_30d: Optional[float] = None
    per_change_365d: Optional[float] = None
    chart_30d_path: Optional[str] = None
    chart_today_path: Optional[str] = None
    chart_365d_path: Optional[str] = None
    date_30d_ago: Optional[date] = None
    date_365d_ago: Optional[date] = None
    timestamp: datetime
    last_update_time: Optional[datetime] = None
    on_date: Optional[date] = None

    @classmethod
    def parse_nse_common_data(cls, in_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse common NSE data fields.

        Args:
            in_data: Dictionary containing NSE data

        Returns:
            Dictionary with parsed common fields
        """
        if not in_data.get("is_nse", False):
            return in_data

        timestamp: datetime = parse_timestamp(in_data["timestamp"])
        last_update_time: datetime = parse_timestamp(in_data["lastUpdateTime"])

        date_30d_ago_obj: date = str_to_date(
            in_data["date30dAgo"], DateFormatEnum.NSE_DATE.value
        )

        date_365d_ago_obj: date = str_to_date(
            in_data["date365dAgo"], DateFormatEnum.NSE_DATE.value
        )

        # Common price data fields
        common_data = {
            "security": in_data["symbol"],
            "identifier": in_data["identifier"],
            "open": float(in_data["open"]),
            "day_high": float(in_data["dayHigh"]),
            "day_low": float(in_data["dayLow"]),
            "last_price": float(in_data["lastPrice"]),
            "previous_close": float(in_data["previousClose"]),
            "change": float(in_data["change"]),
            "p_change": float(in_data["pChange"]),
            "total_traded_volume": int(in_data["totalTradedVolume"]),
            "total_traded_value": float(in_data["totalTradedValue"]),
            "year_high": float(in_data["yearHigh"]),
            "year_low": float(in_data["yearLow"]),
            "ffmc": float(in_data["ffmc"]),
        }

        # Common chart data fields
        chart_data = {
            "near_weak_high": float(
                in_data.get("nearWKH", in_data.get("nearWkHigh", 0))
            ),
            "near_weak_low": float(in_data.get("nearWKL", in_data.get("nearWkLow", 0))),
            "per_change_30d": float(in_data["perChange30d"]),
            "per_change_365d": float(in_data["perChange365d"]),
            "chart_30d_path": in_data["chart30dPath"],
            "chart_today_path": in_data["chartTodayPath"],
            "chart_365d_path": in_data["chart365dPath"],
            "date_30d_ago": date_30d_ago_obj,
            "date_365d_ago": date_365d_ago_obj,
            "timestamp": timestamp,
            "last_update_time": last_update_time,
            "on_date": timestamp.date(),
        }

        # Merge dictionaries
        common_data.update(chart_data)

        return common_data
