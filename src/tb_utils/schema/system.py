"""Pydantic schemas for System configurations, metrics, and logs."""

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from .base import BaseSchema


class SystemMetricResponse(BaseSchema):
    id: int
    timestamp: datetime
    total_equity: float
    cash_balance: float
    unrealized_pnl: float
    realized_pnl: float
    peak_equity: float
    drawdown_pct: float
    open_positions: int


class SystemLogResponse(BaseSchema):
    id: int
    ts: datetime
    service: str
    level: str
    event_type: str
    message: str
    metadata_: Optional[dict[str, Any]] = Field(default=None, alias="metadata")
