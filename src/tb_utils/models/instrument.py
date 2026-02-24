"""Instrument Master Model."""

from sqlalchemy import (
    Column,
    Integer,
    SmallInteger,
    String,
    DateTime,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from .base import Base, PostgresUpsertMixin


class Instrument(Base, PostgresUpsertMixin):
    """Master table for trade-able instruments/stocks."""

    __tablename__ = "instrument"

    instrument_id = Column(Integer, primary_key=True, autoincrement=True)
    isin = Column(String(20), unique=True, nullable=False, index=True)
    ib_symbol = Column(String(20), nullable=False, index=True)
    icici_symbol = Column(String(20))
    company_name = Column(String(255))
    is_fno = Column(SmallInteger, default=0)
    indices = Column(ARRAY(String))
    is_index = Column(SmallInteger, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<Instrument(id={self.instrument_id}, ib_symbol={self.ib_symbol}, isin={self.isin}, is_index={self.is_index})>"
