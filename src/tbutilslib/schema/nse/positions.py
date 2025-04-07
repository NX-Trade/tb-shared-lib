from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, validator

from ...utils.common import validate_quantity
from ...utils.dtu import parse_timestamp


class PositionsSchema(BaseModel):
    """Positions Schema."""

    id: Optional[str] = None
    account: str
    security: str
    sec_type: Optional[str] = None
    currency: Optional[str] = None
    position: Optional[float] = None
    avg_cost: Optional[float] = None
    on_date: Optional[date] = None
    timestamp: datetime

    @validator("avg_cost", pre=True)
    @classmethod
    def validate_avg_cost(cls, v):
        return validate_quantity(v)

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "PositionsSchema":
        """Create a model from NSE data format.

        Args:
            in_data: Dictionary containing NSE data
        """
        ts = parse_timestamp(in_data["timestamp"])

        return cls(**in_data, on_date=ts.date(), timestamp=ts)


class PositionsResponseSchema(BaseModel):
    """Order Dates Response Schema."""

    positions: bool = True
    total_items: int
    possible_keys: List[str] = []
    items: List[PositionsSchema] = []
