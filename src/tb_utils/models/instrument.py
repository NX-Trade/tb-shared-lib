"""Instrument Master Model."""

from sqlalchemy import Column, DateTime, Integer, SmallInteger, String
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class Instrument(Base, PostgresUpsertMixin):
    """Master table for trade-able instruments/stocks."""

    __tablename__ = "instrument"

    instrument_id = Column(Integer, primary_key=True, autoincrement=True)
    isin = Column(String(50), unique=True, nullable=False, index=True)
    symbol = Column(String(100), nullable=False, index=True)
    ib_symbol = Column(String(20), nullable=False, index=True)
    company_name = Column(String(500))
    sector = Column(String(200))
    is_fno = Column(SmallInteger, default=0)
    is_index = Column(SmallInteger, default=0)
    is_nifty_50 = Column(SmallInteger, default=0)
    is_nifty_100 = Column(SmallInteger, default=0)
    is_nifty_500 = Column(SmallInteger, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return (
            f"<Instrument(id={self.instrument_id}, "
            f"symbol={self.symbol}, "
            f"ib_symbol={self.ib_symbol}, "
            f"isin={self.isin}, "
            f"is_index={self.is_index})>"
        )
