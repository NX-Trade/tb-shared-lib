"""FII-DII collection."""
from copy import deepcopy

from mongoengine import fields as mongoFields

from ...config import MongoConfig
from ...utils.enums import DateFormatEnum, FiiDiiCategoryEnum
from ..base import BASE_META, BaseCollection


class FiiDiiCollection(BaseCollection):
    """FII_DII Collection."""

    category = mongoFields.StringField(
        required=True, default=FiiDiiCategoryEnum.CASH.value
    )
    fii_purchase = mongoFields.FloatField()
    dii_purchase = mongoFields.FloatField()
    fii_sales = mongoFields.FloatField()
    dii_sales = mongoFields.FloatField()
    fii_net = mongoFields.FloatField()
    dii_net = mongoFields.FloatField()
    on_date = mongoFields.DateField(format=DateFormatEnum.TB_DATE.value)
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["+on_date"]
    meta = {"collection": MongoConfig.FII_DII}
