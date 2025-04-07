"""Events Schema."""
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ...utils.dtu import str_to_date
from ...utils.enums import DateFormatEnum


class EventsSchema(BaseModel):
    """Events Schema."""

    id: Optional[str] = None
    company: Optional[str] = None
    description: Optional[str] = None
    event_date: date
    index: str = "equities"
    purpose: Optional[str] = None
    security: str

    @classmethod
    def from_nse_data(cls, in_data: Dict[str, Any]) -> "EventsSchema":
        """Create a model from NSE data format."""
        if not in_data.get("is_nse", False):
            return cls(**in_data)

        event_date_obj = str_to_date(in_data["date"], DateFormatEnum.NSE_DATE.value)

        return cls(
            security=in_data["symbol"],
            event_date=event_date_obj,
            company=in_data["company"],
            purpose=in_data["purpose"],
            description=in_data["bm_desc"],
        )


class EventsResponseSchema(BaseModel):
    """Events Response Schema."""

    events: bool = True
    possible_keys: List[str] = []
    total_items: int
    items: List[EventsSchema] = []


class EventsRequestSchema(BaseModel):
    """Events Request Schema."""

    security: str
