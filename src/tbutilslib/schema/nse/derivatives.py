"""Derivatives Related Schema."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from ...utils.common import validate_quantity
from ...utils.dtu import change_date_format, parse_timestamp, str_to_date
from ...utils.enums import DateFormatEnum


class CumulativeDerivativesSchema(BaseModel):
    """Cumulative Derivatives Schema."""

    id: Optional[str] = None
    security: str
    spot_price: float
    future_price: float = 0.0
    total_open_interest_ce: float
    total_volume_ce: float
    total_open_interest_pe: float
    total_volume_pe: float
    pcr_open_interest: float
    pcr_volume: float
    total_open_interest_fut: int
    total_volume_fut: int
    expiry_date: date
    on_date: date
    timestamp: datetime

    @validator(
        "spot_price",
        "future_price",
        "total_open_interest_ce",
        "total_volume_ce",
        "total_open_interest_pe",
        "total_volume_pe",
        "pcr_open_interest",
        "pcr_volume",
        "total_open_interest_fut",
        "total_volume_fut",
        pre=True,
    )
    @classmethod
    def validate_numeric_fields(cls, v):
        return validate_quantity(v)

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "CumulativeDerivativesSchema":
        """Create model from NSE data format."""
        if not in_data.get("is_nse"):
            return cls(**in_data)

        timestamp: datetime = parse_timestamp(in_data["timestamp"])

        expiry_date_str = None
        if "expiry_date" in in_data:
            expiry_date_obj: date = str_to_date(
                in_data["expiry_date"], DateFormatEnum.NSE_DATE.value
            )
            expiry_date_str = change_date_format(
                expiry_date_obj, DateFormatEnum.TB_DATE.value
            )

        return cls(
            security=in_data["security"],
            spot_price=in_data["spot_price"],
            future_price=in_data["future_price"],
            total_open_interest_ce=in_data["total_open_interest_ce"],
            total_volume_ce=in_data["total_volume_ce"],
            total_open_interest_pe=in_data["total_open_interest_pe"],
            total_volume_pe=in_data["total_volume_pe"],
            pcr_open_interest=in_data["pcr_open_interest"],
            pcr_volume=in_data["pcr_volume"],
            total_open_interest_fut=in_data["total_open_interest_fut"],
            total_volume_fut=in_data["total_volume_fut"],
            expiry_date=expiry_date_str,
            on_date=change_date_format(timestamp.date(), DateFormatEnum.TB_DATE.value),
            timestamp=timestamp,
        )


class CumulativeDerivativesResponseSchema(BaseModel):
    """Cumulative Derivatives Response Schema."""

    cumulative: bool = True
    security: Optional[str] = None
    total_items: int
    possible_keys: List[str] = []
    items: List[CumulativeDerivativesSchema] = []


class CumulativeRequestSchema(BaseModel):
    """Cumulative Derivatives Request Schema."""

    security: Optional[str] = None


class DerivativesSchemaCommonFields(BaseModel):
    """Derivatives Common Fields."""

    id: Optional[str] = None
    security: str
    identifier: str
    option_type: Optional[str] = None
    last_price: Optional[float] = None
    open_interest: Optional[int] = None
    implied_volatility: Optional[float] = None
    change_in_open_interest: Optional[int] = None
    p_change_in_open_interest: Optional[float] = None
    change: Optional[float] = None
    p_change: Optional[float] = None
    strike_price: Optional[float] = None
    traded_volume: Optional[int] = None
    spot_price: Optional[float] = None
    expiry_date: date
    on_date: date
    timestamp: datetime

    @validator("open_interest", "traded_volume", pre=True)
    @classmethod
    def validate_integer_fields(cls, v):
        if v is not None:
            return validate_quantity(v)
        return v

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "DerivativesSchemaCommonFields":
        """Create model from NSE data format."""
        if not in_data.get("is_nse"):
            return cls(**in_data)

        timestamp: datetime = parse_timestamp(in_data["timestamp"])

        expiry_date_str = None
        if "expiry_date" in in_data:
            expiry_date_obj: date = str_to_date(
                in_data["expiry_date"], DateFormatEnum.NSE_DATE.value
            )
            expiry_date_str = change_date_format(
                expiry_date_obj, DateFormatEnum.TB_DATE.value
            )

        return cls(
            security=in_data["security"],
            identifier=in_data["identifier"],
            option_type=in_data.get("option_type"),
            last_price=in_data.get("last_price"),
            open_interest=in_data.get("open_interest"),
            implied_volatility=in_data.get("implied_volatility"),
            change_in_open_interest=in_data.get("change_in_open_interest"),
            p_change_in_open_interest=in_data.get("p_change_in_open_interest"),
            change=in_data.get("change"),
            p_change=in_data.get("p_change"),
            strike_price=in_data.get("strike_price"),
            traded_volume=in_data.get("traded_volume"),
            spot_price=in_data.get("spot_price"),
            expiry_date=expiry_date_str,
            on_date=change_date_format(timestamp.date(), DateFormatEnum.TB_DATE.value),
            timestamp=timestamp,
        )


class DerivativesSchemaResponseCommonFields(BaseModel):
    """Derivatives Response Schema."""

    derivatives: bool = True
    security: Optional[str] = None
    total_items: int
    possible_keys: List[str] = []


class IndexDerivativesSchema(DerivativesSchemaCommonFields):
    """Index Derivatives Schema."""

    instrument_type: Optional[str] = None
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    settle_price: Optional[float] = None
    prev_close: Optional[float] = None
    total_buy_quantity: Optional[int] = None
    total_sell_quantity: Optional[int] = None
    total_traded_value: Optional[float] = None
    total_traded_volume: Optional[int] = None
    underlying_value: Optional[float] = None
    market_lot: Optional[int] = None
    market_wide_position_limits: Optional[int] = None
    client_wise_position_limits: Optional[int] = None
    market_type: Optional[str] = None

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "IndexDerivativesSchema":
        """Create model from NSE data format."""
        if not in_data.get("is_nse"):
            return cls(**in_data)

        # First get the common fields
        base_data = super().from_nse_data(in_data)
        base_dict = base_data.dict()

        # Add the specific fields for this schema
        additional_fields = {
            "instrument_type": in_data.get("instrumentType"),
            "open_price": in_data.get("openPrice"),
            "high_price": in_data.get("highPrice"),
            "low_price": in_data.get("lowPrice"),
            "close_price": in_data.get("closePrice"),
            "settle_price": in_data.get("settlePrice"),
            "prev_close": in_data.get("prevClose"),
            "total_buy_quantity": in_data.get("totalBuyQuantity"),
            "total_sell_quantity": in_data.get("totalSellQuantity"),
            "total_traded_value": in_data.get("totalTradedValue"),
            "total_traded_volume": in_data.get("totalTradedVolume"),
            "underlying_value": in_data.get("underlyingValue"),
            "market_lot": in_data.get("marketLot"),
            "market_wide_position_limits": in_data.get("marketWidePositionLimits"),
            "client_wise_position_limits": in_data.get("clientWisePositionLimits"),
            "market_type": in_data.get("marketType"),
        }

        return cls(**{**base_dict, **additional_fields})


class EquityDerivativesSchema(DerivativesSchemaCommonFields):
    """Equity Derivatives Schema."""


class IndexDerivativesResponseSchema(DerivativesSchemaResponseCommonFields):
    """Index Derivatives Response Schema."""

    items: List[IndexDerivativesSchema] = []


class EquityDerivativesResponseSchema(DerivativesSchemaResponseCommonFields):
    """Equity Derivatives Response Schema."""

    items: List[EquityDerivativesSchema] = []


class IndexRequestSchema(BaseModel):
    """Index Derivatives Request Schema."""

    security: str


class EquityRequestSchema(BaseModel):
    """Equity Derivatives Request Schema."""

    security: str


class HistoricalDerivativesSchema(BaseModel):
    """Historical Derivatives Schema."""

    id: Optional[str] = None
    security: str
    instrument: Optional[str] = None
    market_type: Optional[str] = None
    market_lot: Optional[int] = None
    option_type: Optional[str] = None
    strike_price: Optional[float] = None
    open_price: Optional[float] = None
    close_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    last_price: Optional[float] = None
    settle_price: Optional[float] = None
    prev_close_price: Optional[float] = None
    traded_volume: Optional[int] = None
    traded_value: Optional[float] = None
    premium_value: Optional[float] = None
    open_interest: Optional[int] = None
    change_in_oi: Optional[int] = None
    position_type: Optional[str] = None
    on_date: date
    expiry_date: date
    timestamp: datetime

    @validator("traded_volume", "open_interest", "change_in_oi", "market_lot", pre=True)
    @classmethod
    def validate_integer_fields(cls, v):
        if v is not None:
            return validate_quantity(v)
        return v

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "HistoricalDerivativesSchema":
        """Create model from NSE data format."""
        if not in_data.get("is_nse"):
            return cls(**in_data)

        timestamp: datetime = parse_timestamp(in_data["timestamp"])
        on_date_str = change_date_format(timestamp.date(), DateFormatEnum.TB_DATE.value)

        expiry_date_obj: date = str_to_date(
            in_data["expiryDate"], DateFormatEnum.NSE_DATE.value
        )
        expiry_date_str = change_date_format(
            expiry_date_obj, DateFormatEnum.TB_DATE.value
        )

        data = {
            "security": in_data["security"],
            "instrument": in_data["instrument"],
            "market_type": in_data["marketType"],
            "market_lot": in_data["marketLot"],
            "option_type": in_data["optionType"],
            "strike_price": in_data["strikePrice"],
            "open_price": in_data["openPrice"],
            "close_price": in_data["closePrice"],
            "high_price": in_data["highPrice"],
            "low_price": in_data["lowPrice"],
            "last_price": in_data["lastPrice"],
            "settle_price": in_data["settlePrice"],
            "prev_close_price": in_data["prevClosePrice"],
            "traded_volume": in_data["tradedVolume"] or 0,
            "traded_value": in_data["tradedValue"],
            "premium_value": in_data["premiumValue"],
            "open_interest": in_data["openInterest"],
            "change_in_oi": in_data["changeInOI"],
            "position_type": in_data["positionType"],
            "on_date": on_date_str,
            "expiry_date": expiry_date_str,
            "timestamp": timestamp,
        }

        # Adjust market lot calculations
        market_lot = data["market_lot"]
        if market_lot and market_lot != 0:
            data["change_in_oi"] = int(data["change_in_oi"] / market_lot)
            data["open_interest"] = int(data["open_interest"] / market_lot)

        return cls(**data)


class HistoricalDerivativesResponseSchema(BaseModel):
    """Historical Derivatives Response Schema."""

    derivatives: bool = True
    security: Optional[str] = None
    total_items: int
    possible_keys: List[str] = []
    items: List[HistoricalDerivativesSchema] = []


class ExpiryDatesResponseSchema(BaseModel):
    """Expiry Dates Response Schema."""

    expiry_dates: bool = True
    security: Optional[str] = None
    total_items: int
    possible_keys: List[str] = []
    items: List[date] = []


class OptionMetaDataSchema(BaseModel):
    """Security in Focus Schema."""

    id: Optional[str] = None
    security: str
    strike_prices: List[int] = []
    is_fno: bool = False
    on_date: date = Field(default_factory=date.today)
    expiry_dates: List[date] = []
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "OptionMetaDataSchema":
        """Create model from NSE data format."""
        if not in_data.get("is_nse", False):
            return cls(**in_data)

        timestamp: datetime = parse_timestamp(in_data["timestamp"])

        updated_expiry_dates = []
        if "expiry_dates" in in_data:
            for exp in in_data["expiry_dates"]:
                ed = str_to_date(exp, DateFormatEnum.NSE_DATE.value)
                updated_expiry_dates.append(ed)

        return cls(
            security=in_data["security"],
            strike_prices=in_data["strike_prices"],
            expiry_dates=updated_expiry_dates,
            is_fno=in_data.get("is_fno", False),
            on_date=timestamp.date(),
            timestamp=timestamp,
        )


class OptionMetaDataResponseSchema(BaseModel):
    """Security in Focus Response Schema."""

    option_meta_data: bool = True
    total_items: int
    securities: List[str] = []
    items: List[OptionMetaDataSchema] = []
