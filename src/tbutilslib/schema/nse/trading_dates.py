from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TradingDatesSchema(BaseModel):
    """Trading Dates Schema."""

    id: Optional[str] = None
    last_trading_date: date
    current_trading_date: date
    timestamp: datetime = Field(default_factory=datetime.now)


class TradingDatesResponseSchema(BaseModel):
    """Trading Dates Response Schema."""

    trading_dates: bool = True
    possible_keys: List[str] = []
    total_items: int
    items: List[TradingDatesSchema] = []
