"""System Configuration, Metrics, and Log Models."""

from sqlalchemy import JSON, Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from .base import Base


class SystemMetric(Base):
    """System-level metrics for equity curve and drawdown tracking."""

    __tablename__ = "system_metric"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    total_equity = Column(Numeric(12, 2), nullable=False)
    cash_balance = Column(Numeric(12, 2), nullable=False)
    unrealized_pnl = Column(Numeric(10, 2), default=0)
    realized_pnl = Column(Numeric(10, 2), default=0)
    peak_equity = Column(Numeric(12, 2), nullable=False)
    drawdown_pct = Column(Numeric(5, 2), default=0)
    open_positions = Column(Integer, default=0)


class SystemLog(Base):
    """System Logs for critical events across services."""

    __tablename__ = "system_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    service = Column(String(50), nullable=False)
    level = Column(String(10), nullable=False)
    event_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    metadata_ = Column(
        "metadata", JSON, default={}
    )  # _ suffix to avoid SQLAlchemy conflict
