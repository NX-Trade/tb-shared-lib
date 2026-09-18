"""add_compressed_api_telemetry_columns

Stores external API request/response bodies compressed instead of truncating
them to 2,000 characters of text. ``response_preview`` stays plain so LIKE
queries work without decompressing, and ``compression`` names the codec so it
can be swapped (zlib → zstd) without another migration.

Also adds the index the retention purge needs: rows are deleted by age, and
order-execution endpoints are kept far longer than data reads (review 13, Q4).

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-18 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("external_api_request", sa.Column("request_payload_z", sa.LargeBinary(), nullable=True))
    op.add_column("external_api_request", sa.Column("response_payload_z", sa.LargeBinary(), nullable=True))
    op.add_column("external_api_request", sa.Column("response_preview", sa.String(length=500), nullable=True))
    op.add_column("external_api_request", sa.Column("compression", sa.String(length=8), nullable=True))
    # Purge scans by (provider, timestamp); endpoint decides the retention class.
    op.create_index(
        "ix_external_api_request_provider_ts",
        "external_api_request",
        ["api_provider", "request_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_external_api_request_provider_ts", table_name="external_api_request")
    op.drop_column("external_api_request", "compression")
    op.drop_column("external_api_request", "response_preview")
    op.drop_column("external_api_request", "response_payload_z")
    op.drop_column("external_api_request", "request_payload_z")
