"""Index Data Collection."""
from copy import deepcopy

from mongoengine import fields as mongoFields

from ...config.database import MongoConfig
from ...utils.enums import DateFormatEnum
from ..base import BASE_META
from .common import ChartDataBaseModel


class IndexCollection(ChartDataBaseModel):
    """Index Data collection."""

    security = mongoFields.StringField(required=True)
    identifier = mongoFields.StringField()
    series = mongoFields.StringField()
    ffmc = mongoFields.FloatField()
    year_high = mongoFields.FloatField()
    year_low = mongoFields.FloatField()
    total_traded_volume = mongoFields.IntField()
    total_traded_value = mongoFields.FloatField()
    last_update_time = mongoFields.DateTimeField(format=DateFormatEnum.FULL_TS.value)
    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.INDEX_DATA
