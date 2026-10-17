"""client_account credentials: add login columns, drop static_token

broker_client_id, phone, pin and totp_secret were being kept in the
extra_credentials JSON blob, where the same field appeared under several
spellings (MOBILE vs mobile, TOTP_SECRET vs totp_secret) with nothing to
validate them. Every broker needs some subset of these, so they become
columns. extra_credentials stays, and readers fall back to it, so rows that
have not been migrated keep working.

static_token goes: it was a hand-pasted access token acting as a middle
fallback between Redis and the environment, and no row ever held one. Tokens
now live in Redis under a per-broker, per-client key that the collector
refreshes daily, which leaves nothing for a static column to add.

Revision ID: k1e2f3a4b5c6
Revises: j1d2e3f4a5b6
Create Date: 2026-10-17
"""

import sqlalchemy as sa
from alembic import op

revision = "k1e2f3a4b5c6"
down_revision = "j1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_account", sa.Column("broker_client_id", sa.String(length=50)))
    op.add_column("client_account", sa.Column("phone", sa.String(length=20)))
    op.add_column("client_account", sa.Column("pin", sa.String(length=32)))
    op.add_column("client_account", sa.Column("totp_secret", sa.String(length=64)))

    # Move what is already stored, accepting either spelling. extra_credentials
    # is left in place: it is the fallback until every row is confirmed moved.
    op.execute(
        """
        UPDATE client_account SET
            broker_client_id = COALESCE(
                broker_client_id,
                extra_credentials ->> 'client_id',
                extra_credentials ->> 'CLIENT_ID'
            ),
            phone = COALESCE(
                phone,
                extra_credentials ->> 'mobile',
                extra_credentials ->> 'MOBILE',
                extra_credentials ->> 'phone',
                extra_credentials ->> 'PHONE'
            ),
            pin = COALESCE(pin, extra_credentials ->> 'pin', extra_credentials ->> 'PIN'),
            totp_secret = COALESCE(
                totp_secret,
                extra_credentials ->> 'totp_secret',
                extra_credentials ->> 'TOTP_SECRET'
            )
        WHERE extra_credentials IS NOT NULL
        """
    )

    op.drop_column("client_account", "static_token")


def downgrade() -> None:
    op.add_column("client_account", sa.Column("static_token", sa.Text(), nullable=True))
    op.drop_column("client_account", "totp_secret")
    op.drop_column("client_account", "pin")
    op.drop_column("client_account", "phone")
    op.drop_column("client_account", "broker_client_id")
