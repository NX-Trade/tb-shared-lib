"""add platform_setting and platform_setting_history

Operator-editable settings kept in the database instead of environment variables: one JSON row per
setting group, validated in code, with a version and a history of every change. The first user is the
STC option-spread dispatcher (master switch, basket caps, entry window, exit times). No rows are
inserted: until a group is saved the service uses its environment, then the safe code defaults.

Revision ID: w1a2b3c4d5f3
Revises: v1a2b3c4d5f2
Create Date: 2026-10-30 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'w1a2b3c4d5f3'
down_revision: Union[str, None] = 'v1a2b3c4d5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platform_setting',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'platform_setting_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('old_value', sa.JSON(), nullable=True),
        sa.Column('new_value', sa.JSON(), nullable=False),
        sa.Column('changed_by', sa.String(length=100), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_platform_setting_history_key', 'platform_setting_history', ['key'])


def downgrade() -> None:
    op.drop_index('ix_platform_setting_history_key', table_name='platform_setting_history')
    op.drop_table('platform_setting_history')
    op.drop_table('platform_setting')
