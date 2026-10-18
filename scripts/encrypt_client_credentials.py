#!/usr/bin/env python
"""Encrypt the broker credentials already stored in ``client_account``.

New credentials are encrypted on write by the ``EncryptedString`` column, so
this is only for rows that pre-date encryption — and for re-encrypting
everything after a key rotation.

Safe to run repeatedly: a value already encrypted is left alone unless
``--rotate`` is given, and nothing is written when there is nothing to change.

    # report, change nothing
    python scripts/encrypt_client_credentials.py --dry-run

    # encrypt plaintext rows
    python scripts/encrypt_client_credentials.py

    # after changing CREDENTIALS_ENCRYPTION_KEY, with the old key still in
    # CREDENTIALS_ENCRYPTION_KEY_PREVIOUS, rewrite everything under the new one
    python scripts/encrypt_client_credentials.py --rotate

    # back to plaintext, needed before narrowing the columns again
    python scripts/encrypt_client_credentials.py --decrypt

Reads and writes raw column values with SQL rather than through the ORM: the
``EncryptedString`` type encrypts on write and decrypts on read, which is
exactly what has to be bypassed to see what is really stored — and what makes
``--decrypt`` impossible through the ORM at all.

The legacy ``extra_credentials`` blob is emptied of its credential keys while
encrypting. Those are plaintext copies of values that now live in their own
columns, and leaving them would defeat the point.
"""

import argparse
import json
import logging
import os
import sys

from sqlalchemy import text

from tb_utils.config.db_session import get_session_factory
from tb_utils.security import KEY_ENV, decrypt, encrypt, looks_encrypted

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("encrypt_client_credentials")

CREDENTIAL_COLUMNS = (
    "api_key",
    "api_secret",
    "broker_client_id",
    "phone",
    "pin",
    "totp_secret",
)

# Credential names that were duplicated into extra_credentials, either case.
BLOB_CREDENTIAL_KEYS = {
    "client_id",
    "mobile",
    "phone",
    "pin",
    "totp_secret",
    "api_key",
    "api_secret",
}


def target_value(raw: str, *, decrypt_mode: bool, rotate: bool) -> str | None:
    """What this stored value should become, or None if it is already right."""
    if not raw:
        return None
    if decrypt_mode:
        return decrypt(raw) if looks_encrypted(raw) else None
    if looks_encrypted(raw):
        # encrypt() refuses to double-wrap, so a rotation has to go back to
        # plaintext first; without --rotate there is nothing to do.
        return encrypt(decrypt(raw)) if rotate else None
    return encrypt(raw)


def blob_without_credentials(blob) -> tuple[dict | None, list[str]]:
    """The blob with its credential keys removed, and which were removed."""
    if not blob:
        return blob, []
    if isinstance(blob, str):
        blob = json.loads(blob)
    dropped = [k for k in blob if str(k).lower() in BLOB_CREDENTIAL_KEYS]
    return ({k: v for k, v in blob.items() if k not in dropped}, dropped) if dropped else (blob, [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report, change nothing")
    parser.add_argument(
        "--rotate", action="store_true", help="re-encrypt every value under the current key"
    )
    parser.add_argument(
        "--decrypt", action="store_true", help="write the values back as plain text"
    )
    args = parser.parse_args()

    if args.rotate and args.decrypt:
        parser.error("--rotate and --decrypt do opposite things; pick one")
    if not args.decrypt and not os.getenv(KEY_ENV):
        logger.error("%s is not set — there is nothing to encrypt with.", KEY_ENV)
        return 1

    verb = "decrypt" if args.decrypt else ("re-encrypt" if args.rotate else "encrypt")
    columns = ", ".join(CREDENTIAL_COLUMNS)
    touched = 0

    with get_session_factory()() as db:
        rows = (
            db.execute(
                text(
                    f"SELECT account_id, client_code, {columns}, extra_credentials "  # noqa: S608
                    "FROM client_account ORDER BY account_id"
                )
            )
            .mappings()
            .all()
        )

        for row in rows:
            changes = {}
            for column in CREDENTIAL_COLUMNS:
                new = target_value(row[column], decrypt_mode=args.decrypt, rotate=args.rotate)
                if new is not None:
                    changes[column] = new

            blob, dropped = (
                (row["extra_credentials"], [])
                if args.decrypt
                else blob_without_credentials(row["extra_credentials"])
            )

            if not changes and not dropped:
                logger.info("%s: already correct", row["client_code"])
                continue

            touched += 1
            logger.info(
                "%s: %s %s%s",
                row["client_code"],
                verb,
                ", ".join(sorted(changes)) or "nothing",
                f" | clearing from extra_credentials: {', '.join(sorted(dropped))}"
                if dropped
                else "",
            )
            if args.dry_run:
                continue

            params: dict = {"account_id": row["account_id"], **changes}
            assignments = [f"{c} = :{c}" for c in changes]
            if dropped:
                assignments.append("extra_credentials = CAST(:blob AS json)")
                params["blob"] = json.dumps(blob)
            db.execute(
                text(  # noqa: S608 - assignments are built from a fixed column list
                    f"UPDATE client_account SET {', '.join(assignments)} "
                    "WHERE account_id = :account_id"
                ),
                params,
            )

        if args.dry_run:
            logger.info("Dry run: %d account(s) would change.", touched)
            db.rollback()
        else:
            db.commit()
            logger.info("Done: %d account(s) updated.", touched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
