"""add max_open_option_baskets to client_account

How many option baskets (spreads) one account may hold open at once. Defaults to 1, which is what the
platform did before this column existed, so nothing changes until an operator raises it in Broker
Accounts. It limits new entries only; exits are never blocked.

Revision ID: x1a2b3c4d5f4
Revises: w1a2b3c4d5f3
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'x1a2b3c4d5f4'
down_revision: Union[str, None] = 'w1a2b3c4d5f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'client_account',
        sa.Column('max_open_option_baskets', sa.Integer(), server_default='1', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('client_account', 'max_open_option_baskets')
