"""create_system_command_table

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-17 18:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_command",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("command_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("issued_by", sa.String(length=100), nullable=True),
        sa.Column("broker", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", JSON(), server_default="{}", nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_command_command_type"), "system_command", ["command_type"], unique=False)
    op.create_index(op.f("ix_system_command_status"), "system_command", ["status"], unique=False)
    op.create_index(op.f("ix_system_command_issued_at"), "system_command", ["issued_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_system_command_issued_at"), table_name="system_command")
    op.drop_index(op.f("ix_system_command_status"), table_name="system_command")
    op.drop_index(op.f("ix_system_command_command_type"), table_name="system_command")
    op.drop_table("system_command")
