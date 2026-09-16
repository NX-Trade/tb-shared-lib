"""Fundamental Universe Model from Screener.in Sync."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base, PostgresUpsertMixin


class FundamentalUniverse(Base, PostgresUpsertMixin):
    """Stores fundamentally approved instruments from Screener.in screens."""

    __tablename__ = "fundamental_universe"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    isin = Column(String(50), index=True)
    company_name = Column(String(250))
    bse_code = Column(String(20))

    # System & Screen Classification
    screen_id = Column(Integer, nullable=False, index=True)  # 3947466, 3947463, 3947460
    basket_tag = Column(
        String(50), nullable=False, index=True
    )  # CAPGOODS_INFRA, GARP_VALUE, QUALITY_COMPOUNDERS
    industry_group = Column(String(100))
    industry = Column(String(100))

    # Price & Valuation Ratios
    current_price = Column(Numeric(12, 2))
    market_cap_cr = Column(Numeric(14, 2))
    high_price = Column(Numeric(12, 2))
    low_price = Column(Numeric(12, 2))
    pe_ratio = Column(Numeric(10, 2))
    pb_ratio = Column(Numeric(10, 2))
    industry_pe = Column(Numeric(10, 2))
    peg_ratio = Column(Numeric(10, 2))
    book_value = Column(Numeric(12, 2))
    dividend_yield = Column(Numeric(10, 2))
    ev_ebitda = Column(Numeric(10, 2))

    # Profitability & Operating Moat
    roce = Column(Numeric(10, 2))
    roe = Column(Numeric(10, 2))
    roa = Column(Numeric(10, 2))
    piotroski_score = Column(Integer)
    cfo_pat = Column(Numeric(10, 2))
    working_capital_days = Column(Numeric(10, 2))

    # Multi-Year Growth & Solvency
    sales_growth_3yr = Column(Numeric(10, 2))
    profit_growth_3yr = Column(Numeric(10, 2))
    debt_to_equity = Column(Numeric(10, 2))
    pledged_percentage = Column(Numeric(10, 2))

    # Ownership Structure
    promoter_holding = Column(Numeric(10, 2))
    fii_holding = Column(Numeric(10, 2))
    dii_holding = Column(Numeric(10, 2))

    # System Metadata & JSON Payload
    raw_metrics = Column(JSONB)
    is_active = Column(Boolean, default=True, index=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("symbol", "screen_id", name="uq_fund_universe_symbol_screen"),
    )

    def __repr__(self) -> str:
        return (
            f"<FundamentalUniverse(symbol='{self.symbol}', "
            f"screen_id={self.screen_id}, "
            f"basket='{self.basket_tag}', "
            f"mcap={self.market_cap_cr})>"
        )
