"""Agent Verdict and News Embedding Models.

Stores per-agent approval decisions for signal candidates and vector
embeddings for RAG-powered news retrieval.

See ``docs/AGENTIC_AI_WORKFLOW_ARCHITECTURE.md`` for full architecture.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
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
    agent_name = Column(String(50), nullable=False)  # e.g. "signal_auditor"
    model_name = Column(String(100), nullable=False)  # e.g. "qwen3:8b"
    node = Column(String(50), nullable=False)  # e.g. "optiplex", "macbook"

    # ── Decision ───────────────────────────────────────────────────────────
    approved = Column(Boolean, nullable=False)
    confidence = Column(Numeric(5, 4))
    reasoning = Column(Text)

    # ── Context (for audit / replay) ──────────────────────────────────────
    input_context = Column(JSONB, default={})  # serialized input sent to agent
    output_json = Column(JSONB, default={})  # raw structured output from agent

    # ── Observability ─────────────────────────────────────────────────────
    latency_ms = Column(Integer)  # inference time in milliseconds

    # ── LLM gatekeeper audit (Gemini verdicts; NULL on the retired Ollama-era rows) ──
    # One row per call, reproducible: what was asked (``input_context`` is the evidence
    # pack; the hashes identify it and the prompt), what came back (``raw_response`` and
    # the parsed fields), what it cost, and how to find the stored HTTP exchange
    # (``correlation_id`` -> ``external_api_request.correlation_id``).
    # Rows with ``ai_provider = 'GEMINI'`` are kept indefinitely; the purge skips them.
    signal_id = Column(
        Integer,
        ForeignKey("trading_signal.signal_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ai_provider = Column(String(16))  # GEMINI
    as_of = Column(DateTime(timezone=True))  # the moment the evidence describes
    prompt_version = Column(String(24))
    prompt_sha256 = Column(String(64))
    evidence_sha256 = Column(String(64))
    parsed_verdict = Column(String(20))  # APPROVE | REJECT | WAIT_PULLBACK
    reason_codes = Column(JSONB)
    raw_response = Column(Text)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    cost_inr = Column(Numeric(10, 4))
    degraded = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    error_code = Column(String(40))
    correlation_id = Column(String(36), index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        index=True,
    )

    __table_args__ = (
        # One verdict per signal per prompt and evidence: a Celery retry cannot double-spend.
        Index(
            "uq_agent_verdict_signal_prompt",
            "signal_id",
            "agent_name",
            "prompt_sha256",
            "evidence_sha256",
            unique=True,
            postgresql_where=text("signal_id IS NOT NULL AND degraded = false"),
        ),
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
        ForeignKey("news.news_id", ondelete="SET NULL"),
        nullable=True,
    )

    source = Column(String(50), nullable=False)  # "bse_filing", "moneycontrol", etc.
    symbol = Column(String(20), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)

    # 768-dim embedding from nomic-embed-text. Column already exists in the DB
    # (added via raw SQL in the Alembic migration, alongside the HNSW index) —
    # this just gives the ORM a typed view of it.
    embedding = Column(Vector(768))

    published_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )
