"""create_execution_plan_table

Durable state machine for tb-execution's limit → TWAP entry executor. Replaces
the in-process ``time.sleep(180)`` + un-joined daemon TWAP thread, so an entry
in progress survives a worker restart and never blocks the Celery beat.

Revision ID: a3b4c5d6e7f8
Revises: g1b2c3d4e5f6
Create Date: 2026-09-18 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSON

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "g1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_plan",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("broker_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        # Reuses the existing order_side enum type — do not create it here.
        sa.Column(
            "side",
            ENUM("BUY", "SELL", "HOLD", name="order_side", create_type=False),
            nullable=False,
        ),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("stop_loss_price", sa.Numeric(precision=14, scale=4), server_default="0", nullable=False),
        sa.Column("target_price", sa.Numeric(precision=14, scale=4), server_default="0", nullable=False),
        sa.Column("fee_round_trip", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
        sa.Column("state", sa.String(length=20), server_default="LIMIT_ACTIVE", nullable=False),
        sa.Column("entry_order_id", sa.Integer(), nullable=True),
        sa.Column("limit_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("twap_slices_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("twap_slices_done", sa.Integer(), server_default="0", nullable=False),
        sa.Column("twap_remaining_qty", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_slice_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_fill_price", sa.Numeric(precision=14, scale=4), server_default="0", nullable=False),
        sa.Column("broker_order_ids", JSON(), server_default="[]", nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.instrument_id"]),
        sa.ForeignKeyConstraint(["broker_id"], ["broker.broker_id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["trading_signal.signal_id"]),
        sa.ForeignKeyConstraint(["entry_order_id"], ["trading_order.order_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_execution_plan_instrument_id"), "execution_plan", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_execution_plan_state"), "execution_plan", ["state"], unique=False)
    op.create_index(op.f("ix_execution_plan_created_at"), "execution_plan", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_execution_plan_created_at"), table_name="execution_plan")
    op.drop_index(op.f("ix_execution_plan_state"), table_name="execution_plan")
    op.drop_index(op.f("ix_execution_plan_instrument_id"), table_name="execution_plan")
    op.drop_table("execution_plan")
