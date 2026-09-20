"""add option_daily_metrics

EOD option-chain aggregates per underlying and expiry, derived from the NSE F&O
bhavcopy. The live chain endpoint has no history, so this is what makes PCR,
ATM IV and IV rank usable for training and backtesting.

Aggregate rather than raw strikes: the full surface is ~35k rows/day (~15M over
the archive from 2024-01), against ~245k here for the same span. Keyed per
expiry so near/next divergence and rollover are expressible — the live
collector stores only the near expiry for equities.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_daily_metrics",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("underlying_close", sa.Numeric(14, 2), nullable=True),
        sa.Column("expiry_rank", sa.Integer(), nullable=True),
        sa.Column("days_to_expiry", sa.Integer(), nullable=True),
        sa.Column("total_call_oi", sa.BigInteger(), server_default="0"),
        sa.Column("total_put_oi", sa.BigInteger(), server_default="0"),
        sa.Column("total_call_volume", sa.BigInteger(), server_default="0"),
        sa.Column("total_put_volume", sa.BigInteger(), server_default="0"),
        sa.Column("call_oi_change", sa.BigInteger(), server_default="0"),
        sa.Column("put_oi_change", sa.BigInteger(), server_default="0"),
        sa.Column("pcr_oi", sa.Numeric(10, 4), nullable=True),
        sa.Column("pcr_volume", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_pain_strike", sa.Numeric(14, 2), nullable=True),
        sa.Column("atm_strike", sa.Numeric(14, 2), nullable=True),
        sa.Column("atm_iv", sa.Numeric(10, 4), nullable=True),
        sa.Column("atm_call_iv", sa.Numeric(10, 4), nullable=True),
        sa.Column("atm_put_iv", sa.Numeric(10, 4), nullable=True),
        sa.Column("contracts_used", sa.Integer(), server_default="0"),
        sa.Column("source", sa.String(length=10), nullable=False, server_default="NSE_BHAVCOPY"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("trade_date", "symbol", "expiry_date"),
    )
    # Feature loaders read a per-symbol series ordered by date, filtered to the
    # near expiry; this index serves that access pattern directly.
    op.create_index(
        "ix_option_daily_metrics_symbol_date",
        "option_daily_metrics",
        ["symbol", "trade_date"],
    )
    op.create_index(
        "ix_option_daily_metrics_expiry_rank",
        "option_daily_metrics",
        ["expiry_rank"],
    )


def downgrade() -> None:
    op.drop_index("ix_option_daily_metrics_expiry_rank", table_name="option_daily_metrics")
    op.drop_index("ix_option_daily_metrics_symbol_date", table_name="option_daily_metrics")
    op.drop_table("option_daily_metrics")
