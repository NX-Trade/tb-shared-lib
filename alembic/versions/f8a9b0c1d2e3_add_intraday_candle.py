"""add intraday_candle

Intraday OHLCV bars, deliberately separate from historical_equity_data even
though that table's timeframe column would accept '15 minute'. Retention
differs (daily is permanent, intraday is prunable), and millions of intraday
rows would tax every daily query that filters timeframe = '1 day', including
the 600-bar training load.

Sized for 15-minute bars over the F&O universe: ~5M rows for 2022-01 onward.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intraday_candle",
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_key", sa.String(length=80), nullable=True),
        sa.Column("segment", sa.String(length=10), nullable=True),
        sa.Column("open", sa.Numeric(14, 4), nullable=True),
        sa.Column("high", sa.Numeric(14, 4), nullable=True),
        sa.Column("low", sa.Numeric(14, 4), nullable=True),
        sa.Column("close", sa.Numeric(14, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), server_default="0"),
        sa.Column("open_interest", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="UPSTOX"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("symbol", "timeframe", "timestamp"),
    )
    # The scanner reads one symbol's recent bars, which the primary key already
    # serves. This index covers the other direction: sweeping every symbol for
    # a single session, which is how a backtest replays a day.
    op.create_index(
        "ix_intraday_candle_tf_ts",
        "intraday_candle",
        ["timeframe", "timestamp"],
    )
    op.create_index(
        "ix_intraday_candle_instrument_key",
        "intraday_candle",
        ["instrument_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_intraday_candle_instrument_key", table_name="intraday_candle")
    op.drop_index("ix_intraday_candle_tf_ts", table_name="intraday_candle")
    op.drop_table("intraday_candle")
