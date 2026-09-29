"""add_client_account_table

Revision ID: h1a2b3c4d5e6
Revises: g2c3d4e5f6a7
Create Date: 2026-09-29 08:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h1a2b3c4d5e6"
down_revision: Union[str, None] = "g2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create client_account table
    op.create_table(
        "client_account",
        sa.Column("account_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_code", sa.String(length=50), nullable=False),
        sa.Column("client_name", sa.String(length=100), nullable=False),
        sa.Column("broker_type", sa.String(length=20), server_default="UPSTOX", nullable=False),
        sa.Column("api_key", sa.String(length=100), nullable=True),
        sa.Column("api_secret", sa.String(length=100), nullable=True),
        sa.Column("redirect_uri", sa.String(length=255), nullable=True),
        sa.Column("token_storage_key", sa.String(length=100), nullable=True),
        sa.Column("static_token", sa.Text(), nullable=True),
        sa.Column("allocated_capital", sa.Numeric(precision=14, scale=2), server_default="100000.0", nullable=False),
        sa.Column("max_risk_per_trade_pct", sa.Numeric(precision=5, scale=4), server_default="0.0100", nullable=False),
        sa.Column("max_active_trades", sa.Integer(), server_default="2", nullable=False),
        sa.Column("is_active", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("is_paper", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("account_id"),
        sa.UniqueConstraint("client_code"),
    )
    op.create_index(op.f("ix_client_account_client_code"), "client_account", ["client_code"], unique=True)
    op.create_index(op.f("ix_client_account_broker_type"), "client_account", ["broker_type"], unique=False)
    op.create_index(op.f("ix_client_account_is_active"), "client_account", ["is_active"], unique=False)

    # 2. Add account_id to trading_order, position, trade, execution_plan
    op.add_column("trading_order", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trading_order_account_id", "trading_order", "client_account", ["account_id"], ["account_id"])
    op.create_index(op.f("ix_trading_order_account_id"), "trading_order", ["account_id"], unique=False)

    op.add_column("position", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_position_account_id", "position", "client_account", ["account_id"], ["account_id"])
    op.create_index(op.f("ix_position_account_id"), "position", ["account_id"], unique=False)

    op.add_column("trade", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trade_account_id", "trade", "client_account", ["account_id"], ["account_id"])
    op.create_index(op.f("ix_trade_account_id"), "trade", ["account_id"], unique=False)

    op.add_column("execution_plan", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_execution_plan_account_id", "execution_plan", "client_account", ["account_id"], ["account_id"])
    op.create_index(op.f("ix_execution_plan_account_id"), "execution_plan", ["account_id"], unique=False)

    # 3. Seed default Upstox Primary Account
    op.execute(
        """
        INSERT INTO client_account (
            client_code, client_name, broker_type, token_storage_key,
            allocated_capital, max_risk_per_trade_pct, max_active_trades, is_active, is_paper
        ) VALUES (
            'UPSTOX_PRIMARY', 'Primary Upstox Account', 'UPSTOX', 'upstox:access_token',
            100000.0, 0.0100, 2, 1, false
        ) ON CONFLICT (client_code) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_execution_plan_account_id", "execution_plan", type_="foreignkey")
    op.drop_index(op.f("ix_execution_plan_account_id"), table_name="execution_plan")
    op.drop_column("execution_plan", "account_id")

    op.drop_constraint("fk_trade_account_id", "trade", type_="foreignkey")
    op.drop_index(op.f("ix_trade_account_id"), table_name="trade")
    op.drop_column("trade", "account_id")

    op.drop_constraint("fk_position_account_id", "position", type_="foreignkey")
    op.drop_index(op.f("ix_position_account_id"), table_name="position")
    op.drop_column("position", "account_id")

    op.drop_constraint("fk_trading_order_account_id", "trading_order", type_="foreignkey")
    op.drop_index(op.f("ix_trading_order_account_id"), table_name="trading_order")
    op.drop_column("trading_order", "account_id")

    op.drop_index(op.f("ix_client_account_is_active"), table_name="client_account")
    op.drop_index(op.f("ix_client_account_broker_type"), table_name="client_account")
    op.drop_index(op.f("ix_client_account_client_code"), table_name="client_account")
    op.drop_table("client_account")
