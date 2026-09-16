"""add_index_yield_table

Revision ID: e852b7e39c03
Revises: d4a1b7e39c02
Create Date: 2026-08-10 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e852b7e39c03'
down_revision: Union[str, None] = 'd4a1b7e39c02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'index_yield',
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('index_name', sa.String(length=50), nullable=False),
        sa.Column('pe', sa.Numeric(precision=8, scale=2), nullable=False, server_default='0.0'),
        sa.Column('pb', sa.Numeric(precision=8, scale=2), nullable=False, server_default='0.0'),
        sa.Column('div_yield', sa.Numeric(precision=6, scale=3), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('timestamp', 'index_name', name='index_yield_pkey')
    )
    op.create_index(op.f('ix_index_yield_index_name'), 'index_yield', ['index_name'], unique=False)
    op.create_index(op.f('ix_index_yield_timestamp'), 'index_yield', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_index_yield_timestamp'), table_name='index_yield')
    op.drop_index(op.f('ix_index_yield_index_name'), table_name='index_yield')
    op.drop_table('index_yield')
