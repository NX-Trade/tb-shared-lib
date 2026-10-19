"""convert option_chain to a TimescaleDB hypertable

Why now
-------
``option_chain`` was deliberately left a plain table on the grounds that ADR-005
pruned intraday rows to 5 days, so it never accumulated enough volume to justify
partitioning. **ADR-005 was amended on 2026-10-19 to forbid pruning entirely**
— the live chain endpoint has no history, so a deleted snapshot is unrecoverable
and IV-rank work needs the long series. That removes the original rationale:

  ~3,236 chains/day (220 F&O symbols x 2 expiries hourly, plus 3 indices x 2
  expiries every 15 min) x 82 rows per chain (41 strikes x CE/PE)
  ~= 265k rows/day ~= 66M rows/year, growing forever.

A never-pruned table on that trajectory is exactly the case partitioning exists
for. The strike window (``OPTION_CHAIN_STRIKES_LIMIT``, 20 each side) stays at
20 — it is the only remaining bound on row growth, so widening it is now a
partitioning decision, not just a storage one.

Primary key
-----------
No PK change is needed. TimescaleDB requires the partitioning column to appear
in every unique index, and the existing PK is already
``(ts, symbol, expiry_date, strike_price, option_type)`` — ``ts`` leads it.
``option_chain`` has no other unique index. (Contrast ``historical_equity_data``,
which the intraday_candle migration declined to convert precisely because its
surrogate PK is unique on the id alone.)

Chunk sizing
------------
7 days, not the 1 month that ``intraday_candle`` uses. That table sees ~5,500
rows/day, where monthly chunks land at ~165k rows; this one sees ~265k rows/day,
so monthly would build ~5.6M-row chunks while weekly gives ~1.85M — a better fit
for keeping recent chunks and their indexes in memory.

Compression: configured, not scheduled
--------------------------------------
``compress_segmentby`` is ``symbol,option_type`` because ``symbol`` is the
dominant filter in every reader (``queries/greeks.py``'s IV_RANK and
GAMMA_EXPOSURE, and the contract resolver's OPTION_CONTRACTS_QUERY), and that
cardinality (~440 segments/chunk, ~4k rows each) compresses better than also
segmenting by ``expiry_date``.

**No ``add_compression_policy`` call is made here, deliberately.** Upserts into
compressed chunks are restricted, and every writer in this schema goes through
``PostgresUpsertMixin.upsert_native`` (ON CONFLICT). The EOD NSE backfill tasks
(``sync_index_option_chain_history``, the bhavcopy ETL) write *historical* rows,
so an age-based compression policy would silently start failing backfills into
any chunk it had already compressed. Enable compression manually, per-chunk or
by policy, once the backfill campaign in ``docs/ops/DATA_BACKFILL_RUNBOOK.md``
is complete:

    SELECT add_compression_policy('option_chain', INTERVAL '180 days');

No retention policy is added, and none may be: ADR-005 forbids deleting
anything from this table.

Operational note
----------------
``migrate_data => TRUE`` rewrites existing rows into chunks and holds a lock for
the duration. Run this in a maintenance window, outside market hours, via
``make deploy`` on optiplex — never by hand against the live DB.

Revision ID: m1a2b3c4d5e6
Revises: l1f2a3b4c5d6
Create Date: 2026-10-19
"""

from alembic import op

revision = "m1a2b3c4d5e6"
down_revision = "l1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        SELECT create_hypertable(
            'option_chain',
            'ts',
            chunk_time_interval => INTERVAL '7 days',
            migrate_data => TRUE,
            if_not_exists => TRUE
        )
        """
    )
    # Configure compression without scheduling it — see the module docstring for
    # why an automatic policy would break historical backfills.
    op.execute(
        """
        ALTER TABLE option_chain SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'symbol,option_type',
            timescaledb.compress_orderby = 'ts DESC, strike_price'
        )
        """
    )


def downgrade() -> None:
    """Reverse compression settings. The hypertable itself needs a rebuild.

    TimescaleDB has no ``drop_hypertable`` that leaves a plain table behind, so
    the partitioning cannot be undone by DDL. Everything reversible is reversed
    here; the rest is left to a deliberate, supervised rebuild rather than an
    untested copy buried in a downgrade path:

        CREATE TABLE option_chain_plain (LIKE option_chain);
        INSERT INTO option_chain_plain SELECT * FROM option_chain;
        DROP TABLE option_chain;
        ALTER TABLE option_chain_plain RENAME TO option_chain;
        -- then recreate the primary key:
        --   (ts, symbol, expiry_date, strike_price, option_type)

    Raising is the honest outcome: a silent no-op would leave the schema
    partitioned while Alembic reported the revision as reverted.
    """
    op.execute("SELECT remove_compression_policy('option_chain', if_exists => TRUE)")
    op.execute(
        """
        DO $$
        DECLARE chunk regclass;
        BEGIN
            FOR chunk IN SELECT show_chunks('option_chain') LOOP
                PERFORM decompress_chunk(chunk, if_compressed => TRUE);
            END LOOP;
        END $$
        """
    )
    op.execute("ALTER TABLE option_chain SET (timescaledb.compress = FALSE)")
    raise NotImplementedError(
        "Compression has been removed, but option_chain is still a hypertable: "
        "TimescaleDB cannot convert one back to a plain table. See this "
        "migration's downgrade docstring for the rebuild steps."
    )
