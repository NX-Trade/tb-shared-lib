"""add orders_disabled to client_account

Revision ID: d110b3f8bebb
Revises: 7368b84dc8fc
Create Date: 2026-09-29 15:32:53.383394

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd110b3f8bebb'
down_revision: Union[str, None] = '7368b84dc8fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'client_account',
        sa.Column('orders_disabled', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('client_account', 'orders_disabled')
