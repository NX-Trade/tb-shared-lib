"""drop_recommendation_table

Revision ID: g1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-09-18 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g1b2c3d4e5f6"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_recommendation_timestamp"), table_name="recommendation")
    op.drop_index(op.f("ix_recommendation_symbol"), table_name="recommendation")
    op.drop_table("recommendation")


def downgrade() -> None:
    op.create_table(
        "recommendation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("asset_class", sa.String(length=20), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("option_type", sa.String(length=10), nullable=True),
        sa.Column("strike_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("entry_price_range", sa.String(length=100), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("stop_loss", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("execution_signal_id", sa.Integer(), nullable=True),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_signal_id"], ["trading_signal.signal_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recommendation_symbol"), "recommendation", ["symbol"], unique=False)
    op.create_index(op.f("ix_recommendation_timestamp"), "recommendation", ["timestamp"], unique=False)
