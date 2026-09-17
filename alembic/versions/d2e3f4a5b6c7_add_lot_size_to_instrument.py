"""add lot_size to instrument

Revision ID: d2e3f4a5b6c7
Revises: c1f2e3d4b5a6
Create Date: 2026-09-17 08:50:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1f2e3d4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instrument",
        sa.Column("lot_size", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("instrument", "lot_size")
