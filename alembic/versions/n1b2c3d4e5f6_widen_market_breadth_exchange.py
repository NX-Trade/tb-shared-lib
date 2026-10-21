"""widen market_breadth.exchange

Breadth is stored per index using the NSE index name (``NIFTY FINANCIAL SERVICES``,
``NIFTY INDIA INFRASTRUCTURE & LOGISTICS``), which overflowed ``varchar(10)`` and made
the whole ``sync_live_indices`` breadth insert fail. Widening a varchar is a
metadata-only change in Postgres and is safe on the hypertable.

Revision ID: n1b2c3d4e5f6
Revises: m1a2b3c4d5e6
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "n1b2c3d4e5f6"
down_revision = "m1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "market_breadth",
        "exchange",
        existing_type=sa.String(length=10),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "market_breadth",
        "exchange",
        existing_type=sa.String(length=64),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
