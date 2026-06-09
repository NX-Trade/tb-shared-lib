"""merge multiple heads

Revision ID: b2bcd654344c
Revises: 7bf9cfb158c9, f1d92e27965d
Create Date: 2026-06-09 11:38:52.374545

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2bcd654344c'
down_revision: Union[str, None] = ('7bf9cfb158c9', 'f1d92e27965d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
