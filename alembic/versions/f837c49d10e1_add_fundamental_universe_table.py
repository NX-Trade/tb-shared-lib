"""add_fundamental_universe_table

Revision ID: f837c49d10e1
Revises: e852b7e39c03
Create Date: 2026-09-09 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f837c49d10e1"
down_revision: Union[str, None] = "e852b7e39c03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fundamental_universe",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("isin", sa.String(length=50), nullable=True),
        sa.Column("company_name", sa.String(length=250), nullable=True),
        sa.Column("bse_code", sa.String(length=20), nullable=True),
        sa.Column("screen_id", sa.Integer(), nullable=False),
        sa.Column("basket_tag", sa.String(length=50), nullable=False),
        sa.Column("industry_group", sa.String(length=100), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("current_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("market_cap_cr", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("high_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("low_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("pe_ratio", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("pb_ratio", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("industry_pe", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("peg_ratio", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("book_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("ev_ebitda", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("roce", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("roe", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("roa", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("piotroski_score", sa.Integer(), nullable=True),
        sa.Column("cfo_pat", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("working_capital_days", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("sales_growth_3yr", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("profit_growth_3yr", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("pledged_percentage", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("promoter_holding", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("fii_holding", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("dii_holding", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("raw_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "screen_id", name="uq_fund_universe_symbol_screen"),
    )
    op.create_index(op.f("ix_fundamental_universe_symbol"), "fundamental_universe", ["symbol"], unique=False)
    op.create_index(op.f("ix_fundamental_universe_isin"), "fundamental_universe", ["isin"], unique=False)
    op.create_index(op.f("ix_fundamental_universe_screen_id"), "fundamental_universe", ["screen_id"], unique=False)
    op.create_index(op.f("ix_fundamental_universe_basket_tag"), "fundamental_universe", ["basket_tag"], unique=False)
    op.create_index(op.f("ix_fundamental_universe_is_active"), "fundamental_universe", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fundamental_universe_is_active"), table_name="fundamental_universe")
    op.drop_index(op.f("ix_fundamental_universe_basket_tag"), table_name="fundamental_universe")
    op.drop_index(op.f("ix_fundamental_universe_screen_id"), table_name="fundamental_universe")
    op.drop_index(op.f("ix_fundamental_universe_isin"), table_name="fundamental_universe")
    op.drop_index(op.f("ix_fundamental_universe_symbol"), table_name="fundamental_universe")
    op.drop_table("fundamental_universe")
