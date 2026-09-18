"""add_trading_order_submit_attempts

Makes broker submission exactly-once by construction.

``order_worker`` claimed work with ``status='PENDING' AND broker_order_id IS
NULL``, and wrote that same state back whenever the broker returned no order id.
The row was therefore re-queued on the next 30-second tick and the same order was
sent again — repeatedly, each attempt creating a real order at the broker.

The counter is incremented and committed *before* the broker call, so the queue
claims a row rather than releasing it, and a crash mid-flight cannot produce a
duplicate. Order placement is not idempotent: a duplicate order is real money,
while an un-submitted order is recoverable.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-18 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_order",
        sa.Column("submit_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    # Existing rows that already reached a broker must not be re-sent once the
    # queue starts filtering on this column.
    op.execute(
        "UPDATE trading_order SET submit_attempts = 1 "
        "WHERE broker_order_id IS NOT NULL OR status <> 'PENDING'"
    )


def downgrade() -> None:
    op.drop_column("trading_order", "submit_attempts")
