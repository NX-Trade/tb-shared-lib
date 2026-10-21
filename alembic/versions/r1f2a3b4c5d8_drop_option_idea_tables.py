"""drop option_basket_idea and option_idea_skip

Created by ``p1e2f3a4b5c6`` for a nightly job that stored generated option ideas. Strategies are
now suggested on demand from the latest chain at request time, so nothing writes or reads these
tables. They never held a row in production. Idempotent, and the downgrade recreates them as
``p1e2f3a4b5c6`` made them.

Revision ID: r1f2a3b4c5d8
Revises: q1f2a3b4c5d7
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "r1f2a3b4c5d8"
down_revision = "q1f2a3b4c5d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS option_idea_skip")
    op.execute("DROP TABLE IF EXISTS option_basket_idea")


def downgrade() -> None:
    op.create_table(
        "option_basket_idea",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("generated_for", sa.Date(), nullable=False),
        sa.Column("underlying", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=6), nullable=False),
        sa.Column("bias", sa.String(length=8), nullable=False),
        sa.Column("conviction", sa.Numeric(4, 3), nullable=False),
        sa.Column("template", sa.String(length=40), nullable=False),
        sa.Column("template_label", sa.String(length=60), nullable=False),
        sa.Column("shape", sa.String(length=20), nullable=False),
        sa.Column("family", sa.String(length=8), nullable=False),
        sa.Column("slot_role", sa.String(length=14), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("dte", sa.Integer(), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("legs", sa.JSON(), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=False),
        sa.Column("score", sa.Numeric(10, 4), nullable=False),
        sa.Column("ev_view", sa.Numeric(14, 2), nullable=False),
        sa.Column("pop_view", sa.Numeric(5, 4), nullable=False),
        sa.Column("max_profit", sa.Numeric(14, 2), nullable=False),
        sa.Column("max_loss", sa.Numeric(14, 2), nullable=False),
        sa.Column("return_on_risk", sa.Numeric(8, 4), nullable=False),
        sa.Column("view_source", sa.String(length=40), nullable=False),
        sa.Column("view_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("view_entry", sa.Numeric(14, 4), nullable=True),
        sa.Column("view_target", sa.Numeric(14, 4), nullable=True),
        sa.Column("view_stop", sa.Numeric(14, 4), nullable=True),
        sa.Column("sigma_source", sa.String(length=20), nullable=False),
        sa.Column("chain_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analytics_version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="ACTIVE", nullable=False),
        sa.Column("outcome", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generated_for", "underlying", "template", "expiry_date", name="uq_option_basket_idea"
        ),
    )
    op.create_index("ix_option_basket_idea_underlying", "option_basket_idea", ["underlying"])
    op.create_index(
        "ix_option_basket_idea_day_kind", "option_basket_idea", ["generated_for", "kind"]
    )
    op.create_table(
        "option_idea_skip",
        sa.Column("generated_for", sa.Date(), nullable=False),
        sa.Column("underlying", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=6), nullable=False),
        sa.Column("bias", sa.String(length=8), nullable=True),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("view_source", sa.String(length=40), nullable=True),
        sa.Column("view_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("generated_for", "underlying"),
    )
