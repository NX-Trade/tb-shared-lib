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


class DerivativeTick(Base, PostgresUpsertMixin):
    """High-frequency tick data for options and futures from IBKR.

    This table stores snapshot prices, bid/ask, volume, and open interest
    for individual derivative contracts at a specific timestamp.
    """

    __tablename__ = "derivative_tick"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Contract Details
    # Underlying symbol (e.g., NIFTY, RELIANCE)
    symbol = Column(String(50), nullable=False, index=True)
    contract_type = Column(String(10), nullable=False)  # FUT, CE, PE
    strike = Column(Numeric(18, 2))  # Null for FUT
    expiry = Column(Date, nullable=False, index=True)

    # Tick Data
    price = Column(Numeric(18, 4))
    bid = Column(Numeric(18, 4))
    ask = Column(Numeric(18, 4))
    volume = Column(BigInteger)
    open_interest = Column(BigInteger)
    implied_vol = Column(Numeric(10, 4))

    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "timestamp",
            "symbol",
            "contract_type",
            "strike",
            "expiry",
            name="uq_deriv_tick_ts_sym_typ_strk_exp",
        ),
    )


class BlockDeal(Base, PostgresUpsertMixin):
    """Block Deal Data."""

    __tablename__ = "block_deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    security_name = Column(String(200))
    client_name = Column(String(200), index=True)
    buy_sell = Column(String(10))  # BUY / SELL
    quantity_traded = Column(BigInteger)
    trade_price = Column(Numeric(18, 4))
    remarks = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "date",
            "symbol",
            "client_name",
            "buy_sell",
            "trade_price",
            "quantity_traded",
            name="uq_block_deal",
        ),
    )


class BulkDeal(Base, PostgresUpsertMixin):
    """Bulk Deal Data."""

    __tablename__ = "bulk_deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    security_name = Column(String(200))
    client_name = Column(String(200), index=True)
    buy_sell = Column(String(10))  # BUY / SELL
    quantity_traded = Column(BigInteger)
    trade_price = Column(Numeric(18, 4))
    remarks = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "date",
            "symbol",
            "client_name",
            "buy_sell",
            "trade_price",
            "quantity_traded",
            name="uq_bulk_deal",
        ),
    )


class IndiaVIX(Base, PostgresUpsertMixin):
    """India VIX Daily historical values."""

    __tablename__ = "india_vix"

    timestamp = Column(DateTime(timezone=True), primary_key=True)
    open = Column(Numeric(10, 4), nullable=False)
    high = Column(Numeric(10, 4), nullable=False)
    low = Column(Numeric(10, 4), nullable=False)
    close = Column(Numeric(10, 4), nullable=False)
    prev_close = Column(Numeric(10, 4))
    change = Column(Numeric(10, 4))
    pct_change = Column(Numeric(10, 4))


class FuturesOI(Base, PostgresUpsertMixin):
    """Daily stock and index futures open interest."""

    __tablename__ = "futures_oi"

    timestamp = Column(DateTime(timezone=True), primary_key=True)
    symbol = Column(String(50), primary_key=True)
    expiry_date = Column(Date, primary_key=True)
    open_interest = Column(BigInteger, nullable=False, default=0)
    change_in_oi = Column(BigInteger, nullable=False, default=0)
    volume = Column(BigInteger, nullable=False, default=0)
    close = Column(Numeric(18, 4), nullable=False)


class ParticipantOI(Base, PostgresUpsertMixin):
    """Participant-wise Open Interest (OI) daily derivatives data."""

    __tablename__ = "participant_oi"

    trade_date = Column(Date, primary_key=True)
    category = Column(String(20), primary_key=True)  # FII, DII, PRO, CLIENT
    source = Column(String(20), primary_key=True)  # NSE, SENSIBULL

    # Futures Index
    futures_idx_long = Column(BigInteger, default=0)
    futures_idx_short = Column(BigInteger, default=0)
    futures_idx_net = Column(BigInteger, default=0)
    futures_idx_outstanding = Column(BigInteger, default=0)

    # Futures Stock
    futures_stk_long = Column(BigInteger, default=0)
    futures_stk_short = Column(BigInteger, default=0)
    futures_stk_net = Column(BigInteger, default=0)
    futures_stk_outstanding = Column(BigInteger, default=0)

    # Index Call Option
    option_call_long_oi = Column(BigInteger, default=0)
    option_call_long_oi_change = Column(BigInteger, default=0)
    option_call_short_oi = Column(BigInteger, default=0)
    option_call_short_oi_change = Column(BigInteger, default=0)
    option_call_net_oi = Column(BigInteger, default=0)
    option_call_net_oi_change = Column(BigInteger, default=0)

    # Index Put Option
    option_put_long_oi = Column(BigInteger, default=0)
    option_put_long_oi_change = Column(BigInteger, default=0)
    option_put_short_oi = Column(BigInteger, default=0)
    option_put_short_oi_change = Column(BigInteger, default=0)
    option_put_net_oi = Column(BigInteger, default=0)
    option_put_net_oi_change = Column(BigInteger, default=0)

    # Options Overall
    option_overall_net_oi = Column(BigInteger, default=0)
    option_overall_net_oi_change = Column(BigInteger, default=0)

    # Index-wise Futures
    nifty_fut_net_oi = Column(BigInteger, default=0)
    banknifty_fut_net_oi = Column(BigInteger, default=0)
    finnifty_fut_net_oi = Column(BigInteger, default=0)
    midcpnifty_fut_net_oi = Column(BigInteger, default=0)
    niftynxt50_fut_net_oi = Column(BigInteger, default=0)

    # Sentiment views
    futures_net_view = Column(String(20))
    futures_net_action = Column(String(20))
    futures_stk_net_view = Column(String(20))
    futures_stk_net_action = Column(String(20))
    options_net_view = Column(String(20))
    options_net_action = Column(String(20))

    # Market close snapshots
    nifty_close = Column(Numeric(18, 4))
    banknifty_close = Column(Numeric(18, 4))

    extras = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class DeliveryData(Base, PostgresUpsertMixin):
    """Daily spot delivery positions and percentages."""

    __tablename__ = "delivery_data"

    timestamp = Column(DateTime(timezone=True), primary_key=True)
    symbol = Column(String(50), primary_key=True)
    traded_qty = Column(BigInteger, nullable=False, default=0)
    deliverable_qty = Column(BigInteger, nullable=False, default=0)
    delivery_pct = Column(Numeric(6, 3), nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
