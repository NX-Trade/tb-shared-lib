"""MaxOI Schema."""
from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class MaxOiDatumSchema(BaseModel):
    """MaxOI Datum Schema."""

    open_interest: Optional[int] = None
    strike_price: Optional[int] = None


class MaxOpenInterestSchema(BaseModel):
    """MaxOI Schema."""

    CE: Optional[MaxOiDatumSchema] = None
    PE: Optional[MaxOiDatumSchema] = None


class MaxOpenInterestResponseSchema(BaseModel):
    """MaxOI Response Schema."""

    max_open_interest: bool = True
    security: Optional[str] = None
    expiry_date: Optional[date] = None
    possible_keys: List[str] = []
    items: Optional[MaxOpenInterestSchema] = None


class MaxOpenInterestRequestSchema(BaseModel):
    """MaxOI Request Schema."""

    security: Optional[str] = None
