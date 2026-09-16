"""add_error_message_to_trading_order

Revision ID: a3f1c8b9e204
Revises: f837c49d10e1
Create Date: 2026-09-10 06:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f1c8b9e204"
down_revision: Union[str, None] = "f837c49d10e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_order",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trading_order", "error_message")
