"""Fundamental Data Models."""

from sqlalchemy import BigInteger, Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class FundamentalData(Base, PostgresUpsertMixin):
    """Provisional table for storing Fundamental Data.

    This schema might change after sampling actual XML from IBKR.
    """

    __tablename__ = "fundamental_data"

    fundamental_id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, index=True) # Intentionally weak FK since we might fetch symbols not yet in our DB
    symbol = Column(String(50), nullable=False, index=True)

    pe_ratio = Column(Numeric(10, 2))
    beta = Column(Numeric(10, 2))
    dividend_yield = Column(Numeric(10, 2))
    market_cap = Column(BigInteger)
    eps = Column(Numeric(10, 2))
    roe = Column(Numeric(10, 2))

    report_xml = Column(Text)  # Store raw XML just in case we need to re-parse later

    fetched_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("symbol", name="uq_fundamental_data_symbol"),
    )
