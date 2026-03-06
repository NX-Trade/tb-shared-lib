"""Market Data Models."""

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class FiiDii(Base, PostgresUpsertMixin):
    """FII-DII Daily Cash Data."""

    __tablename__ = "fiidii"

    fiidii_id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False)
    source = Column(String(20), nullable=False, default="NSE")  # NSE / SENSIBULL
    category = Column(String(10), nullable=False)  # 'FII' or 'DII'
    segment = Column(String(20), nullable=False, default="CASH")
    buy_value = Column(Numeric(18, 2), nullable=False, default=0)
    sell_value = Column(Numeric(18, 2), nullable=False, default=0)
    net_value = Column(Numeric(18, 2), nullable=False, default=0)
    net_action = Column(String(10))  # BUY / SELL
    net_view = Column(String(10))  # BULLISH / BEARISH
    net_view_strength = Column(String(10))  # Strong / Medium / Mild
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "category",
            "segment",
            name="fiidii_trade_date_category_segment_key",
        ),
    )


class FiiDiiDerivatives(Base, PostgresUpsertMixin):
    """FII/DII/PRO/Client Derivatives (Futures + Options) Daily Data.

    Sourced from Sensibull API. One row per participant per instrument
    type per trading date.
    """

    __tablename__ = "fiidii_derivatives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False)
    source = Column(String(20), nullable=False)  # NSE or SENSIBULL from SOURCE_ENUM
    instrument_type = Column(String(20), nullable=False)  # FUTURES or OPTIONS
    category = Column(String(10), nullable=False)  # FII, DII, PRO, CLIENT

    # ── Futures fields ────────────────────────────────────────────────────
    net_oi = Column(Numeric(18, 2), default=0)
    outstanding_oi = Column(Numeric(18, 2), default=0)
    net_action = Column(String(10))  # BUY / SELL
    net_view = Column(String(10))  # BULLISH / BEARISH
    net_view_strength = Column(String(10))  # Strong / Medium / Mild

    # ── Stock futures ─────────────────────────────────────────────────────
    stock_net_oi = Column(Numeric(18, 2), default=0)
    stock_outstanding_oi = Column(Numeric(18, 2), default=0)
    stock_net_action = Column(String(10))
    stock_net_view = Column(String(10))
    stock_net_view_strength = Column(String(10))

    # ── Options — overall ─────────────────────────────────────────────────
    options_net_oi = Column(Numeric(18, 2), default=0)
    options_net_oi_change = Column(Numeric(18, 2), default=0)
    options_net_oi_change_action = Column(String(10))
    options_net_oi_change_view = Column(String(10))
    options_net_oi_change_view_strength = Column(String(10))

    # ── Keep Market snapshot ───────────────────────────────────────────────────
    nifty = Column(Numeric(12, 2))
    nifty_change_pct = Column(Numeric(8, 4))
    banknifty = Column(Numeric(12, 2))
    banknifty_change_pct = Column(Numeric(8, 4))

    # ── JSONB catch-all ────────────────────────────────────────────────────
    extras = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "source",
            "category",
            "instrument_type",
            name="fiidii_deriv_date_src_cat_inst_key",
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
