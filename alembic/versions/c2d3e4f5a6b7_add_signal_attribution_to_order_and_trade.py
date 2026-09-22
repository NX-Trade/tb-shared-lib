"""add signal_id attribution columns to trading_order and trade

Makes signal → realised-P&L attribution a one-hop join.

Before this migration ``signal_id`` existed on exactly one table,
``execution_plan``, so answering "what did this signal actually earn, net of
slippage and fees?" required a four-hop join::

    trading_signal → execution_plan → trading_order → trade

That path is fragile in three ways:

1. ``execution_plan.signal_id`` is nullable, so a plan created without a signal
   silently orphans the outcome.
2. Orders created outside a plan — bracket stop/target legs, auditor-replaced
   stops, ``monitor_positions`` exits, spread legs, broker-side fills found by
   the reconciler — never appear on the chain at all.
3. A ``trade`` row produced by a manual or broker-side exit has no plan to walk
   back to, so its cause is unknowable.

An unattributable fill is a labelled training row that cost real money and
cannot be used, so the id is denormalised onto both tables.

Key changes:
- ``trading_order``: adds nullable indexed ``signal_id`` FK → ``trading_signal``.
- ``trade``: adds nullable indexed ``signal_id`` FK → ``trading_signal``.
- Backfills both from the existing ``execution_plan`` path, including child
  orders linked by ``parent_order_id`` (stop/target legs of a backfilled entry).

``NULL`` after this migration means "genuinely not signal-driven" (a manual
trade), which is a meaningful state — it is not the same as "we lost the link".
Coverage is monitored by
``collector.tasks.nse.monitoring.check_signal_attribution_coverage``.

Revision ID: c2d3e4f5a6b7
Revises: b0c1d2e3f4a5
Create Date: 2026-09-21 23:10:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Columns ─────────────────────────────────────────────────────────
    op.add_column("trading_order", sa.Column("signal_id", sa.Integer(), nullable=True))
    op.add_column("trade", sa.Column("signal_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_trading_order_signal_id",
        "trading_order",
        "trading_signal",
        ["signal_id"],
        ["signal_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_trade_signal_id",
        "trade",
        "trading_signal",
        ["signal_id"],
        ["signal_id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_trading_order_signal_id", "trading_order", ["signal_id"])
    op.create_index("ix_trade_signal_id", "trade", ["signal_id"])

    # ── 2. Backfill entry orders from execution_plan ───────────────────────
    op.execute(
        """
        UPDATE trading_order o
           SET signal_id = ep.signal_id
          FROM execution_plan ep
         WHERE ep.entry_order_id = o.order_id
           AND ep.signal_id IS NOT NULL
           AND o.signal_id IS NULL
        """
    )

    # ── 3. Backfill child orders (stop / target legs) from their parent ────
    # Bracket legs carry parent_order_id pointing at the entry order, so they
    # inherit attribution once step 2 has populated the entry.
    op.execute(
        """
        UPDATE trading_order child
           SET signal_id = parent.signal_id
          FROM trading_order parent
         WHERE child.parent_order_id = parent.order_id
           AND parent.signal_id IS NOT NULL
           AND child.signal_id IS NULL
        """
    )

    # ── 4. Backfill trades from their entry order ──────────────────────────
    op.execute(
        """
        UPDATE trade t
           SET signal_id = o.signal_id
          FROM trading_order o
         WHERE t.entry_order_id = o.order_id
           AND o.signal_id IS NOT NULL
           AND t.signal_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_trade_signal_id", table_name="trade")
    op.drop_index("ix_trading_order_signal_id", table_name="trading_order")
    op.drop_constraint("fk_trade_signal_id", "trade", type_="foreignkey")
    op.drop_constraint("fk_trading_order_signal_id", "trading_order", type_="foreignkey")
    op.drop_column("trade", "signal_id")
    op.drop_column("trading_order", "signal_id")
