"""add_trade_stop_order_id

Revision ID: a3f7c2e91b04
Revises: ee6367c36683
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c2e91b04'
down_revision: Union[str, None] = 'ee6367c36683'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trade', sa.Column('stop_order_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'trade_stop_order_id_fkey', 'trade', 'trading_order', ['stop_order_id'], ['order_id']
    )


def downgrade() -> None:
    op.drop_constraint('trade_stop_order_id_fkey', 'trade', type_='foreignkey')
    op.drop_column('trade', 'stop_order_id')
