"""encrypt client_account credentials at rest

Widens the credential columns to Text — a Fernet token runs to roughly 140
characters, so the sized columns would have truncated on write — then
encrypts whatever is already stored.

The legacy extra_credentials blob is emptied of its credential keys at the
same time. k1e2f3a4b5c6 copied them into columns but left the originals
behind, and leaving plaintext secrets in a JSON column would defeat the
point of encrypting the columns beside it.

Needs CREDENTIALS_ENCRYPTION_KEY to be set. Without it the rows are left as
plaintext and a warning is logged, so the migration is still safe to run —
re-run it once the key is in place.

Revision ID: l1f2a3b4c5d6
Revises: k1e2f3a4b5c6
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

from tb_utils.security import encrypt, looks_encrypted

revision = "l1f2a3b4c5d6"
down_revision = "k1e2f3a4b5c6"
branch_labels = None
depends_on = None

CREDENTIAL_COLUMNS = (
    "api_key",
    "api_secret",
    "broker_client_id",
    "phone",
    "pin",
    "totp_secret",
)

# Credential names that were duplicated into extra_credentials, in either case.
BLOB_CREDENTIAL_KEYS = (
    "client_id", "CLIENT_ID",
    "mobile", "MOBILE", "phone", "PHONE",
    "pin", "PIN",
    "totp_secret", "TOTP_SECRET",
    "api_key", "API_KEY", "api_secret", "API_SECRET",
)


def upgrade() -> None:
    for column in CREDENTIAL_COLUMNS:
        op.alter_column("client_account", column, type_=sa.Text(), existing_nullable=True)

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT account_id, {', '.join(CREDENTIAL_COLUMNS)} FROM client_account")
    ).mappings().all()

    for row in rows:
        changes = {
            column: encrypt(row[column])
            for column in CREDENTIAL_COLUMNS
            if row[column] and not looks_encrypted(row[column])
        }
        if not changes:
            continue
        assignments = ", ".join(f"{c} = :{c}" for c in changes)
        bind.execute(
            sa.text(f"UPDATE client_account SET {assignments} WHERE account_id = :account_id"),
            {**changes, "account_id": row["account_id"]},
        )

    # Drop the now-redundant plaintext copies, keeping any genuinely
    # broker-specific extras that are not credentials.
    for key in BLOB_CREDENTIAL_KEYS:
        bind.execute(
            sa.text(
                "UPDATE client_account SET extra_credentials = extra_credentials - :key "
                "WHERE extra_credentials ? :key"
            ),
            {"key": key},
        )


def downgrade() -> None:
    """Decrypt back to plaintext and restore the sized columns.

    The blob copies are not put back: the columns are the source of truth
    now, and re-creating plaintext duplicates would be the opposite of the
    point.
    """
    from tb_utils.security import decrypt

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT account_id, {', '.join(CREDENTIAL_COLUMNS)} FROM client_account")
    ).mappings().all()

    for row in rows:
        changes = {
            column: decrypt(row[column])
            for column in CREDENTIAL_COLUMNS
            if looks_encrypted(row[column])
        }
        if not changes:
            continue
        assignments = ", ".join(f"{c} = :{c}" for c in changes)
        bind.execute(
            sa.text(f"UPDATE client_account SET {assignments} WHERE account_id = :account_id"),
            {**changes, "account_id": row["account_id"]},
        )

    for column, length in (
        ("api_key", 100),
        ("api_secret", 100),
        ("broker_client_id", 50),
        ("phone", 20),
        ("pin", 32),
        ("totp_secret", 64),
    ):
        op.alter_column(
            "client_account", column, type_=sa.String(length=length), existing_nullable=True
        )
