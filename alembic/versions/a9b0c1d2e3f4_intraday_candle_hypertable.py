"""convert intraday_candle to a TimescaleDB hypertable

Why this table and not the others
---------------------------------
``intraday_candle`` is the fastest-growing table in the schema — 5,500 rows a
day at 15m across ~220 F&O symbols, and a multiple of that if 1-minute bars or
more symbols are added. It is also the only one with a genuine retention need,
where ``drop_chunk`` is a file unlink against a ``DELETE`` that would rewrite
millions of rows and bloat the heap.

Not ``historical_equity_data``: its surrogate ``historical_equity_data_id``
primary key is unique on the id alone, and TimescaleDB requires every unique
index to include the partitioning column. Converting it would mean dropping
that key first — a change to a table every service reads, for a problem nobody
has measured.

Not ``option_daily_metrics``: ~286k rows at full coverage with permanent
retention. Partitioning would add operational surface for no benefit.

Chunk sizing
------------
One month rather than the 7-day default. At ~5,500 rows/day, weekly chunks
would hold ~38k rows and accumulate ~170 of them over the backfilled range;
monthly gives ~165k-row chunks and ~56 of them, a better ratio at this volume.

Compression segments by ``(symbol, timeframe)`` because those are the columns
every read filters on, leaving ``timestamp`` as the ordering key. It applies
only to chunks older than 90 days so recent data stays writable.

No retention policy is added here deliberately. Automatic deletion on a
schedule should be an explicit decision with a stated horizon, not something
buried in a migration.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-09-20
"""

from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # migrate_data moves rows already present into chunks. Cheap now at a few
    # million rows; slow and lock-holding if deferred until the table is large.
    op.execute(
        """
        SELECT create_hypertable(
            'intraday_candle',
            'timestamp',
            chunk_time_interval => INTERVAL '1 month',
            migrate_data => TRUE,
            if_not_exists => TRUE
        )
        """
    )
    op.execute(
        """
        ALTER TABLE intraday_candle SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'symbol,timeframe',
            timescaledb.compress_orderby = 'timestamp DESC'
        )
        """
    )
    op.execute("SELECT add_compression_policy('intraday_candle', INTERVAL '90 days')")


def downgrade() -> None:
    """Reverse compression. Reverting the hypertable itself needs a rebuild.

    TimescaleDB has no ``drop_hypertable`` that leaves a plain table behind, so
    the partitioning cannot be undone by DDL. Everything reversible is reversed
    here; the rest is left to a deliberate, supervised rebuild rather than an
    untested 40-line copy buried in a downgrade path:

        CREATE TABLE intraday_candle_plain (LIKE intraday_candle);
        INSERT INTO intraday_candle_plain SELECT * FROM intraday_candle;
        DROP TABLE intraday_candle;
        ALTER TABLE intraday_candle_plain RENAME TO intraday_candle;
        -- then recreate the primary key and indexes from
        -- f8a9b0c1d2e3_add_intraday_candle.py

    Raising is the honest outcome: a silent no-op would leave the schema
    partitioned while Alembic reported the revision as reverted.
    """
    op.execute("SELECT remove_compression_policy('intraday_candle', if_exists => TRUE)")
    op.execute(
        """
        DO $$
        DECLARE chunk regclass;
        BEGIN
            FOR chunk IN SELECT show_chunks('intraday_candle') LOOP
                PERFORM decompress_chunk(chunk, if_compressed => TRUE);
            END LOOP;
        END $$
        """
    )
    op.execute("ALTER TABLE intraday_candle SET (timescaledb.compress = FALSE)")
    raise NotImplementedError(
        "Compression has been removed, but intraday_candle is still a "
        "hypertable: TimescaleDB cannot convert one back to a plain table. "
        "See this migration's downgrade docstring for the rebuild steps."
    )
