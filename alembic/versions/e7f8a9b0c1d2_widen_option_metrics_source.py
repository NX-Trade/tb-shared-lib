"""widen option_daily_metrics.source to 20 chars

The column was created as varchar(10) with a server_default of
'NSE_BHAVCOPY' — 12 characters. Every insert failed with
StringDataRightTruncation, and the default itself was unusable, so the table
could never be populated by either path.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "option_daily_metrics",
        "source",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
        server_default="NSE_BHAVCOPY",
    )


def downgrade() -> None:
    # Narrowing again would truncate 'NSE_BHAVCOPY', so reset the default to a
    # value that fits before shrinking the column.
    op.alter_column(
        "option_daily_metrics",
        "source",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
        server_default="NSE",
    )
