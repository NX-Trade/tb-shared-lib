"""add agent_verdict and news_embedding tables

Revision ID: d4a1b7e39c02
Revises: c73d9021f100
Create Date: 2026-08-05 10:49:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4a1b7e39c02'
down_revision: Union[str, None] = 'c73d9021f100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enable pgvector extension (requires pgvector package installed in PostgreSQL) ──
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── AgentVerdict table ──────────────────────────────────────────────────
    op.create_table(
        'agent_verdict',
        sa.Column(
            'verdict_id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('trade_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('agent_name', sa.String(length=50), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('node', sa.String(length=50), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('input_context', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('output_json', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('verdict_id'),
    )
    op.create_index(
        op.f('ix_agent_verdict_symbol'), 'agent_verdict', ['symbol'], unique=False
    )
    op.create_index(
        op.f('ix_agent_verdict_trade_date'), 'agent_verdict', ['trade_date'], unique=False
    )
    op.create_index(
        op.f('ix_agent_verdict_created_at'), 'agent_verdict', ['created_at'], unique=False
    )

    # ── NewsEmbedding table ────────────────────────────────────────────────
    op.create_table(
        'news_embedding',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            'announcement_id',
            sa.Integer(),
            sa.ForeignKey('corporate_announcement.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'news_id',
            sa.Integer(),
            sa.ForeignKey('news.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_news_embedding_symbol'), 'news_embedding', ['symbol'], unique=False
    )

    # ── Add pgvector embedding column + HNSW index ────────────────────────
    # Using raw SQL because Alembic's Column type doesn't natively support pgvector.
    op.execute("ALTER TABLE news_embedding ADD COLUMN embedding vector(768)")
    op.execute(
        "CREATE INDEX ix_news_embedding_embedding_hnsw "
        "ON news_embedding USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index('ix_news_embedding_embedding_hnsw', table_name='news_embedding')
    op.drop_index(op.f('ix_news_embedding_symbol'), table_name='news_embedding')
    op.drop_table('news_embedding')

    op.drop_index(op.f('ix_agent_verdict_created_at'), table_name='agent_verdict')
    op.drop_index(op.f('ix_agent_verdict_trade_date'), table_name='agent_verdict')
    op.drop_index(op.f('ix_agent_verdict_symbol'), table_name='agent_verdict')
    op.drop_table('agent_verdict')

    # NOTE: We do NOT drop the pgvector extension — other tables may depend on it.
