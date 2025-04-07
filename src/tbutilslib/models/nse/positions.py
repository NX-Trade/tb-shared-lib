from copy import deepcopy

from mongoengine import fields as mongoFields

from ...config import MongoConfig
from ..base import BASE_META
from .common import DateBaseModel


class PositionsCollection(DateBaseModel):
    """POSITIONS collection."""

    account = mongoFields.StringField(required=True)
    security = mongoFields.StringField(required=True)
    secType = mongoFields.StringField()
    currency = mongoFields.StringField()
    position = mongoFields.FloatField()
    avg_cost = mongoFields.FloatField()
    meta = deepcopy(BASE_META)
    meta["ordering"] = ["-timestamp"]
    meta["collection"] = MongoConfig.POSITIONS
