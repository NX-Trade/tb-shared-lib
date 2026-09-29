"""Pydantic schemas for ClientAccount."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ClientAccountBase(BaseModel):
    """Base schema for client account."""

    client_code: str = Field(
        ..., max_length=50, description="Unique client identifier (e.g. UPSTOX_MAIN)"
    )
    client_name: str = Field(..., max_length=100, description="Display name for client")
    broker_type: str = Field(
        "UPSTOX", max_length=20, description="Broker platform (UPSTOX, ANGELONE, PAPER)"
    )
    api_key: Optional[str] = Field(None, max_length=100)
    api_secret: Optional[str] = Field(None, max_length=100)
    redirect_uri: Optional[str] = Field(None, max_length=255)
    token_storage_key: Optional[str] = Field(
        None, max_length=100, description="Redis key storing OAuth token"
    )
    static_token: Optional[str] = Field(None, description="Static access token fallback")
    extra_credentials: Optional[dict[str, Any]] = Field(
        None,
        description="Broker-specific auth fields beyond the generic columns "
        "(e.g. Angel One client_id/pin/totp_secret)",
    )
    allocated_capital: Decimal = Field(
        Decimal("100000.00"), description="Allocated trading capital"
    )
    max_risk_per_trade_pct: Decimal = Field(
        Decimal("0.0100"), description="Max risk percentage per trade (0.01 = 1%)"
    )
    max_active_trades: int = Field(2, description="Max concurrent open trades for this account")
    daily_max_loss_limit: Optional[Decimal] = Field(
        None, description="₹ override for this account's daily CircuitBreaker limit"
    )
    monthly_max_loss_limit: Optional[Decimal] = Field(
        None, description="₹ override for this account's monthly CircuitBreaker limit"
    )
    is_active: int = Field(1, description="Active status (1=active, 0=paused)")
    is_paper: bool = Field(False, description="Whether orders should route to paper simulator")
    is_halted: bool = Field(
        False, description="Per-account panic toggle, independent of the platform kill-switch"
    )
    orders_disabled: bool = Field(
        False,
        description="If true, the real broker adapter is used for reads (quotes/positions/"
        "balance) but every order-placing call is refused before reaching the broker",
    )


class ClientAccountCreate(ClientAccountBase):
    """Schema for creating a new client account."""


class ClientAccountUpdate(BaseModel):
    """Schema for updating an existing client account."""

    client_name: Optional[str] = None
    broker_type: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    token_storage_key: Optional[str] = None
    static_token: Optional[str] = None
    extra_credentials: Optional[dict[str, Any]] = None
    allocated_capital: Optional[Decimal] = None
    max_risk_per_trade_pct: Optional[Decimal] = None
    max_active_trades: Optional[int] = None
    daily_max_loss_limit: Optional[Decimal] = None
    monthly_max_loss_limit: Optional[Decimal] = None
    is_active: Optional[int] = None
    is_paper: Optional[bool] = None
    is_halted: Optional[bool] = None
    orders_disabled: Optional[bool] = None


class ClientAccountResponse(ClientAccountBase):
    """Schema for client account response."""

    account_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
