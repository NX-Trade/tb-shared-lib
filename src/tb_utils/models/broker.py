"""Broker and API Request Models."""

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class Broker(Base):
    """Broker information table."""

    __tablename__ = "broker"

    broker_id = Column(Integer, primary_key=True, autoincrement=True)
    broker_name = Column(String(20), unique=True, nullable=False)
    broker_type = Column(String(20))
    is_active = Column(SmallInteger, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    health_logs = relationship("BrokerHealthLog", back_populates="broker")
    orders = relationship("TradingOrder", back_populates="broker")
    positions = relationship("Position", back_populates="broker")
    trades = relationship("Trade", back_populates="broker")
    # For historical data relationships, those can be imported/mapped when needed

    def __repr__(self):
        return f"<Broker(id={self.broker_id}, name={self.broker_name})>"


class BrokerHealthLog(Base):
    """Broker connection health log."""

    __tablename__ = "broker_health_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    broker_id = Column(Integer, ForeignKey("broker.broker_id"))
    layer = Column(String(10))
    status = Column(String(20))
    reason = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    broker = relationship("Broker", back_populates="health_logs")

    def __repr__(self):
        return f"<BrokerHealthLog(status={self.status}, timestamp={self.timestamp})>"


class ExternalApiRequest(Base):
    """External API Request logging table.

    Logs all external API requests/responses for debugging, analytics,
    and circuit breaking.
    """

    __tablename__ = "external_api_request"

    request_id = Column(BigInteger, primary_key=True, autoincrement=True)
    api_provider = Column(Integer, nullable=False, index=True)
    api_endpoint = Column(String(500), nullable=False)
    http_method = Column(String(10), nullable=False)
    request_headers = Column(Text)
    request_payload = Column(Text)
    http_status_code = Column(Integer, index=True)
    response_headers = Column(Text)
    response_payload = Column(Text)
    request_timestamp = Column(
        DateTime(timezone=True), nullable=False, default=func.now(), index=True
    )
    response_timestamp = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    is_success = Column(SmallInteger, default=0, index=True)
    error_code = Column(String(50))
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    circuit_breaker_state = Column(Integer)
    correlation_id = Column(String(36), index=True)
    user_agent = Column(String(200))
    created_at = Column(DateTime(timezone=True), default=func.now())

    def __repr__(self):
        return f"<ExternalApiRequest(endpoint={self.api_endpoint}, status={self.http_status_code})>"
