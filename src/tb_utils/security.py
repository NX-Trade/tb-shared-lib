"""Encryption for credentials held in the database.

Broker credentials — API secrets, login PINs, TOTP seeds — are encrypted at
rest with Fernet (AES-128-CBC with an HMAC), keyed from the environment. The
key never lives in the database, so a dump, a backup, a read replica or a
stray ``pg_dump`` in a log yields nothing usable on its own.

This does not defend against an attacker who already has the application
host: the key is in that process's environment. What it removes is every
weaker path to the same secrets, which is most of them.

Two keys are read so a rotation can be done without downtime:

* ``CREDENTIALS_ENCRYPTION_KEY`` — used to encrypt, and tried first to decrypt.
* ``CREDENTIALS_ENCRYPTION_KEY_PREVIOUS`` — only tried for decryption, so
  values written under the old key stay readable until they are re-saved.

Generate one with ``python -c "from tb_utils.security import generate_key;
print(generate_key())"``. **Losing the key loses the credentials** — they
cannot be recovered and would have to be re-entered from the broker, so it
belongs in a secret store, not only on the host.
"""

import logging
import os
from functools import lru_cache
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

logger = logging.getLogger(__name__)

KEY_ENV = "CREDENTIALS_ENCRYPTION_KEY"
PREVIOUS_KEY_ENV = "CREDENTIALS_ENCRYPTION_KEY_PREVIOUS"

# Every Fernet token is urlsafe-base64 of a payload whose first byte is the
# version 0x80, which always renders as this prefix. It is how a stored value
# written before encryption is told apart from one written after.
TOKEN_PREFIX = "gAAAAA"


class EncryptionKeyMissing(RuntimeError):
    """Stored ciphertext cannot be read: the key is absent or is the wrong one."""


@lru_cache(maxsize=1)
def _cipher() -> Optional[MultiFernet]:
    """The configured cipher, or None when no key is set."""
    keys = [k for k in (os.getenv(KEY_ENV), os.getenv(PREVIOUS_KEY_ENV)) if k]
    if not keys:
        return None
    return MultiFernet([Fernet(key.encode()) for key in keys])


@lru_cache(maxsize=1)
def _warn_no_key() -> None:
    """Say it once: the cache is the latch."""
    logger.warning(
        "%s is not set — credentials are being stored in plain text. "
        "Set it to encrypt them at rest.",
        KEY_ENV,
    )


def reset_cipher_cache() -> None:
    """Forget the cached cipher, after a key rotation or in tests."""
    _cipher.cache_clear()
    _warn_no_key.cache_clear()


def looks_encrypted(value: Any) -> bool:
    """Whether a stored value is ciphertext rather than legacy plaintext."""
    return isinstance(value, str) and value.startswith(TOKEN_PREFIX)


def encrypt(value: Any) -> Any:
    """Encrypt a credential for storage.

    Empty values and values already encrypted are returned untouched, so
    re-saving a row cannot double-wrap it. With no key configured the value
    is stored as-is: refusing to write would take the platform down over a
    missing environment variable, which is a worse failure than the one it
    would prevent.
    """
    if value is None or value == "" or looks_encrypted(value):
        return value

    cipher = _cipher()
    if cipher is None:
        _warn_no_key()
        return value
    return cipher.encrypt(str(value).encode()).decode()


def decrypt(value: Any) -> Any:
    """Decrypt a stored credential.

    A value that is not ciphertext is returned unchanged — rows written
    before encryption keep working, which is what lets this be switched on
    without a flag day.

    Raises:
        EncryptionKeyMissing: If the value is ciphertext but no key, or the
            wrong key, is configured. This is deliberately loud: returning
            the ciphertext would hand an unusable "credential" to a broker
            login or an order, and the failure would surface somewhere far
            less obvious.
    """
    if not looks_encrypted(value):
        return value

    cipher = _cipher()
    if cipher is None:
        raise EncryptionKeyMissing(
            f"A stored credential is encrypted but {KEY_ENV} is not set, so it cannot be read."
        )
    try:
        return cipher.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionKeyMissing(
            f"A stored credential could not be decrypted with {KEY_ENV}"
            f" (or {PREVIOUS_KEY_ENV}). Was the key rotated without re-encrypting?"
        ) from exc


def generate_key() -> str:
    """A new Fernet key, as the string the environment variable expects."""
    return Fernet.generate_key().decode()
