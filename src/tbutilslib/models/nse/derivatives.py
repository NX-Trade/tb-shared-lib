"""Derivatives Related Collection."""
from copy import deepcopy
from datetime import date, datetime

from mongoengine import fields as mongoFields

from ...config import MongoConfig
from ...utils.enums import DateFormatEnum
from ..base import BASE_META, BaseCollection


class CumulativeDerivativesCollection(BaseCollection):
    """CUMULATIVE_DERIVATIVES collection."""

    security = mongoFields.StringField(required=True)
    spot_price = mongoFields.FloatField()
    future_price = mongoFields.FloatField(default=0)
    total_open_interest_ce = mongoFields.FloatField()
    total_volume_ce = mongoFields.FloatField()
    total_open_interest_pe = mongoFields.FloatField()
    total_volume_pe = mongoFields.FloatField()
    pcr_open_interest = mongoFields.FloatField()
    pcr_volume = mongoFields.FloatField()
    total_open_interest_fut = mongoFields.IntField()
    total_volume_fut = mongoFields.IntField()
    timestamp = mongoFields.DateTimeField(format=DateFormatEnum.FULL_TS.value)
    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    expiry_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.CUMULATIVE_DERIVATIVES


class DerivativesCommonFields:
    """Derivatives Common Fields for collection."""

    security = mongoFields.StringField(required=True)
    identifier = mongoFields.StringField(required=True)
    option_type = mongoFields.StringField()
    last_price = mongoFields.FloatField()
    open_interest = mongoFields.IntField()
    implied_volatility = mongoFields.FloatField()
    change_in_open_interest = mongoFields.IntField()
    p_change_in_open_interest = mongoFields.FloatField()
    change = mongoFields.FloatField()
    p_change = mongoFields.FloatField()
    strike_price = mongoFields.FloatField()
    traded_volume = mongoFields.IntField()
    spot_price = mongoFields.FloatField()
    expiry_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    timestamp = mongoFields.DateTimeField(format=DateFormatEnum.FULL_TS.value)


class IndexDerivativesCollection(BaseCollection, DerivativesCommonFields):
    """INDEX_DERIVATIVES collection."""

    instrument_type = mongoFields.StringField()
    open_price = mongoFields.FloatField()
    high_price = mongoFields.FloatField()
    low_price = mongoFields.FloatField()
    close_price = mongoFields.FloatField()
    prev_close = mongoFields.FloatField()
    number_of_contracts_traded = mongoFields.IntField()
    total_turnover = mongoFields.FloatField()
    value = mongoFields.FloatField()
    vmap = mongoFields.FloatField()
    premium_turnover = mongoFields.FloatField()
    market_lot = mongoFields.IntField()
    settlement_price = mongoFields.FloatField()
    daily_volatility = mongoFields.FloatField()
    annualised_volatility = mongoFields.FloatField()
    client_wise_position_limits = mongoFields.IntField()
    market_wide_position_limits = mongoFields.IntField()
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.INDEX_DERIVATIVES


class EquityDerivatesCollection(BaseCollection, DerivativesCommonFields):
    """EQUITY_DERIVATIVES collection."""

    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.EQUITY_DERIVATIVES


class HistoricalDerivatesCollection(BaseCollection):
    """HISTORICAL_DERIVATIVES collection."""

    security = mongoFields.StringField(required=True)
    instrument = mongoFields.StringField()
    market_type = mongoFields.StringField()
    market_lot = mongoFields.IntField()
    option_type = mongoFields.StringField()
    strike_price = mongoFields.FloatField()
    open_price = mongoFields.FloatField()
    close_price = mongoFields.FloatField()
    high_price = mongoFields.FloatField()
    low_price = mongoFields.FloatField()
    last_price = mongoFields.FloatField()
    settle_price = mongoFields.FloatField()
    prev_close_price = mongoFields.FloatField()
    traded_volume = mongoFields.IntField()
    traded_value = mongoFields.IntField()
    premium_value = mongoFields.FloatField()
    open_interest = mongoFields.IntField()
    change_in_open_interest = mongoFields.IntField()
    position_type = mongoFields.StringField()
    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    expiry_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    timestamp = mongoFields.DateTimeField(format=DateFormatEnum.FULL_TS_TZ.value)
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.HISTORICAL_DERIVATIVES


class OptionMetaDataCollection(BaseCollection):
    """OptionMetaData collection."""

    security = mongoFields.StringField(required=True)
    strike_prices = mongoFields.ListField(mongoFields.IntField())
    expiry_dates = mongoFields.ListField(
        mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    )
    is_fno = mongoFields.BooleanField(default=False)
    on_date = mongoFields.DateField(
        format=DateFormatEnum.TB_DATE.value, default=date.today()
    )
    timestamp = mongoFields.DateTimeField(
        format=DateFormatEnum.FULL_TS.value, default=datetime.now
    )
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.OPTION_META_DATA
