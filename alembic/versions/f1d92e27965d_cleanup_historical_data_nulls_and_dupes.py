"""Clean up historical data - remove NULL/NaN values and duplicates.

Revision ID: f1d92e27965d
Revises: b4d92e27965c
Create Date: 2026-06-08 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "f1d92e27965d"
down_revision = "b4d92e27965c"
branch_labels = None
depends_on = None


def upgrade():
    """Clean up bad data and enforce constraints."""
    # 1. Clean up historical_equity_data - remove records with NULL/NaN OHLCV
    op.execute(
        text(
            """
            DELETE FROM historical_equity_data
            WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL
            OR open != open OR high != high OR low != low OR close != close OR volume != volume
            """
        )
    )

    # 2. Clean up historical_index_data - remove records with NULL/NaN OHLCV
    op.execute(
        text(
            """
            DELETE FROM historical_index_data
            WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
            OR open != open OR high != high OR low != low OR close != close
            """
        )
    )

    # 3. Deduplicate historical_equity_data - keep the most recent record for each (symbol, timeframe, timestamp)
    op.execute(
        text(
            """
            DELETE FROM historical_equity_data a
            USING historical_equity_data b
            WHERE a.historical_equity_data_id < b.historical_equity_data_id
            AND a.symbol = b.symbol
            AND a.timeframe = b.timeframe
            AND a.timestamp = b.timestamp
            """
        )
    )

    # 4. Deduplicate historical_index_data
    op.execute(
        text(
            """
            DELETE FROM historical_index_data a
            USING historical_index_data b
            WHERE a.historical_index_data_id < b.historical_index_data_id
            AND a.symbol = b.symbol
            AND a.timeframe = b.timeframe
            AND a.timestamp = b.timestamp
            AND a.index_name = b.index_name
            """
        )
    )

    # 5. Clean up candle table - remove NULL/NaN values
    op.execute(
        text(
            """
            DELETE FROM candle
            WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL
            OR open != open OR high != high OR low != low OR close != close OR volume != volume
            """
        )
    )


def downgrade():
    """Cannot restore deleted bad data."""
    pass
