"""add_strategy_cluster_to_trading_signal

Revision ID: b8f1a2c3d4e5
Revises: b7e429a1c021
Create Date: 2026-09-14 20:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8f1a2c3d4e5"
down_revision: Union[str, None] = "b7e429a1c021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add nullable strategy_cluster column with index
    op.add_column(
        "trading_signal",
        sa.Column("strategy_cluster", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_trading_signal_strategy_cluster",
        "trading_signal",
        ["strategy_cluster"],
    )

    # 2. Backfill existing rows according to strategy_name
    op.execute(
        "UPDATE trading_signal SET strategy_cluster = 'DELIVERY_ACCUMULATION' "
        "WHERE strategy_name LIKE 'delivery_%'"
    )
    op.execute(
        "UPDATE trading_signal SET strategy_cluster = 'SHORT_TERM_CLUSTER' "
        "WHERE strategy_name = 'short_term_cluster'"
    )
    op.execute(
        "UPDATE trading_signal SET strategy_cluster = 'LONG_TERM_CLUSTER' "
        "WHERE strategy_name = 'long_term_cluster'"
    )
    op.execute(
        "UPDATE trading_signal SET strategy_cluster = 'FNO_DERIVATIVES' "
        "WHERE strategy_name LIKE 'fno_%'"
    )


def downgrade() -> None:
    op.drop_index("ix_trading_signal_strategy_cluster", table_name="trading_signal")
    op.drop_column("trading_signal", "strategy_cluster")
