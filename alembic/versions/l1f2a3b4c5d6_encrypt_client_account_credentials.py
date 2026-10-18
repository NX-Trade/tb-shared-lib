"""widen client_account credential columns for encryption

Schema only. A Fernet token runs to roughly 140 characters, which the sized
columns would reject on write ("value too long for type character varying"),
so they become Text.

Encrypting the rows that are already stored is a data change, not a schema
change, and lives in ``scripts/encrypt_client_credentials.py``. Keeping it
out of here means it can be re-run, dry-run, and reused for a key rotation,
and that a schema migration does not depend on a runtime encryption key.

Revision ID: l1f2a3b4c5d6
Revises: k1e2f3a4b5c6
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "l1f2a3b4c5d6"
down_revision = "k1e2f3a4b5c6"
branch_labels = None
depends_on = None

CREDENTIAL_COLUMNS: tuple[tuple[str, int], ...] = (
    ("api_key", 100),
    ("api_secret", 100),
    ("broker_client_id", 50),
    ("phone", 20),
    ("pin", 32),
    ("totp_secret", 64),
)


def upgrade() -> None:
    for column, _ in CREDENTIAL_COLUMNS:
        op.alter_column("client_account", column, type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    """Narrow the columns back.

    Run ``scripts/encrypt_client_credentials.py --decrypt`` first: a Fernet
    token does not fit these widths and Postgres refuses the conversion
    outright ("value too long for type character varying"), so nothing is
    truncated and no guard is needed here.
    """
    for column, length in CREDENTIAL_COLUMNS:
        op.alter_column(
            "client_account", column, type_=sa.String(length=length), existing_nullable=True
        )
