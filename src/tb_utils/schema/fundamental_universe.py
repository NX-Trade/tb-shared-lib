"""Fundamental Universe API Schemas."""

from datetime import datetime
from typing import Optional

from .base import BaseSchema


class FundamentalUniverseResponse(BaseSchema):
    """Response schema for FundamentalUniverse records."""

    id: int
    symbol: str
    isin: Optional[str] = None
    company_name: Optional[str] = None
    bse_code: Optional[str] = None

    # Classification
    screen_id: int
    basket_tag: str
    industry_group: Optional[str] = None
    industry: Optional[str] = None

    # Price & Valuation
    current_price: Optional[float] = None
    market_cap_cr: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    industry_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    book_value: Optional[float] = None
    dividend_yield: Optional[float] = None
    ev_ebitda: Optional[float] = None

    # Profitability
    roce: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    piotroski_score: Optional[int] = None
    cfo_pat: Optional[float] = None
    working_capital_days: Optional[float] = None

    # Growth & Solvency
    sales_growth_3yr: Optional[float] = None
    profit_growth_3yr: Optional[float] = None
    debt_to_equity: Optional[float] = None
    pledged_percentage: Optional[float] = None

    # Ownership
    promoter_holding: Optional[float] = None
    fii_holding: Optional[float] = None
    dii_holding: Optional[float] = None

    # Metadata
    is_active: Optional[bool] = True
    synced_at: Optional[datetime] = None


class FundamentalBasketSummary(BaseSchema):
    """Summary metrics per basket_tag."""

    basket_tag: str
    count: int
    avg_pe: Optional[float] = None
    avg_roce: Optional[float] = None
    avg_roe: Optional[float] = None
    avg_piotroski: Optional[float] = None
    avg_debt_to_equity: Optional[float] = None
    total_market_cap_cr: Optional[float] = None
