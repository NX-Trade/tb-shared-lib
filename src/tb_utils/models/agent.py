"""Agent Verdict and News Embedding Models.

Stores per-agent approval decisions for signal candidates and vector
embeddings for RAG-powered news retrieval.

See ``docs/AGENTIC_AI_WORKFLOW_ARCHITECTURE.md`` for full architecture.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func, text

from .base import Base


class AgentVerdict(Base):
    """Per-agent approval/rejection decision on a signal candidate.

    Every agent invocation (Signal Auditor, News Analyst, Risk Guard, etc.)
    persists its verdict here.  The Master Orchestrator reads all verdicts
    for a given (symbol, trade_date) tuple to make the final decision.

    30-day retention enforced by a Celery purge task.
    """

    __tablename__ = "agent_verdict"

    verdict_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    symbol = Column(String(20), nullable=False, index=True)
    trade_date = Column(DateTime(timezone=True), nullable=False, index=True)

    # ── Agent identification ───────────────────────────────────────────────
    agent_name = Column(String(50), nullable=False)   # e.g. "signal_auditor"
    model_name = Column(String(100), nullable=False)  # e.g. "qwen3:8b"
    node = Column(String(50), nullable=False)         # e.g. "optiplex", "macbook"

    # ── Decision ───────────────────────────────────────────────────────────
    approved = Column(Boolean, nullable=False)
    confidence = Column(Numeric(5, 4))
    reasoning = Column(Text)

    # ── Context (for audit / replay) ──────────────────────────────────────
    input_context = Column(JSONB, default={})   # serialized input sent to agent
    output_json = Column(JSONB, default={})     # raw structured output from agent

    # ── Observability ─────────────────────────────────────────────────────
    latency_ms = Column(Integer)  # inference time in milliseconds

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        index=True,
    )


class NewsEmbedding(Base):
    """pgvector embedding store for RAG-powered news retrieval.

    Chunks from ``CorporateAnnouncement`` and ``News`` records are embedded
    via ``nomic-embed-text`` (768-dimensional) and stored here for cosine
    similarity search by the News Analyst agent.

    Requires the ``pgvector`` PostgreSQL extension::

        CREATE EXTENSION IF NOT EXISTS vector;

    An HNSW index is created on the ``embedding`` column for fast
    approximate nearest-neighbour lookups.
    """

    __tablename__ = "news_embedding"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Source linkage (nullable — not all chunks map to a single record) ─
    announcement_id = Column(
        Integer,
        ForeignKey("corporate_announcement.id", ondelete="SET NULL"),
        nullable=True,
    )
    news_id = Column(
        Integer,
        ForeignKey("news.id", ondelete="SET NULL"),
        nullable=True,
    )

    source = Column(String(50), nullable=False)   # "bse_filing", "moneycontrol", etc.
    symbol = Column(String(20), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)

    # ── Vector column ─────────────────────────────────────────────────────
    # The pgvector ``Vector`` type is registered via the Alembic migration.
    # We store the column spec here as a raw string type so that the model
    # file does not force a hard dependency on pgvector at import time.
    # The actual column type is ``vector(768)`` in PostgreSQL.
    # embedding = Column(Vector(768))  # — set via migration, not ORM

    published_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )
