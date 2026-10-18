"""widen client_account credential columns for encryption

Schema only. A Fernet token runs to roughly 140 characters, so the sized
columns would truncate one on write; they become Text.

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
    """Narrow the columns again, refusing if that would truncate a secret.

    Encrypted values do not fit the original widths, so decrypt first:
    ``python scripts/encrypt_client_credentials.py --decrypt``.
    """
    bind = op.get_bind()
    for column, length in CREDENTIAL_COLUMNS:
        too_long = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM client_account "  # noqa: S608 - a fixed column list
                f"WHERE {column} IS NOT NULL AND length({column}) > :length"
            ),
            {"length": length},
        ).scalar()
        if too_long:
            raise RuntimeError(
                f"{too_long} client_account row(s) have a {column} longer than {length} "
                "characters, which this would truncate. They are probably still encrypted — "
                "run scripts/encrypt_client_credentials.py --decrypt first."
            )

    for column, length in CREDENTIAL_COLUMNS:
        op.alter_column(
            "client_account", column, type_=sa.String(length=length), existing_nullable=True
        )
