"""Nifty Equity Collection."""
from copy import deepcopy

from mongoengine import fields as mongoFields

from ...config.database import MongoConfig
from ...utils.enums import DateFormatEnum
from ..base import BASE_META, BaseCollection
from .common import ChartDataBaseModel


class NiftyEquityCollection(ChartDataBaseModel):
    """NIFTY_EQUITY collection."""

    security = mongoFields.StringField(required=True)
    identifier = mongoFields.StringField()
    isin = mongoFields.StringField()
    series = mongoFields.StringField()
    total_traded_volume = mongoFields.IntField()
    total_traded_value = mongoFields.FloatField()
    year_high = mongoFields.FloatField()
    year_low = mongoFields.FloatField()
    ffmc = mongoFields.FloatField()

    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    last_update_time = mongoFields.DateTimeField(format=DateFormatEnum.FULL_TS.value)
    company_name = mongoFields.StringField()
    industry = mongoFields.StringField()
    active_series = mongoFields.ListField(mongoFields.StringField())
    debt_series = mongoFields.ListField(mongoFields.StringField())
    temp_suspended_series = mongoFields.ListField(mongoFields.StringField())
    is_fno_sec = mongoFields.BooleanField()
    is_ca_sec = mongoFields.BooleanField()
    is_slb_sec = mongoFields.BooleanField()
    is_debt_sec = mongoFields.BooleanField()
    is_suspended = mongoFields.BooleanField()
    is_etf_Sec = mongoFields.BooleanField()
    is_delisted = mongoFields.BooleanField()
    is_municipal_bond = mongoFields.BooleanField()
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.NIFTY_EQUITY


class AdvanceDeclineCollection(BaseCollection):
    """ADVANCE_DECLINE collection."""

    declines = mongoFields.IntField()
    advances = mongoFields.IntField()
    unchanged = mongoFields.IntField()
    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    timestamp = mongoFields.DateTimeField(format=DateFormatEnum.FULL_TS.value)
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.ADVANCE_DECLINE


class EquityMetaCollection(BaseCollection):
    """STATIC_EQUITY collection."""

    security = mongoFields.StringField(required=True)
    company = mongoFields.StringField()
    industry = mongoFields.StringField()
    isin = mongoFields.StringField()
    series = mongoFields.StringField()
    is_fno = mongoFields.BooleanField(default=False)
    is_nifty_50 = mongoFields.BooleanField(default=False)
    is_nifty_100 = mongoFields.BooleanField(default=False)
    is_nifty_500 = mongoFields.BooleanField(default=False)
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-security"]
    meta["collection"] = MongoConfig.EQUITY_META
