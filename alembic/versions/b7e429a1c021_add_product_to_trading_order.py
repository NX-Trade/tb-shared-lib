"""add_product_to_trading_order

Revision ID: b7e429a1c021
Revises: a3f1c8b9e204
Create Date: 2026-09-11 09:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e429a1c021"
down_revision: Union[str, None] = "a3f1c8b9e204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_order",
        sa.Column("product", sa.String(length=10), nullable=True, server_default="D"),
    )


def downgrade() -> None:
    op.drop_column("trading_order", "product")
