"""agent_verdict: audit columns for Gemini gatekeeper verdicts

One row per LLM call, reproducible: the signal it judged, the evidence and prompt (hashed), the parsed
verdict and reason codes, the raw reply, tokens and estimated cost, whether it was degraded, and the
correlation id that finds the stored HTTP exchange in ``external_api_request``. A partial unique index
stops a retried task from judging the same signal twice with the same prompt and evidence. All columns
are nullable (or defaulted) so the retired Ollama-era rows stay valid.

Revision ID: t1a2b3c4d5f0
Revises: s1a2b3c4d5e9
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "t1a2b3c4d5f0"
down_revision = "s1a2b3c4d5e9"
branch_labels = None
depends_on = None

TABLE = "agent_verdict"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("signal_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_agent_verdict_signal", TABLE, "trading_signal", ["signal_id"], ["signal_id"], ondelete="SET NULL"
    )
    op.create_index("ix_agent_verdict_signal_id", TABLE, ["signal_id"])
    op.add_column(TABLE, sa.Column("ai_provider", sa.String(length=16), nullable=True))
    op.add_column(TABLE, sa.Column("as_of", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("prompt_version", sa.String(length=24), nullable=True))
    op.add_column(TABLE, sa.Column("prompt_sha256", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("evidence_sha256", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("parsed_verdict", sa.String(length=20), nullable=True))
    op.add_column(TABLE, sa.Column("reason_codes", postgresql.JSONB(), nullable=True))
    op.add_column(TABLE, sa.Column("raw_response", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("cost_inr", sa.Numeric(10, 4), nullable=True))
    op.add_column(
        TABLE, sa.Column("degraded", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column(TABLE, sa.Column("error_code", sa.String(length=40), nullable=True))
    op.add_column(TABLE, sa.Column("correlation_id", sa.String(length=36), nullable=True))
    op.create_index("ix_agent_verdict_correlation_id", TABLE, ["correlation_id"])
    op.create_index(
        "uq_agent_verdict_signal_prompt",
        TABLE,
        ["signal_id", "agent_name", "prompt_sha256", "evidence_sha256"],
        unique=True,
        postgresql_where=sa.text("signal_id IS NOT NULL AND degraded = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_agent_verdict_signal_prompt", table_name=TABLE)
    op.drop_index("ix_agent_verdict_correlation_id", table_name=TABLE)
    for column in (
        "correlation_id",
        "error_code",
        "degraded",
        "cost_inr",
        "completion_tokens",
        "prompt_tokens",
        "raw_response",
        "reason_codes",
        "parsed_verdict",
        "evidence_sha256",
        "prompt_sha256",
        "prompt_version",
        "as_of",
        "ai_provider",
    ):
        op.drop_column(TABLE, column)
    op.drop_index("ix_agent_verdict_signal_id", table_name=TABLE)
    op.drop_constraint("fk_agent_verdict_signal", TABLE, type_="foreignkey")
    op.drop_column(TABLE, "signal_id")
