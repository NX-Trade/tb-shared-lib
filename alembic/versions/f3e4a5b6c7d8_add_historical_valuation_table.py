"""add historical_valuation table

Stores 10-year valuation multiples (P/E, P/BV, EV/EBITDA, MCap/Sales),
underlying fundamental bases (EPS, Book Value, EBITDA, Sales), quarterly
margins (GPM %, OPM %, NPM %), and reported benchmark medians from
Screener.in interactive charts.

Revision ID: f3e4a5b6c7d8
Revises: d3e4f5a6b7c8
Create Date: 2026-09-23 01:28:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f3e4a5b6c7d8"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "historical_valuation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pe", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("pb", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("ev_ebitda", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("market_cap_sales", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("eps", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("book_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("ebitda", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("sales", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("gpm_pct", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("opm_pct", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("npm_pct", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("median_pe", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("median_pb", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("median_ev_ebitda", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("median_market_cap_sales", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="SCREENER"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "timestamp", name="uq_historical_valuation_symbol_ts"),
    )
    op.create_index(
        op.f("ix_historical_valuation_symbol"),
        "historical_valuation",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_historical_valuation_timestamp"),
        "historical_valuation",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_historical_valuation_timestamp"), table_name="historical_valuation")
    op.drop_index(op.f("ix_historical_valuation_symbol"), table_name="historical_valuation")
    op.drop_table("historical_valuation")
