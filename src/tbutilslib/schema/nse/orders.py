from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator

from ...utils.common import validate_quantity


class OrdersSchema(BaseModel):
    """Orders Schema."""

    id: Optional[str] = None
    order_id: int
    security: str
    sec_type: str
    order_type: str
    status: Optional[str] = None
    action: Optional[str] = None
    limit_price: Optional[float] = None
    aux_price: Optional[float] = None
    total_quantity: float
    filled: Optional[float] = None
    remaining: Optional[float] = None
    avg_fill_price: Optional[float] = None
    on_date: Optional[date] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    @validator("total_quantity", pre=True)
    @classmethod
    def validate_total_quantity(cls, v):
        return validate_quantity(v)


class OrdersResponseSchema(BaseModel):
    """Order Dates Response Schema."""

    orders: bool = True
    total_items: int
    possible_keys: List[str] = []
    items: List[OrdersSchema] = []
