"""add option_strategy_signal and option_strategy_leg tables

Revision ID: c1f2e3d4b5a6
Revises: b8f1a2c3d4e5
Create Date: 2026-09-16 18:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1f2e3d4b5a6"
down_revision: Union[str, None] = "b8f1a2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create option_strategy_signal
    op.create_table(
        "option_strategy_signal",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("strategy_type", sa.String(length=32), nullable=False),
        sa.Column("spread_type", sa.String(length=10), nullable=False),
        sa.Column("underlying_symbol", sa.String(length=20), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("dte", sa.Integer(), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("net_premium", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("max_profit", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("max_loss", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("risk_reward_ratio", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("breakeven_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("underlying_entry_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("underlying_target_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("underlying_stop_loss", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("margin_required_approx", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata", sa.JSON(), nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["trading_signal.signal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_option_strategy_signal_signal_id",
        "option_strategy_signal",
        ["signal_id"],
    )
    op.create_index(
        "ix_option_strategy_signal_underlying_symbol",
        "option_strategy_signal",
        ["underlying_symbol"],
    )
    op.create_index(
        "ix_option_strategy_signal_status",
        "option_strategy_signal",
        ["status"],
    )

    # 2. Create option_strategy_leg
    op.create_table(
        "option_strategy_leg",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_signal_id", sa.Integer(), nullable=False),
        sa.Column("execution_order", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=4), nullable=False),
        sa.Column("option_type", sa.String(length=2), nullable=False),
        sa.Column("strike_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("symbol", sa.String(length=60), nullable=False),
        sa.Column("entry_premium", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("target_premium", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("stop_loss_premium", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("delta", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("theta", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("iv", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("is_hedge", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["strategy_signal_id"],
            ["option_strategy_signal.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_option_strategy_leg_strategy_signal_id",
        "option_strategy_leg",
        ["strategy_signal_id"],
    )


def downgrade() -> None:
    op.drop_table("option_strategy_leg")
    op.drop_table("option_strategy_signal")
