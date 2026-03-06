"""Add fiidii_derivatives table and update fiidii table.

Revision ID: 0d74251f71ff
Revises: 8ec9a1295d43
Create Date: 2026-03-06 12:15:45.068963

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "0d74251f71ff"
down_revision: Union[str, None] = "8ec9a1295d43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create fiidii_derivatives table ──────────────────────────────────
    op.create_table(
        "fiidii_derivatives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("instrument_type", sa.String(20), nullable=False),
        sa.Column("category", sa.String(10), nullable=False),
        # Futures fields
        sa.Column("net_oi", sa.Numeric(18, 2), default=0),
        sa.Column("outstanding_oi", sa.Numeric(18, 2), default=0),
        sa.Column("net_action", sa.String(10)),
        sa.Column("net_view", sa.String(10)),
        sa.Column("net_view_strength", sa.String(10)),
        # Stock futures
        sa.Column("stock_net_oi", sa.Numeric(18, 2), default=0),
        sa.Column("stock_outstanding_oi", sa.Numeric(18, 2), default=0),
        sa.Column("stock_net_action", sa.String(10)),
        sa.Column("stock_net_view", sa.String(10)),
        sa.Column("stock_net_view_strength", sa.String(10)),
        # Options overall
        sa.Column("options_net_oi", sa.Numeric(18, 2), default=0),
        sa.Column("options_net_oi_change", sa.Numeric(18, 2), default=0),
        sa.Column("options_net_oi_change_action", sa.String(10)),
        sa.Column("options_net_oi_change_view", sa.String(10)),
        sa.Column("options_net_oi_change_view_strength", sa.String(10)),
        # Market snapshot
        sa.Column("nifty", sa.Numeric(12, 2)),
        sa.Column("nifty_change_pct", sa.Numeric(8, 4)),
        sa.Column("banknifty", sa.Numeric(12, 2)),
        sa.Column("banknifty_change_pct", sa.Numeric(8, 4)),
        # JSONB extras
        sa.Column("extras", JSONB, default={}),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trade_date",
            "source",
            "category",
            "instrument_type",
            name="fiidii_deriv_date_src_cat_inst_key",
        ),
    )

    # ── Update fiidii table — add source, net_action, net_view, net_view_strength ─
    op.add_column("fiidii", sa.Column("source", sa.String(20), nullable=True))
    op.add_column("fiidii", sa.Column("net_action", sa.String(10)))
    op.add_column("fiidii", sa.Column("net_view", sa.String(10)))
    op.add_column("fiidii", sa.Column("net_view_strength", sa.String(10)))

    # Backfill existing rows with default source
    op.execute("UPDATE fiidii SET source = 'NSE' WHERE source IS NULL")
    op.alter_column("fiidii", "source", nullable=False)

    # ── Fix instrument.symbol nullable ─────────────────────────────────────
    op.alter_column(
        "instrument", "symbol", existing_type=sa.VARCHAR(length=100), nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "instrument", "symbol", existing_type=sa.VARCHAR(length=100), nullable=True
    )

    op.drop_column("fiidii", "net_view_strength")
    op.drop_column("fiidii", "net_view")
    op.drop_column("fiidii", "net_action")
    op.drop_column("fiidii", "source")

    op.drop_table("fiidii_derivatives")
