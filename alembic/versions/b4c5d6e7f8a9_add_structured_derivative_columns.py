"""add structured derivative columns to position, order, trade, and execution plan

Extends the trading tables with structured derivative contract columns
(instrument_type, strike_price, expiry_date, trading_symbol) so that F&O
positions — options and futures — are tracked alongside equities in the
same tables.

Key changes:
- ``position``: adds ``trading_symbol``, ``instrument_type``, ``strike_price``,
  ``expiry_date``, ``is_algo``, ``last_price``, ``created_at``.
  Unique constraint changes from ``(instrument_id, broker_id)`` to
  ``(trading_symbol, broker_id)``.
- ``trading_order``: widens ``symbol`` to 60 chars, adds derivative columns.
- ``trade``: adds ``trading_symbol`` and derivative columns.
- ``execution_plan``: widens ``symbol`` to 60 chars, adds derivative columns.

Backfills existing equity rows with ``trading_symbol`` from the instrument
master and ``instrument_type='EQUITY'``.

Revision ID: b4c5d6e7f8a9
Revises: a9b0c1d2e3f4
Create Date: 2026-09-22 13:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b4c5d6e7f8a9"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Position table ──────────────────────────────────────────────────

    # Add new columns (trading_symbol starts nullable for backfill)
    op.add_column("position", sa.Column("trading_symbol", sa.String(60), nullable=True))
    op.add_column(
        "position",
        sa.Column(
            "instrument_type", sa.String(10), nullable=False, server_default="EQUITY"
        ),
    )
    op.add_column(
        "position", sa.Column("strike_price", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column("position", sa.Column("expiry_date", sa.Date(), nullable=True))
    op.add_column(
        "position",
        sa.Column("is_algo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "position", sa.Column("last_price", sa.Numeric(14, 4), nullable=True)
    )
    op.add_column(
        "position",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Backfill trading_symbol from instrument master for existing equity rows
    op.execute(
        """
        UPDATE position p
        SET trading_symbol = i.symbol
        FROM instrument i
        WHERE p.instrument_id = i.instrument_id
          AND p.trading_symbol IS NULL
        """
    )

    # Any rows without a matching instrument get their instrument_id as fallback
    op.execute(
        """
        UPDATE position
        SET trading_symbol = CAST(instrument_id AS VARCHAR)
        WHERE trading_symbol IS NULL
        """
    )

    # Now make trading_symbol NOT NULL
    op.alter_column("position", "trading_symbol", nullable=False)

    # Create index on trading_symbol
    op.create_index("ix_position_trading_symbol", "position", ["trading_symbol"])

    # Swap unique constraint
    op.drop_constraint("uix_position_key", "position", type_="unique")
    op.create_unique_constraint(
        "uix_position_symbol_broker", "position", ["trading_symbol", "broker_id"]
    )

    # ── 2. Trading order table ─────────────────────────────────────────────

    # Widen symbol column
    op.alter_column(
        "trading_order",
        "symbol",
        existing_type=sa.String(20),
        type_=sa.String(60),
    )

    # Add derivative columns
    op.add_column(
        "trading_order",
        sa.Column("instrument_type", sa.String(10), nullable=True),
    )
    op.add_column(
        "trading_order",
        sa.Column("strike_price", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "trading_order", sa.Column("expiry_date", sa.Date(), nullable=True)
    )

    # ── 3. Trade table ─────────────────────────────────────────────────────

    op.add_column(
        "trade", sa.Column("trading_symbol", sa.String(60), nullable=True)
    )
    op.add_column(
        "trade", sa.Column("instrument_type", sa.String(10), nullable=True)
    )
    op.add_column(
        "trade", sa.Column("strike_price", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column("trade", sa.Column("expiry_date", sa.Date(), nullable=True))

    # Backfill trading_symbol for existing trades
    op.execute(
        """
        UPDATE trade t
        SET trading_symbol = i.symbol,
            instrument_type = 'EQUITY'
        FROM instrument i
        WHERE t.instrument_id = i.instrument_id
          AND t.trading_symbol IS NULL
        """
    )

    op.create_index("ix_trade_trading_symbol", "trade", ["trading_symbol"])

    # ── 4. Execution plan table ────────────────────────────────────────────

    # Widen symbol column
    op.alter_column(
        "execution_plan",
        "symbol",
        existing_type=sa.String(20),
        type_=sa.String(60),
    )

    op.add_column(
        "execution_plan",
        sa.Column("instrument_type", sa.String(10), nullable=True),
    )
    op.add_column(
        "execution_plan",
        sa.Column("strike_price", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "execution_plan", sa.Column("expiry_date", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    # ── 4. Execution plan (reverse) ────────────────────────────────────────
    op.drop_column("execution_plan", "expiry_date")
    op.drop_column("execution_plan", "strike_price")
    op.drop_column("execution_plan", "instrument_type")
    op.alter_column(
        "execution_plan",
        "symbol",
        existing_type=sa.String(60),
        type_=sa.String(20),
    )

    # ── 3. Trade (reverse) ─────────────────────────────────────────────────
    op.drop_index("ix_trade_trading_symbol", table_name="trade")
    op.drop_column("trade", "expiry_date")
    op.drop_column("trade", "strike_price")
    op.drop_column("trade", "instrument_type")
    op.drop_column("trade", "trading_symbol")

    # ── 2. Trading order (reverse) ─────────────────────────────────────────
    op.drop_column("trading_order", "expiry_date")
    op.drop_column("trading_order", "strike_price")
    op.drop_column("trading_order", "instrument_type")
    op.alter_column(
        "trading_order",
        "symbol",
        existing_type=sa.String(60),
        type_=sa.String(20),
    )

    # ── 1. Position (reverse) ──────────────────────────────────────────────
    op.drop_constraint("uix_position_symbol_broker", "position", type_="unique")
    op.create_unique_constraint(
        "uix_position_key", "position", ["instrument_id", "broker_id"]
    )
    op.drop_index("ix_position_trading_symbol", table_name="position")
    op.drop_column("position", "created_at")
    op.drop_column("position", "last_price")
    op.drop_column("position", "is_algo")
    op.drop_column("position", "expiry_date")
    op.drop_column("position", "strike_price")
    op.drop_column("position", "instrument_type")
    op.drop_column("position", "trading_symbol")
