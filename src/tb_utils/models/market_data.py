"""Market Data Models."""

from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Numeric,
    Date,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from .base import Base, PostgresUpsertMixin


class FiiDii(Base, PostgresUpsertMixin):
    """FII-DII Daily Data."""

    __tablename__ = "fiidii"

    fiidii_id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False)
    category = Column(String(10), nullable=False)  # 'FII' or 'DII'
    segment = Column(String(20), nullable=False, default="CASH")
    buy_value = Column(Numeric(18, 2), nullable=False, default=0)
    sell_value = Column(Numeric(18, 2), nullable=False, default=0)
    net_value = Column(Numeric(18, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "category",
            "segment",
            name="fiidii_trade_date_category_segment_key",
        ),
    )


class News(Base):
    """News Headlines."""

    __tablename__ = "news"

    news_id = Column(Integer, primary_key=True, autoincrement=True)
    headline = Column(Text, nullable=False)
    summary = Column(Text)
    url = Column(Text)
    source = Column(String(100), index=True)
    category = Column(String(50))
    symbols = Column(String(200))  # comma-separated
    published_at = Column(DateTime(timezone=True), index=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class MarketBreadth(Base, PostgresUpsertMixin):
    """Market Breadth (Advance-Decline) Hypertable."""

    __tablename__ = "market_breadth"

    ts = Column(DateTime(timezone=True), primary_key=True)
    exchange = Column(String(10), primary_key=True, default="NSE")
    advances = Column(Integer, nullable=False, default=0)
    declines = Column(Integer, nullable=False, default=0)
    unchanged = Column(Integer, nullable=False, default=0)
    advance_volume = Column(BigInteger, default=0)
    decline_volume = Column(BigInteger, default=0)
    ad_ratio = Column(Numeric(8, 4))
