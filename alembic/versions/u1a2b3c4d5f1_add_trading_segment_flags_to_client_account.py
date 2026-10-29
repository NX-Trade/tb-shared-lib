"""add trading segment flags to client_account

Per-account permission to open new trades in each market segment. All three default to false and
existing rows are deliberately NOT backfilled: after this runs, every existing account stops opening
new equity trades until an operator turns is_equity_trade_enabled back on in Broker Accounts. Exits,
stop auditing and reconciliation are unaffected.

Revision ID: u1a2b3c4d5f1
Revises: t1a2b3c4d5f0
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'u1a2b3c4d5f1'
down_revision: Union[str, None] = 't1a2b3c4d5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FLAGS = ('is_equity_trade_enabled', 'is_derivative_trade_enabled', 'is_commodity_trade_enabled')


def upgrade() -> None:
    op.add_column('client_account', sa.Column('is_equity_trade_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('client_account', sa.Column('is_derivative_trade_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('client_account', sa.Column('is_commodity_trade_enabled', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    for flag in reversed(FLAGS):
        op.drop_column('client_account', flag)
