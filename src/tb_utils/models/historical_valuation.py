"""Historical Valuation Model for multi-year fundamentals and valuation ratios."""

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class HistoricalValuation(Base, PostgresUpsertMixin):
    """Stores historical valuation metrics, margins, and fundamental bases for an instrument.

    Sourced from Screener.in's 10-year interactive valuation charts, providing
    weekly historical points for P/E, P/BV, EV/EBITDA, quarterly margins (GPM, OPM, NPM),
    and reported 10Y/5Y medians.
    """

    __tablename__ = "historical_valuation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Valuation Multiples
    pe = Column(Numeric(10, 2), nullable=True)
    pb = Column(Numeric(10, 2), nullable=True)
    ev_ebitda = Column(Numeric(10, 2), nullable=True)
    market_cap_sales = Column(Numeric(10, 2), nullable=True)

    # Underlying Fundamental Bases
    eps = Column(Numeric(12, 2), nullable=True)
    book_value = Column(Numeric(12, 2), nullable=True)
    ebitda = Column(Numeric(14, 2), nullable=True)
    sales = Column(Numeric(14, 2), nullable=True)

    # Profitability Margins (%)
    gpm_pct = Column(Numeric(6, 2), nullable=True)
    opm_pct = Column(Numeric(6, 2), nullable=True)
    npm_pct = Column(Numeric(6, 2), nullable=True)

    # Benchmark Multiples (e.g. 10Y / 5Y Screener reported medians)
    median_pe = Column(Numeric(10, 2), nullable=True)
    median_pb = Column(Numeric(10, 2), nullable=True)
    median_ev_ebitda = Column(Numeric(10, 2), nullable=True)
    median_market_cap_sales = Column(Numeric(10, 2), nullable=True)

    # Metadata
    source = Column(String(20), nullable=False, default="SCREENER")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uq_historical_valuation_symbol_ts"),
    )

    def __repr__(self) -> str:
        return (
            f"<HistoricalValuation(symbol='{self.symbol}', "
            f"timestamp='{self.timestamp}', "
            f"pe={self.pe}, pb={self.pb}, ev_ebitda={self.ev_ebitda})>"
        )
