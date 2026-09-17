"""System Configuration, Metrics, and Log Models."""

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, DOUBLE_PRECISION, JSON, JSONB
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class SystemCommand(Base):
    """Durable operator commands consumed by tb-execution's 15-second beat.

    Replaces the fire-and-forget Redis pub/sub pattern used by the panic
    endpoint.  tb-execution queries for PENDING rows, sets status=PROCESSING
    while working, and writes DONE or FAILED with an acknowledged_at timestamp
    so the UI can poll for completion.

    Lifecycle:  PENDING → PROCESSING → DONE | FAILED
    """

    __tablename__ = "system_command"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # e.g. LIQUIDATE_ALL, CANCEL_ALL
    command_type = Column(String(50), nullable=False, index=True)
    # PENDING | PROCESSING | DONE | FAILED
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    issued_by = Column(String(100), nullable=True)  # operator id / service name
    broker = Column(String(50), nullable=True)  # e.g. UPSTOX, IB
    reason = Column(Text, nullable=True)  # human-readable reason
    payload = Column(JSON, default={})  # arbitrary JSON context
    issued_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    result_message = Column(Text, nullable=True)  # fill in on DONE/FAILED


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
    metadata_ = Column("metadata", JSON, default={})  # _ suffix to avoid SQLAlchemy conflict


class TaskLog(Base):
    """Logs for Celery Tasks execution status."""

    __tablename__ = "celery_task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(255), unique=True, index=True, nullable=False)
    task_name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False)  # e.g., 'SUCCESS', 'FAILED'
    error_message = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RegimeLog(Base, PostgresUpsertMixin):
    """Daily market volatility regime classifications."""

    __tablename__ = "regime_log"

    timestamp = Column(DateTime(timezone=True), primary_key=True)
    symbol = Column(String(50), primary_key=True)  # e.g. NIFTY, BANKNIFTY
    predicted_state = Column(Integer, nullable=False)
    state_probability = Column(ARRAY(DOUBLE_PRECISION), nullable=False)
    confidence = Column(Numeric(5, 4))
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class WatchlistFocus(Base, PostgresUpsertMixin):
    """System-generated daily watchlist focus stocks."""

    __tablename__ = "watchlist_focus"

    timestamp = Column(DateTime(timezone=True), primary_key=True)
    symbol = Column(String(50), primary_key=True)
    xgboost_prob = Column(Numeric(5, 4), nullable=False)
    technical_score = Column(Numeric(5, 2))
    features_json = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
