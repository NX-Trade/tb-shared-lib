"""Operator-editable settings stored in the database: validated, versioned, audited, fail-closed.

Each setting group is a pydantic model (its schema and its defaults) registered under a key. The
values live as one JSON row in ``platform_setting``; every save is validated, bumps the version and
writes a ``platform_setting_history`` row saying what changed and who changed it.

Precedence for a value: the stored row, then the service's environment (passed as
``fallback``), then the code default. **Defaults are always the safe ones** (a trading switch
defaults to off), because they are also what is used when a setting cannot be read: a database that
is down, or a stored value that no longer validates, must stop a strategy trading, never start it.
In particular an invalid row is not repaired from the environment: a corrupt row plus an env
value that says "on" stays off.

Reads and writes take a session and nothing else, so they work from any service.
"""

import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from tb_utils.models import PlatformSetting, PlatformSettingHistory

logger = logging.getLogger("tb_utils.platform_settings")

_HH_MM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MARKET_CLOSE = "15:30"


class SettingError(ValueError):
    """A setting cannot be read or saved."""


class SettingConflict(SettingError):
    """The setting changed since the caller read it."""


class SettingValidationError(SettingError):
    """The proposed values are not valid; ``errors`` says why, field by field."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


def time_of(hh_mm: str) -> dt.time:
    """``"14:30"`` as a time."""
    hour, minute = hh_mm.split(":")
    return dt.time(int(hour), int(minute))


# ── The setting groups ───────────────────────────────────────────────────────


class StcSpreadSettings(BaseModel):  # pylint: disable=too-few-public-methods
    """The STC option-spread dispatcher: the master switch, caps, entry window and exit times."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False  # the master switch; every account's own flags still apply
    max_active_baskets: int = Field(3, ge=1, le=20)  # across the platform
    max_per_underlying: int = Field(1, ge=1, le=5)  # per account
    entry_start: str = "09:30"
    entry_end: str = "14:30"  # two legs must enter and the exit must finish
    signal_max_age_minutes: int = Field(10, ge=1, le=60)
    order_type: Literal["MARKETABLE_LIMIT", "MARKET"] = "MARKETABLE_LIMIT"
    refresh_timeout_seconds: int = Field(45, ge=10, le=300)
    eod_exit_time: str = "15:15"  # the exit starts, with marketable limits
    hard_exit_time: str = "15:29"  # anything still open goes at market

    @field_validator("entry_start", "entry_end", "eod_exit_time", "hard_exit_time")
    @classmethod
    def _real_time(cls, value: str) -> str:
        if not _HH_MM.match(value):
            raise ValueError("must be a time written HH:MM")
        return value

    @model_validator(mode="after")
    def _times_in_order(self) -> "StcSpreadSettings":
        if self.entry_start >= self.entry_end:
            raise ValueError("entry_end must be after entry_start")
        if self.entry_end >= self.eod_exit_time:
            raise ValueError("the exit must start after the last entry")
        if self.eod_exit_time >= self.hard_exit_time:
            raise ValueError("hard_exit_time must be after eod_exit_time")
        if self.hard_exit_time >= MARKET_CLOSE:
            raise ValueError(f"hard_exit_time must be before the {MARKET_CLOSE} close")
        return self


SETTING_MODELS: dict[str, type[BaseModel]] = {"stc_spread": StcSpreadSettings}


@dataclass(frozen=True)
class LoadedSetting:
    """A setting's effective values and where they came from."""

    values: Any  # an instance of the group's model
    # database | fallback | default | invalid (stored value unusable) | error (could not read)
    source: str
    version: int
    updated_by: Optional[str] = None
    updated_at: Optional[dt.datetime] = None


def _model(key: str) -> type[BaseModel]:
    try:
        return SETTING_MODELS[key]
    except KeyError:
        raise SettingError(f"unknown setting {key!r}") from None


def _safe(model: type[BaseModel], source: str) -> LoadedSetting:
    """The fail-closed answer: the code defaults, which are always off."""
    return LoadedSetting(model(), source, 0)


def load_setting(db: Session, key: str, fallback: Optional[dict] = None) -> LoadedSetting:
    """The effective values for ``key``. A bad or unreadable value never raises: it fails closed."""
    model = _model(key)
    try:
        row = db.get(PlatformSetting, key)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("[platform_settings] Could not read %s; failing closed.", key)
        return _safe(model, "error")

    base = dict(fallback or {})
    try:
        if row is None:
            return LoadedSetting(model(**base), "fallback" if fallback else "default", 0)
        values = model(**{**base, **(row.value or {})})
    except ValidationError:
        logger.error("[platform_settings] Invalid value for %s: failing closed.", key)
        return _safe(model, "invalid")
    return LoadedSetting(values, "database", row.version, row.updated_by, row.updated_at)


def _messages(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "field": ".".join(str(p) for p in err["loc"]) or "settings",
            "message": err["msg"].removeprefix("Value error, "),
        }
        for err in exc.errors()
    ]


def save_setting(
    db: Session,
    key: str,
    changes: dict,
    updated_by: str,
    expected_version: Optional[int] = None,
    fallback: Optional[dict] = None,
) -> LoadedSetting:
    """Merge ``changes`` over the effective values, validate, store, and record the change.

    Raises :class:`SettingValidationError` for bad values and :class:`SettingConflict` if
    ``expected_version`` is given and no longer matches. Nothing is written on either.
    """
    model = _model(key)
    if not (updated_by or "").strip():
        raise SettingError("updated_by is required: every change records who made it")
    current = load_setting(db, key, fallback)
    if current.source == "error":
        raise SettingError(f"cannot read the current {key} setting, so it cannot be changed")
    stored = db.get(PlatformSetting, key)
    version = stored.version if stored is not None else 0
    if expected_version is not None and expected_version != version:
        raise SettingConflict(f"{key} is at version {version}, not {expected_version}")

    try:
        new = model(**{**current.values.model_dump(), **changes})
    except ValidationError as exc:
        raise SettingValidationError(_messages(exc)) from exc

    new_value = new.model_dump(mode="json")
    old_value = None if stored is None else dict(stored.value or {})
    now = dt.datetime.now(dt.UTC)
    try:
        if stored is None:
            db.add(
                PlatformSetting(
                    key=key, value=new_value, version=1, updated_by=updated_by, updated_at=now
                )
            )
        else:
            stored.value, stored.version = new_value, version + 1
            stored.updated_by, stored.updated_at = updated_by, now
        db.add(
            PlatformSettingHistory(
                key=key,
                version=version + 1,
                old_value=old_value,
                new_value=new_value,
                changed_by=updated_by,
                changed_at=now,
            )  # fmt: skip
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return LoadedSetting(new, "database", version + 1, updated_by, now)


__all__ = [
    "LoadedSetting",
    "SETTING_MODELS",
    "SettingConflict",
    "SettingError",
    "SettingValidationError",
    "StcSpreadSettings",
    "load_setting",
    "save_setting",
    "time_of",
]
