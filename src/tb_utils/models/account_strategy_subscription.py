"""Account-Strategy subscription: which strategies run on which client accounts."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class AccountStrategySubscription(Base):
    """Configures which ``TradingSignal.strategy_name`` values fan out to a given
    ``ClientAccount``. Signal execution only reaches accounts with a matching,
    enabled subscription row — a strategy is never implicitly wired to every
    account.
    """

    __tablename__ = "account_strategy_subscription"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(
        Integer, ForeignKey("client_account.account_id"), nullable=False, index=True
    )
    strategy_name = Column(String(50), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, server_default="true", default=True)
    # Optional per-subscription overrides (e.g. a different max_risk_per_trade_pct
    # for this strategy on this account than the account's default).
    risk_override = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    account = relationship("ClientAccount", back_populates="strategy_subscriptions")

    __table_args__ = (UniqueConstraint("account_id", "strategy_name", name="uix_account_strategy"),)

    def __repr__(self) -> str:
        return (
            f"<AccountStrategySubscription(account_id={self.account_id}, "
            f"strategy='{self.strategy_name}', enabled={self.is_enabled})>"
        )
