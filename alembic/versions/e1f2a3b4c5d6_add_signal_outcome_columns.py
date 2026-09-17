"""add signal outcome and lifecycle tracking columns to trading_signal

Revision ID: e1f2a3b4c5d6
Revises: d2e3f4a5b6c7
Create Date: 2026-09-17 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_signal",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="ACTIVE",
            nullable=False,
        ),
    )
    op.add_column(
        "trading_signal",
        sa.Column("exit_price", sa.Numeric(precision=14, scale=4), nullable=True),
    )
    op.add_column(
        "trading_signal",
        sa.Column("outcome_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trading_signal",
        sa.Column("pnl_pct", sa.Numeric(precision=6, scale=3), nullable=True),
    )
    op.add_column(
        "trading_signal",
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trading_signal",
        sa.Column("duration_days", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_trading_signal_status",
        "trading_signal",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_trading_signal_outcome_time",
        "trading_signal",
        ["outcome_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trading_signal_outcome_time", table_name="trading_signal")
    op.drop_index("ix_trading_signal_status", table_name="trading_signal")
    op.drop_column("trading_signal", "duration_days")
    op.drop_column("trading_signal", "duration_minutes")
    op.drop_column("trading_signal", "pnl_pct")
    op.drop_column("trading_signal", "outcome_time")
    op.drop_column("trading_signal", "exit_price")
    op.drop_column("trading_signal", "status")
