"""add_recommendation_entry_exit_prices

Revision ID: 7bf9cfb158c9
Revises: 6af9cfb158c9
Create Date: 2026-05-28 17:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7bf9cfb158c9'
down_revision: Union[str, None] = '6af9cfb158c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recommendation', sa.Column('entry_price', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column('recommendation', sa.Column('exit_price', sa.Numeric(precision=18, scale=4), nullable=True))


def downgrade() -> None:
    op.drop_column('recommendation', 'exit_price')
    op.drop_column('recommendation', 'entry_price')
