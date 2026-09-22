"""add is_algo flag to trade

Lets the trade book hold trades that were placed manually at the broker and
discovered by reconciliation, without corrupting strategy statistics.

Until now a manual trade produced no ``trade`` row at all: the position
reconciler returned early for a flat broker position it had no book entry for,
so a manually round-tripped intraday position was recorded nowhere. That left
the circuit breaker blind to discretionary P&L — it sums ``net_pnl`` over CLOSED
trades, so a manual loss could not contribute to the daily/weekly drawdown
limits and the algo would keep sizing as if the day were flat.

The deliberate split this flag enables:

* **Risk / equity queries do not filter on it.** ``realized_pnl_since`` and
  ``total_realized_pnl`` must see manual trades, because it is the same capital
  at risk and a discretionary loss should be able to halt the algo.
* **Attribution queries filter to ``is_algo = true``.** Per-strategy expectancy,
  hit rates and the signal-attribution coverage monitor must exclude manual
  trades, which have no signal and no strategy.

Existing rows default to ``true``: everything written before this migration came
from the execution engine.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-22 19:05:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trade",
        sa.Column("is_algo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_trade_is_algo", "trade", ["is_algo"])


def downgrade() -> None:
    op.drop_index("ix_trade_is_algo", table_name="trade")
    op.drop_column("trade", "is_algo")
