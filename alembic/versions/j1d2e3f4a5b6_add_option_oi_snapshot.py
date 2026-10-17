"""add option_oi_snapshot

Whole-chain OI/volume totals per expiry, with the PCR and India VIX at that
timestamp. ``option_chain`` only keeps a window of strikes around spot, so a
PCR summed from it understates the expiry; NSE publishes totals for every
strike alongside the chain and this table stores them.

Revision ID: j1d2e3f4a5b6
Revises: i1c2i3c4i5d6
Create Date: 2026-10-17
"""

import sqlalchemy as sa
from alembic import op

revision = "j1d2e3f4a5b6"
down_revision = "i1c2i3c4i5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_oi_snapshot",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("total_call_oi", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_put_oi", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_call_volume", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_put_volume", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("pcr_oi", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("pcr_volume", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("vix", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="NSE"),
        sa.PrimaryKeyConstraint("ts", "symbol", "expiry_date"),
    )
    # The page reads one symbol's expiry series over a day, newest sessions first.
    op.create_index(
        "ix_option_oi_snapshot_symbol_expiry_ts",
        "option_oi_snapshot",
        ["symbol", "expiry_date", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_option_oi_snapshot_symbol_expiry_ts", table_name="option_oi_snapshot")
    op.drop_table("option_oi_snapshot")
