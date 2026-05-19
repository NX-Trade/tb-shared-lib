"""NSE Reference Data Models."""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class NseIndex(Base, PostgresUpsertMixin):
    """NSE Index Catalogue."""

    __tablename__ = "nse_index"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)
    index_name = Column(String(100), nullable=False)
    index_symbol = Column(String(50), nullable=False)
    constituent_url = Column(String(255))
    factsheet_url = Column(String(255))
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (UniqueConstraint("category", "index_name", name="uix_nse_index_cat_name"),)


class IndexConstituent(Base, PostgresUpsertMixin):
    """NSE Index Constituents (Stocks in Index)."""

    __tablename__ = "index_constituent"

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_category = Column(String(50), nullable=False)
    index_name = Column(String(100), nullable=False)
    symbol = Column(String(50), nullable=False)
    company_name = Column(String(255))
    industry = Column(String(200))
    isin = Column(String(20))
    series = Column(String(10))
    as_of_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint("index_name", "symbol", name="uix_index_constituent_idx_sym"),
    )


class FnoExpiry(Base, PostgresUpsertMixin):
    """F&O Expiry Dates."""

    __tablename__ = "fno_expiry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_type = Column(String(20), nullable=False)  # FUTURES / OPTIONS
    underlying_symbol = Column(String(50))  # Null for futures
    expiry_date = Column(Date, nullable=False)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "instrument_type",
            "underlying_symbol",
            "expiry_date",
            name="uix_fno_expiry_type_sym_date",
        ),
    )


class FnoBanList(Base, PostgresUpsertMixin):
    """F&O Ban List Daily Data."""

    __tablename__ = "fno_ban_list"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "symbol",
            name="uq_fno_ban_list_date_symbol",
        ),
    )

