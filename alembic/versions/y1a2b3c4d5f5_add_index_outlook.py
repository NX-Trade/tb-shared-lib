"""add index_outlook

The AI commentary for Nifty 50 and Bank Nifty on the dashboard: one row per generation (pre-market,
close, or a manual refresh) with the evidence the model saw and what it answered. No rows are inserted.

Revision ID: y1a2b3c4d5f5
Revises: x1a2b3c4d5f4
Create Date: 2026-10-30 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'y1a2b3c4d5f5'
down_revision: Union[str, None] = 'x1a2b3c4d5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'index_outlook',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('as_of', sa.DateTime(timezone=True), nullable=False),
        sa.Column('mode', sa.String(length=12), nullable=False),
        sa.Column('degraded', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('model_name', sa.String(length=64), nullable=True),
        sa.Column('prompt_version', sa.String(length=16), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('output', sa.JSON(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_inr', sa.Float(), nullable=True),
        sa.Column('requested_by', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_index_outlook_symbol', 'index_outlook', ['symbol'])
    op.create_index('ix_index_outlook_as_of', 'index_outlook', ['as_of'])


def downgrade() -> None:
    op.drop_index('ix_index_outlook_as_of', table_name='index_outlook')
    op.drop_index('ix_index_outlook_symbol', table_name='index_outlook')
    op.drop_table('index_outlook')
