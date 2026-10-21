"""add trade.unrealized_pnl

The ``Trade`` model has always declared ``unrealized_pnl``, but no migration ever created it on
``trade`` (the initial migration only put it on ``system_metric`` and the since-dropped
``position`` table). Every ``SELECT`` of the model therefore failed on a database built from
migrations with ``column trade.unrealized_pnl does not exist``, taking the trades endpoints down.
Idempotent, so a database that already has the column is left alone.

Revision ID: q1f2a3b4c5d7
Revises: p1e2f3a4b5c6
Create Date: 2026-10-22
"""

from alembic import op

revision = "q1f2a3b4c5d7"
down_revision = "p1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE trade ADD COLUMN IF NOT EXISTS unrealized_pnl NUMERIC(10, 2) DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE trade DROP COLUMN IF EXISTS unrealized_pnl")
