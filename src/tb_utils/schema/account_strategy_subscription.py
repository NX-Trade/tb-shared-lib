"""Pydantic schemas for AccountStrategySubscription."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AccountStrategySubscriptionBase(BaseModel):
    """Base schema for an account's subscription to a strategy."""

    account_id: int = Field(..., description="ClientAccount this subscription belongs to")
    strategy_name: str = Field(
        ..., max_length=50, description="Matches TradingSignal.strategy_name (e.g. STC_INTRADAY)"
    )
    is_enabled: bool = Field(
        True, description="Whether signals for this strategy fan out to the account"
    )
    risk_override: Optional[dict[str, Any]] = Field(
        None, description="Optional per-subscription risk overrides"
    )


class AccountStrategySubscriptionCreate(AccountStrategySubscriptionBase):
    """Schema for creating a new subscription."""


class AccountStrategySubscriptionUpdate(BaseModel):
    """Schema for updating an existing subscription."""

    is_enabled: Optional[bool] = None
    risk_override: Optional[dict[str, Any]] = None


class AccountStrategySubscriptionResponse(AccountStrategySubscriptionBase):
    """Schema for subscription response."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
