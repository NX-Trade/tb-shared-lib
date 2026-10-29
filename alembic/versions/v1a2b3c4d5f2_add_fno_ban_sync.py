"""add fno_ban_sync

One row per trading day whose F&O ban list was synced. fno_ban_list holds only banned symbols, so a
day with nobody banned leaves no rows there and cannot be told apart from a day the sync never ran;
the guard that blocks new option entries on banned names needs that difference. No backfill: past
days stay "unknown", which only matters for today.

Revision ID: v1a2b3c4d5f2
Revises: u1a2b3c4d5f1
Create Date: 2026-10-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'v1a2b3c4d5f2'
down_revision: Union[str, None] = 'u1a2b3c4d5f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fno_ban_sync',
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('banned_count', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('trade_date'),
    )


def downgrade() -> None:
    op.drop_table('fno_ban_sync')
