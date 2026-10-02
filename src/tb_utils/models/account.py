"""Client Account model for multi-account trade routing and portfolio scoping."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class ClientAccount(Base):
    """Trading Client Account for multi-broker and multi-client order dispatch."""

    __tablename__ = "client_account"

    account_id = Column(Integer, primary_key=True, autoincrement=True)
    client_code = Column(String(50), unique=True, nullable=False, index=True)
    client_name = Column(String(100), nullable=False)
    broker_type = Column(
        String(20), nullable=False, default="UPSTOX", index=True
    )  # UPSTOX, ANGELONE, PAPER

    # API Credentials & Token references
    api_key = Column(String(100), nullable=True)
    api_secret = Column(String(100), nullable=True)
    redirect_uri = Column(String(255), nullable=True)
    token_storage_key = Column(
        String(100), nullable=True
    )  # Redis key containing daily OAuth access token
    static_token = Column(Text, nullable=True)
    # Broker-specific auth fields that don't fit the generic columns above
    # (e.g. Angel One's client_id + pin + totp_secret, structurally different
    # from Upstox's OAuth token).
    extra_credentials = Column(JSON, nullable=True)

    # Risk & Capital allocation
    allocated_capital = Column(
        Numeric(14, 2), nullable=False, server_default="100000.0", default=100000.0
    )
    max_risk_per_trade_pct = Column(
        Numeric(5, 4), nullable=False, server_default="0.0100", default=0.0100
    )  # 1% default
    max_active_trades = Column(Integer, nullable=False, server_default="2", default=2)
    # ₹ overrides for this account's CircuitBreaker; NULL falls back to a
    # proportional default derived from allocated_capital at the service layer
    # (see risk/circuit_breaker.py) rather than the platform-wide settings.
    daily_max_loss_limit = Column(Numeric(14, 2), nullable=True)
    monthly_max_loss_limit = Column(Numeric(14, 2), nullable=True)

    # Status toggles
    is_active = Column(SmallInteger, nullable=False, server_default="1", default=1, index=True)
    is_paper = Column(Boolean, nullable=False, server_default="false", default=False)
    # Per-account panic toggle — distinct from is_active, which gates
    # onboarding/lifecycle. Set by an operator to halt just this account
    # without touching the platform-wide TRADING_HALTED kill-switch.
    is_halted = Column(Boolean, nullable=False, server_default="false", default=False)
    # When true, the account's real broker adapter is used for reads (quotes,
    # positions, balance) but every order-placing call is refused before it
    # reaches the broker (see broker/read_only_guard.py in tb-trade-engine).
    # Distinct from is_paper: is_paper never calls the real broker at all.
    orders_disabled = Column(Boolean, nullable=False, server_default="false", default=False)

    # Audit timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    orders = relationship("TradingOrder", back_populates="account")
    holdings = relationship("Holding", back_populates="account")
    trades = relationship("Trade", back_populates="account")
    strategy_subscriptions = relationship(
        "AccountStrategySubscription", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ClientAccount(id={self.account_id}, code='{self.client_code}', "
            f"broker='{self.broker_type}')>"
        )
