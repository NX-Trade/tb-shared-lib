"""add option_strategy_leg.lots

Legs had no quantity, so a ratio structure (a 1x2x1 butterfly, a ratio spread) could not be
stored: the doubled short leg was recorded once and every consumer sized it at one lot.
``lots`` is the ratio unit count of the strategy's ``lot_size`` for one structure. Existing
rows are all 1-lot-per-leg verticals, so the server default backfills them correctly.

Revision ID: o1c2d3e4f5a6
Revises: n1b2c3d4e5f6
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "o1c2d3e4f5a6"
down_revision = "n1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "option_strategy_leg",
        sa.Column("lots", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("option_strategy_leg", "lots")
