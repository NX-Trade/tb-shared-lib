"""Pydantic schemas for Instruments."""

from datetime import datetime
from typing import List, Optional

from .base import BaseSchema


class InstrumentResponse(BaseSchema):
    instrument_id: int
    isin: str
    ib_symbol: str
    icici_symbol: Optional[str] = None
    company_name: Optional[str] = None
    is_fno: int
    indices: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
