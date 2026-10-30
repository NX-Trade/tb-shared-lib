"""Settings an operator can change without a deploy, and the history of every change."""

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func

from .base import Base


class PlatformSetting(Base):
    """One setting group (e.g. ``stc_spread``) as a JSON object, validated by its own schema.

    The schema lives in ``tb_utils.platform_settings``; this row only stores the values and who
    last changed them. A group with no row falls back to the service's environment, then to the
    code defaults, which are always the safe (off) ones.
    """

    __tablename__ = "platform_setting"

    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)  # bumped on every save; guards overwrites
    description = Column(Text, nullable=True)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PlatformSettingHistory(Base):
    """What a setting was before and after each change, and who changed it."""

    __tablename__ = "platform_setting_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    old_value = Column(JSON, nullable=True)  # None for the first save
    new_value = Column(JSON, nullable=False)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
