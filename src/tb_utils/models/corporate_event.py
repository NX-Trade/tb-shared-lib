"""Corporate Event and Trading Holiday Models."""

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class CorporateEvent(Base, PostgresUpsertMixin):
    """Corporate events table for tracking company actions."""

    __tablename__ = "corporate_event"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    company_name = Column(String(200))

    event_type = Column(
        ENUM(
            "RESULT",
            "DIVIDEND",
            "AGM",
            "BONUS",
            "SPLIT",
            "BUYBACK",
            "RIGHTS",
            "OTHER",
            name="event_type",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )

    event_date = Column(DateTime(timezone=True), nullable=False, index=True)
    ex_date = Column(DateTime(timezone=True))
    record_date = Column(DateTime(timezone=True))
    description = Column(Text)
    subject = Column(Text)
    isin = Column(String(20))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("symbol", "event_date", name="uix_corporate_event_key"),
    )

    def __repr__(self):
        return (
            f"<CorporateEvent(symbol={self.symbol}, "
            f"type={self.event_type}, "
            f"date={self.event_date})>"
        )


class TradingHoliday(Base):
    """Trading holidays table for NSE calendar."""

    __tablename__ = "trading_holiday"

    holiday_id = Column(Integer, primary_key=True, autoincrement=True)
    holiday_date = Column(
        DateTime(timezone=True), nullable=False, unique=True, index=True
    )
    holiday_name = Column(String(200), nullable=False)
    holiday_type = Column(String(50), default="TRADING")
    week_day = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=func.now())

    def __repr__(self):
        return f"<TradingHoliday(date={self.holiday_date}, name={self.holiday_name})>"
