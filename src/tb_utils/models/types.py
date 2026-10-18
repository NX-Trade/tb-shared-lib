"""Custom SQLAlchemy column types."""

from typing import Any, Optional

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from tb_utils.security import decrypt, encrypt


class EncryptedString(TypeDecorator):  # pylint: disable=too-many-ancestors
    """A string column encrypted at rest and decrypted on read.

    Transparent to every consumer: ``account.api_secret`` is the plaintext
    secret in Python and ciphertext in Postgres, so the broker adapters and
    the collector's auth manager need no encryption code of their own, and
    the plaintext only exists in memory for as long as it is being used.

    Backed by ``Text`` rather than a sized ``String`` because a Fernet token
    is roughly 140 characters for even a short secret — a ``String(100)``
    column would silently truncate on write.
    """

    impl = Text
    cache_ok = True

    @property
    def python_type(self) -> type:
        return str

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        return encrypt(value)

    def process_result_value(self, value: Any, dialect: Any) -> Optional[str]:
        return decrypt(value)

    def process_literal_param(self, value: Any, dialect: Any) -> str:
        """Inline a literal — encrypted, so a compiled statement cannot leak it."""
        return repr(encrypt(value))
