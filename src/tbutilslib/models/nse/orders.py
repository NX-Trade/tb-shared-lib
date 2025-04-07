from copy import deepcopy

from mongoengine import fields as mongoFields

from ...config import MongoConfig
from ..base import BASE_META
from .common import DateBaseModel


class OrdersCollection(DateBaseModel):
    """ORDERS collection."""

    order_id = mongoFields.IntField(required=True)
    security = mongoFields.StringField(required=True)
    sec_type = mongoFields.StringField(required=True)
    order_type = mongoFields.StringField(required=True)
    status = mongoFields.StringField()
    action = mongoFields.StringField()
    limit_price = mongoFields.FloatField()
    aux_price = mongoFields.FloatField()
    total_quantity = mongoFields.FloatField()
    filled = mongoFields.FloatField()
    remaining = mongoFields.FloatField()
    avg_fill_price = mongoFields.FloatField()
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.ORDERS
