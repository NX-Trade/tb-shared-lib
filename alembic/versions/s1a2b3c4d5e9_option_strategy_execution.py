"""saved option strategies and their executions

Lets a trader save a strategy from the option builder and run it on one or more broker accounts.
``option_strategy_signal`` gains a name, a source and the profit-target multiple. Each run on an
account is an ``option_strategy_execution`` with one ``option_execution_leg`` per contract, so fills,
P&L, the exit and any rollback are tracked per account. A partial unique index allows only one
*active* execution per (strategy, account), which stops a double click opening a position twice.

Revision ID: s1a2b3c4d5e9
Revises: r1f2a3b4c5d8
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "s1a2b3c4d5e9"
down_revision = "r1f2a3b4c5d8"
branch_labels = None
depends_on = None

ACTIVE = "('PENDING', 'ENTERING', 'OPEN', 'ROLLING_BACK', 'EXITING')"


def upgrade() -> None:
    op.add_column("option_strategy_signal", sa.Column("name", sa.String(length=80), nullable=True))
    op.add_column(
        "option_strategy_signal",
        sa.Column("source", sa.String(length=12), server_default="SYSTEM", nullable=False),
    )
    op.add_column(
        "option_strategy_signal",
        sa.Column(
            "profit_target_multiple", sa.Numeric(5, 2), server_default="2.00", nullable=False
        ),
    )

    op.create_table(
        "option_strategy_execution",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=14), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("profit_target_multiple", sa.Numeric(5, 2), nullable=False),
        sa.Column("max_loss", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("entry_net", sa.Numeric(14, 2), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(14, 2), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(14, 2), nullable=True),
        sa.Column("exit_reason", sa.String(length=24), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["option_strategy_signal.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["client_account.account_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_option_strategy_execution_strategy_id", "option_strategy_execution", ["strategy_id"]
    )
    op.create_index(
        "ix_option_strategy_execution_account_id", "option_strategy_execution", ["account_id"]
    )
    op.create_index("ix_option_strategy_execution_status", "option_strategy_execution", ["status"])
    op.create_index(
        "uq_option_execution_active",
        "option_strategy_execution",
        ["strategy_id", "account_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN {ACTIVE}"),
    )

    op.create_table(
        "option_execution_leg",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("leg_order", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=4), nullable=False),
        sa.Column("option_type", sa.String(length=2), nullable=False),
        sa.Column("strike_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("lots", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("broker_symbol", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("entry_order_id", sa.Integer(), nullable=True),
        sa.Column("entry_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("entry_filled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exit_order_id", sa.Integer(), nullable=True),
        sa.Column("exit_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("exit_filled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_price", sa.Numeric(14, 4), nullable=True),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["option_strategy_execution.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["entry_order_id"], ["trading_order.order_id"]),
        sa.ForeignKeyConstraint(["exit_order_id"], ["trading_order.order_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_option_execution_leg_execution_id", "option_execution_leg", ["execution_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_option_execution_leg_execution_id", table_name="option_execution_leg")
    op.drop_table("option_execution_leg")
    op.drop_index("uq_option_execution_active", table_name="option_strategy_execution")
    op.drop_index("ix_option_strategy_execution_status", table_name="option_strategy_execution")
    op.drop_index("ix_option_strategy_execution_account_id", table_name="option_strategy_execution")
    op.drop_index(
        "ix_option_strategy_execution_strategy_id", table_name="option_strategy_execution"
    )
    op.drop_table("option_strategy_execution")
    op.drop_column("option_strategy_signal", "profit_target_multiple")
    op.drop_column("option_strategy_signal", "source")
    op.drop_column("option_strategy_signal", "name")
