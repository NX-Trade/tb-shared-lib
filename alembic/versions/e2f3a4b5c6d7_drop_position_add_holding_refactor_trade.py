"""drop_position_add_holding_refactor_trade

Revision ID: e2f3a4b5c6d7
Revises: d110b3f8bebb
Create Date: 2026-10-02 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d110b3f8bebb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop position table
    op.execute("DROP TABLE IF EXISTS position CASCADE")

    # 2. Create holding table for settled Demat equity inventory
    op.create_table(
        "holding",
        sa.Column("holding_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("broker_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("trading_symbol", sa.String(length=60), nullable=False),
        sa.Column("underlying_symbol", sa.String(length=20), nullable=True),
        sa.Column("isin", sa.String(length=20), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authorized_quantity", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("average_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("last_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("close_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("pnl", sa.Numeric(precision=12, scale=2), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["client_account.account_id"]),
        sa.ForeignKeyConstraint(["broker_id"], ["broker.broker_id"]),
        sa.PrimaryKeyConstraint("holding_id"),
        sa.UniqueConstraint("trading_symbol", "broker_id", "account_id", name="uix_holding_symbol_broker_account"),
    )
    op.create_index("ix_holding_broker_id", "holding", ["broker_id"])
    op.create_index("ix_holding_account_id", "holding", ["account_id"])
    op.create_index("ix_holding_trading_symbol", "holding", ["trading_symbol"])
    op.create_index("ix_holding_underlying_symbol", "holding", ["underlying_symbol"])
    op.create_index("ix_holding_isin", "holding", ["isin"])

    # 3. Refactor trade table: drop foreign key constraint on instrument_id and promote trading_symbol
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'trade_instrument_id_fkey' AND table_name = 'trade'
            ) THEN
                ALTER TABLE trade DROP CONSTRAINT trade_instrument_id_fkey;
            END IF;
        END $$;
    """)
    op.alter_column("trade", "instrument_id", existing_type=sa.Integer(), nullable=True)

    # Add new operational columns to trade if they do not exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trade' AND column_name = 'underlying_symbol'
            ) THEN
                ALTER TABLE trade ADD COLUMN underlying_symbol VARCHAR(20);
                CREATE INDEX ix_trade_underlying_symbol ON trade (underlying_symbol);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trade' AND column_name = 'product'
            ) THEN
                ALTER TABLE trade ADD COLUMN product VARCHAR(5) NOT NULL DEFAULT 'I';
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trade' AND column_name = 'last_price'
            ) THEN
                ALTER TABLE trade ADD COLUMN last_price NUMERIC(14, 4);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column("trade", "last_price")
    op.drop_column("trade", "product")
    op.drop_index("ix_trade_underlying_symbol", table_name="trade")
    op.drop_column("trade", "underlying_symbol")
    op.drop_table("holding")
