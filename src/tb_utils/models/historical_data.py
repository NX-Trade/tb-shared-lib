"""Historical Data and Timeseries Hypertables Models."""

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from .base import Base, PostgresUpsertMixin


class HistoricalEquityData(Base, PostgresUpsertMixin):
    """Historical Equity Data."""

    __tablename__ = "historical_equity_data"

    historical_equity_data_id = Column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id = Column(
        Integer, ForeignKey("instrument.instrument_id"), nullable=False
    )
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    open = Column(Numeric(10, 2), nullable=False)
    high = Column(Numeric(10, 2), nullable=False)
    low = Column(Numeric(10, 2), nullable=False)
    close = Column(Numeric(10, 2), nullable=False)
    adj_close = Column(Numeric(10, 2))
    volume = Column(BigInteger, nullable=False)
    broker_id = Column(Integer, ForeignKey("broker.broker_id"))

    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "timestamp", name="uix_historical_data_key"
        ),
    )


class HistoricalIndexData(Base, PostgresUpsertMixin):
    """Historical Index Data."""

    __tablename__ = "historical_index_data"

    historical_index_data_id = Column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id = Column(
        Integer, ForeignKey("instrument.instrument_id"), nullable=False
    )
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    index_name = Column(String(20), nullable=False, index=True)
    open = Column(Numeric(10, 2), nullable=False)
    high = Column(Numeric(10, 2), nullable=False)
    low = Column(Numeric(10, 2), nullable=False)
    close = Column(Numeric(10, 2), nullable=False)
    adj_close = Column(Numeric(10, 2))
    broker_id = Column(Integer, ForeignKey("broker.broker_id"))

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "timestamp",
            "index_name",
            name="uix_historical_index_data_key",
        ),
    )


class Candle(Base, PostgresUpsertMixin):
    """Candle time-series hypertable."""

    __tablename__ = "candle"

    ts = Column(DateTime(timezone=True), primary_key=True)
    symbol = Column(String(30), primary_key=True)
    timeframe = Column(String(10), primary_key=True)

    open = Column(Numeric(14, 4), nullable=False)
    high = Column(Numeric(14, 4), nullable=False)
    low = Column(Numeric(14, 4), nullable=False)
    close = Column(Numeric(14, 4), nullable=False)
    volume = Column(BigInteger, nullable=False, default=0)
    vwap = Column(Numeric(14, 4))
    source = Column(String(10), nullable=False, default="IB")


class OptionChain(Base, PostgresUpsertMixin):
    """Option Chain time-series hypertable."""

    __tablename__ = "option_chain"

    ts = Column(DateTime(timezone=True), primary_key=True)
    symbol = Column(String(30), primary_key=True)
    expiry_date = Column(Date, primary_key=True)
    strike_price = Column(Numeric(14, 2), primary_key=True)
    option_type = Column(String(2), primary_key=True)

    open = Column(Numeric(14, 4))
    high = Column(Numeric(14, 4))
    low = Column(Numeric(14, 4))
    close = Column(Numeric(14, 4))
    ltp = Column(Numeric(14, 4))
    volume = Column(BigInteger, default=0)
    open_interest = Column(BigInteger, default=0)
    change_in_oi = Column(BigInteger, default=0)
    implied_vol = Column(Numeric(10, 4))
    delta = Column(Numeric(10, 6))
    gamma = Column(Numeric(10, 6))
    theta = Column(Numeric(10, 6))
    vega = Column(Numeric(10, 6))
    bid_price = Column(Numeric(14, 4))
    ask_price = Column(Numeric(14, 4))
    bid_qty = Column(Integer)
    ask_qty = Column(Integer)
    source = Column(String(10), nullable=False, default="NSE")
