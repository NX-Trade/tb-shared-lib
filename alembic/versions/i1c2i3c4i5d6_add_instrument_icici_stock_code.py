"""Add instrument.icici_stock_code for ICICI Direct (Breeze) order routing.

Revision ID: i1c2i3c4i5d6
Revises: e2f3a4b5c6d7
Create Date: 2026-10-16 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i1c2i3c4i5d6"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("instrument", sa.Column("icici_stock_code", sa.String(length=20), nullable=True))
    op.create_index(
        op.f("ix_instrument_icici_stock_code"), "instrument", ["icici_stock_code"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_instrument_icici_stock_code"), table_name="instrument")
    op.drop_column("instrument", "icici_stock_code")
