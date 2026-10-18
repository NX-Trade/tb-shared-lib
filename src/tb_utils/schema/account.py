"""Pydantic schemas for ClientAccount.

Credentials are write-only. They can be set and replaced through the API but
never read back: ``ClientAccountResponse`` masks every one of them, so a
client listing accounts receives ``has_api_secret: true`` and a row of dots
rather than the secret itself.

That shapes editing too. A blank credential field means "leave the stored one
alone", and the mask the UI displays is recognised and discarded if it is
echoed back, so re-saving a form without retyping a secret cannot overwrite it
with dots.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Shown in place of a stored credential. Also treated as "unchanged" on the
# way in, since this is exactly what a form round-trips when left untouched.
MASK = "••••••••"

#: Never revealed, not even in part.
SECRET_FIELDS: tuple[str, ...] = ("api_secret", "pin", "totp_secret")
#: Revealed only by their last few characters, enough to tell two keys apart.
PARTIAL_FIELDS: tuple[str, ...] = ("api_key", "phone", "broker_client_id")

CREDENTIAL_FIELDS: tuple[str, ...] = SECRET_FIELDS + PARTIAL_FIELDS


def mask_tail(value: Optional[str], keep: int = 4) -> Optional[str]:
    """Mask all but the last ``keep`` characters, or entirely if it is short."""
    if not value:
        return None
    text = str(value)
    return MASK if len(text) <= keep else f"{MASK}{text[-keep:]}"


def is_masked(value: Any) -> bool:
    """Whether a submitted value is a mask echoed back rather than a new secret."""
    return isinstance(value, str) and MASK[0] in value


class ClientAccountBase(BaseModel):
    """Base schema for client account."""

    client_code: str = Field(
        ..., max_length=50, description="Unique client identifier (e.g. UPSTOX_MAIN)"
    )
    client_name: str = Field(..., max_length=100, description="Display name for client")
    broker_type: str = Field(
        "UPSTOX", max_length=20, description="Broker platform (UPSTOX, ANGELONE, ICICI, PAPER)"
    )
    api_key: Optional[str] = Field(None, max_length=100)
    api_secret: Optional[str] = Field(None, max_length=100)
    redirect_uri: Optional[str] = Field(None, max_length=255)
    token_storage_key: Optional[str] = Field(
        None, max_length=100, description="Redis key storing OAuth token"
    )
    broker_client_id: Optional[str] = Field(
        None, max_length=50, description="Broker-side client id (e.g. the Angel One client code)"
    )
    phone: Optional[str] = Field(
        None, max_length=20, description="Mobile number used to log in (Upstox)"
    )
    pin: Optional[str] = Field(None, max_length=32, description="Login PIN behind the broker's 2FA")
    totp_secret: Optional[str] = Field(
        None, max_length=64, description="Base32 TOTP seed for unattended 2FA"
    )
    extra_credentials: Optional[dict[str, Any]] = Field(
        None,
        description="Legacy broker-specific auth fields. Superseded by the columns above; "
        "still read as a fallback for rows written before they existed",
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
    """Schema for updating an existing client account.

    Only the fields actually supplied are written. A credential left blank, or
    returned still wearing its mask, is dropped here so the stored value
    survives a form round-trip that did not touch it.
    """

    client_name: Optional[str] = None
    broker_type: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    token_storage_key: Optional[str] = None
    broker_client_id: Optional[str] = None
    phone: Optional[str] = None
    pin: Optional[str] = None
    totp_secret: Optional[str] = None
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

    @model_validator(mode="before")
    @classmethod
    def _keep_untouched_credentials(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            key: value
            for key, value in data.items()
            if key not in CREDENTIAL_FIELDS or (value and not is_masked(value))
        }


class ClientAccountResponse(ClientAccountBase):
    """Schema for client account response, with every credential redacted."""

    account_id: int
    created_at: datetime
    updated_at: datetime

    # Whether each credential slot is filled, so the UI can say "set" without
    # ever being handed the value. One per entry in CREDENTIAL_FIELDS.
    has_api_key: bool = False
    has_api_secret: bool = False
    has_pin: bool = False
    has_totp_secret: bool = False
    has_phone: bool = False
    has_broker_client_id: bool = False

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _redact_credentials(self) -> "ClientAccountResponse":
        """Replace every credential with its mask once the row has been read.

        Runs after validation rather than before it, so the real values are
        never carried into the serialised output by a field this does not
        know about.
        """
        for name in SECRET_FIELDS:
            raw = getattr(self, name, None)
            setattr(self, f"has_{name}", bool(raw))
            setattr(self, name, MASK if raw else None)
        for name in PARTIAL_FIELDS:
            raw = getattr(self, name, None)
            setattr(self, f"has_{name}", bool(raw))
            setattr(self, name, mask_tail(raw))

        # The legacy blob holds the same secrets on un-migrated rows. Its keys
        # are worth seeing; its values are not.
        if self.extra_credentials:
            self.extra_credentials = dict.fromkeys(self.extra_credentials, MASK)
        return self
