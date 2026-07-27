"""add_nifty_500_as_of_date_table

Revision ID: c73d9021f100
Revises: a3f7c2e91b04
Create Date: 2026-07-27 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c73d9021f100'
down_revision: Union[str, None] = 'a3f7c2e91b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'nifty_500_as_of_date',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('is_member', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('weight', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('as_of_date', 'symbol', name='uix_nifty_500_as_of_date_sym')
    )
    op.create_index(op.f('ix_nifty_500_as_of_date_as_of_date'), 'nifty_500_as_of_date', ['as_of_date'], unique=False)
    op.create_index(op.f('ix_nifty_500_as_of_date_symbol'), 'nifty_500_as_of_date', ['symbol'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_nifty_500_as_of_date_symbol'), table_name='nifty_500_as_of_date')
    op.drop_index(op.f('ix_nifty_500_as_of_date_as_of_date'), table_name='nifty_500_as_of_date')
    op.drop_table('nifty_500_as_of_date')
