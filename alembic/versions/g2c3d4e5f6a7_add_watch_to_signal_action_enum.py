"""Add WATCH to signal_action enum.

Revision ID: g2c3d4e5f6a7
Revises: f3e4a5b6c7d8
Create Date: 2026-09-29 00:07:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g2c3d4e5f6a7"
down_revision: Union[str, None] = "f3e4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE signal_action ADD VALUE IF NOT EXISTS 'WATCH'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type.
    # To fully downgrade, the enum would need to be recreated without WATCH.
    pass
