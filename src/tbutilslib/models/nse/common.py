"""Common MongoDB models for NSE data.

This module contains common MongoDB models that are shared across
multiple NSE data types to reduce code duplication.
"""

from mongoengine import fields as mongoFields

from ...utils.enums import DateFormatEnum
from ..base import BaseCollection


class DateBaseModel(BaseCollection):
    """Base model with common date fields."""

    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    timestamp = mongoFields.DateTimeField(format=DateFormatEnum.FULL_TS.value)


class PriceDataBaseModel(DateBaseModel):
    """Base model for price data common to equity and indexes."""

    open = mongoFields.FloatField()
    day_high = mongoFields.FloatField()
    day_low = mongoFields.FloatField()
    last_price = mongoFields.FloatField()
    previous_close = mongoFields.FloatField()
    change = mongoFields.FloatField()
    p_change = mongoFields.FloatField()


class ChartDataBaseModel(PriceDataBaseModel):
    """Base model for chart data common to equity and indexes."""

    near_weak_high = mongoFields.FloatField()
    near_weak_low = mongoFields.FloatField()
    per_change_30d = mongoFields.FloatField()
    per_change_365d = mongoFields.FloatField()
    chart_30d_path = mongoFields.StringField()
    chart_today_path = mongoFields.StringField()
    chart_365d_path = mongoFields.StringField()
    date_30d_ago = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    date_365d_ago = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
