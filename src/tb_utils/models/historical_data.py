"""Historical Data and Timeseries Hypertables Models."""

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)

from tb_utils.utils.enums import SourceEnum

from .base import Base, PostgresUpsertMixin


class HistoricalEquityData(Base, PostgresUpsertMixin):
    """Historical Equity Data."""

    __tablename__ = "historical_equity_data"

    historical_equity_data_id = Column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instrument.instrument_id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    open = Column(Numeric(10, 2), nullable=False)
    high = Column(Numeric(10, 2), nullable=False)
    low = Column(Numeric(10, 2), nullable=False)
    close = Column(Numeric(10, 2), nullable=False)
    adj_close = Column(Numeric(10, 2))
    volume = Column(BigInteger, nullable=False)
    # SourceEnum can be ICICI, IB, NSE
    source_id = Column(SmallInteger, nullable=False, default=SourceEnum.IB.value)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uix_historical_data_key"),
    )


class HistoricalIndexData(Base, PostgresUpsertMixin):
    """Historical Index Data."""

    __tablename__ = "historical_index_data"

    historical_index_data_id = Column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id = Column(Integer, ForeignKey("instrument.instrument_id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    index_name = Column(String(20), nullable=False, index=True)
    open = Column(Numeric(10, 2), nullable=False)
    high = Column(Numeric(10, 2), nullable=False)
    low = Column(Numeric(10, 2), nullable=False)
    close = Column(Numeric(10, 2), nullable=False)
    adj_close = Column(Numeric(10, 2))
    shares_traded = Column(BigInteger)
    turnover_cr = Column(Numeric(14, 2))
    # SourceEnum can be ICICI, IB, NSE
    source_id = Column(SmallInteger, nullable=False, default=SourceEnum.NSE.value)

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
    """Live option chain snapshots.

    Not a hypertable, despite what this docstring claimed until 2026-09-20 —
    ``timescaledb_information.hypertables`` was empty. Left as a plain table:
    intraday rows are pruned to 5 days by ADR-005 (exempting the 15:30 golden
    records), so it does not accumulate the volume that would justify
    partitioning.
    """

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
    underlying_value = Column(Numeric(14, 2))
    source = Column(String(10), nullable=False, default="NSE")


class IntradayCandle(Base, PostgresUpsertMixin):
    """Intraday OHLCV bars, kept apart from ``historical_equity_data``.

    **TimescaleDB hypertable** — partitioned on ``timestamp`` in 1-month chunks,
    with compression on chunks older than 90 days segmented by
    ``(symbol, timeframe)``. See migration ``a9b0c1d2e3f4``. It is the only
    hypertable in the schema; ``historical_equity_data`` cannot be one while it
    keeps a surrogate primary key, since TimescaleDB requires every unique index
    to include the partitioning column.

    That table has a ``timeframe`` column and would technically accept
    ``'15 minute'``, which is the trap. Three reasons it lives here instead:

    * **Retention differs.** Daily bars are permanent history; intraday is
      bulky and prunable, the same split ADR-005 already applies to intraday
      option data.
    * **Query isolation.** Every daily query filters ``timeframe = '1 day'``.
      Millions of intraday rows in the same table make those filters scan a
      far larger index — a permanent tax on the 600-bar training load and
      every feature query.
    * **Write cadence differs** — one EOD batch against continuous appends.

    Stored at **5-minute** granularity over the F&O universe: 75 bars/session x
    ~220 symbols x ~1,170 sessions from 2022-01 is ~19M rows.

    5m rather than 15m because aggregation only runs one way. OHLCV aggregation
    is associative (open=first, high=max, low=min, close=last, volume=sum), so
    5m -> 15m yields bars identical to resampling from 1m, and VWAP is preserved
    because the STC path computes typical_price on the *15m* bar. 15m -> 5m is
    impossible, so storing the coarser bar would discard optionality no later
    strategy could recover. 1-minute was rejected as the floor: ~96M rows to
    serve a sub-5-minute strategy that does not exist.

    ``timeframe`` is part of the primary key, so several granularities coexist.
    """

    __tablename__ = "intraday_candle"

    symbol = Column(String(50), primary_key=True)
    # '1 minute' | '5 minute' | '15 minute' | '1 hour'
    timeframe = Column(String(16), primary_key=True)
    timestamp = Column(DateTime(timezone=True), primary_key=True)

    # Upstox key, retained so a bar can be re-fetched or traced to its source
    # contract — expired option contracts carry their own key.
    instrument_key = Column(String(80), index=True)
    segment = Column(String(10))  # EQ | FO | INDEX

    open = Column(Numeric(14, 4))
    high = Column(Numeric(14, 4))
    low = Column(Numeric(14, 4))
    close = Column(Numeric(14, 4))
    volume = Column(BigInteger, default=0)
    # NULL for cash equity; populated for futures and options.
    open_interest = Column(BigInteger, nullable=True)

    source = Column(String(20), nullable=False, default="UPSTOX")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OptionDailyMetrics(Base, PostgresUpsertMixin):
    """EOD option-chain aggregates per underlying and expiry.

    Derived from the NSE F&O bhavcopy, which publishes every contract daily and
    is archived from ~2024-01 — unlike the live chain endpoint, which offers no
    history. This is what makes PCR, ATM IV and IV rank available for training
    and backtesting at all.

    Stored as an aggregate rather than raw strikes: the full option surface is
    ~35,000 rows a day (~15M over the archive), while one row per
    (date, symbol, expiry) is ~245k for the same span. Raw strikes are only
    needed for strike-level work such as max-pain curves or GEX by strike; the
    metrics that feed the screener and the scanners are all summable here.

    Keyed per expiry rather than per symbol so near/next divergence and
    rollover are expressible — the live collector stores only the near expiry
    for equities (105 symbols), which is why those remain unanswerable today.
    """

    __tablename__ = "option_daily_metrics"

    trade_date = Column(Date, primary_key=True)
    symbol = Column(String(30), primary_key=True)
    expiry_date = Column(Date, primary_key=True)

    underlying_close = Column(Numeric(14, 2))
    # Rank of this expiry on the date: 1 = nearest, 2 = next, ...
    expiry_rank = Column(Integer, index=True)
    days_to_expiry = Column(Integer)

    total_call_oi = Column(BigInteger, default=0)
    total_put_oi = Column(BigInteger, default=0)
    total_call_volume = Column(BigInteger, default=0)
    total_put_volume = Column(BigInteger, default=0)
    call_oi_change = Column(BigInteger, default=0)
    put_oi_change = Column(BigInteger, default=0)

    pcr_oi = Column(Numeric(10, 4))
    pcr_volume = Column(Numeric(10, 4))
    # Strike where option writers lose least — sum of ITM payoff is minimised.
    max_pain_strike = Column(Numeric(14, 2))

    atm_strike = Column(Numeric(14, 2))
    # Mean of the ATM call and put IV, solved from settlement prices via
    # tb_utils.greeks.implied_volatility (the bhavcopy carries no IV).
    atm_iv = Column(Numeric(10, 4))
    atm_call_iv = Column(Numeric(10, 4))
    atm_put_iv = Column(Numeric(10, 4))

    contracts_used = Column(Integer, default=0)
    # 20, not 10: "NSE_BHAVCOPY" is 12 characters and silently failed every
    # insert with StringDataRightTruncation on the narrower column.
    source = Column(String(20), nullable=False, default="NSE_BHAVCOPY")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
