"""add trade.last_updated_at

When the open position's last_price and unrealized_pnl were last marked, so the Positions page can show
a "Last updated" time and a stale mark is visible. Nullable and not backfilled: a position gets a time the
next time the reconciler marks it.

Revision ID: z1a2b3c4d5f6
Revises: y1a2b3c4d5f5
Create Date: 2026-11-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'z1a2b3c4d5f6'
down_revision: Union[str, None] = 'y1a2b3c4d5f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trade', sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('trade', 'last_updated_at')
