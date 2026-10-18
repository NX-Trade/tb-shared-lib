# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
# pylint: disable=unused-argument        # fixtures requested purely for their side effects
"""Credentials are ciphertext at rest and plaintext only in memory."""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import Text

from tb_utils.models.account import ClientAccount
from tb_utils.models.types import EncryptedString
from tb_utils.schema.account import CREDENTIAL_FIELDS
from tb_utils.security import (
    KEY_ENV,
    PREVIOUS_KEY_ENV,
    EncryptionKeyMissing,
    decrypt,
    encrypt,
    generate_key,
    looks_encrypted,
    reset_cipher_cache,
)

SECRET = "PFL65K4XWVMIG4NCYUUROKBWXPQOQDO4"


@pytest.fixture
def key(monkeypatch):
    """A configured encryption key, isolated from the real environment."""
    value = generate_key()
    monkeypatch.setenv(KEY_ENV, value)
    monkeypatch.delenv(PREVIOUS_KEY_ENV, raising=False)
    reset_cipher_cache()
    yield value
    reset_cipher_cache()


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(PREVIOUS_KEY_ENV, raising=False)
    reset_cipher_cache()
    yield
    reset_cipher_cache()


def test_a_secret_does_not_survive_in_the_stored_value(key):
    stored = encrypt(SECRET)

    assert SECRET not in stored
    assert looks_encrypted(stored)
    assert decrypt(stored) == SECRET


def test_the_same_secret_encrypts_differently_each_time(key):
    """Fernet carries a random IV, so equal secrets must not look equal at rest."""
    assert encrypt(SECRET) != encrypt(SECRET)
    assert decrypt(encrypt(SECRET)) == decrypt(encrypt(SECRET)) == SECRET


def test_empty_values_pass_straight_through(key):
    assert encrypt(None) is None and encrypt("") == ""
    assert decrypt(None) is None and decrypt("") == ""


def test_re_saving_does_not_wrap_the_ciphertext_twice(key):
    once = encrypt(SECRET)

    assert encrypt(once) == once
    assert decrypt(once) == SECRET


def test_a_row_written_before_encryption_still_reads(key):
    """Plaintext left over from before the migration must not break."""
    assert decrypt("plain-text-api-key") == "plain-text-api-key"


def test_without_a_key_values_are_stored_as_they_are(no_key):
    # Refusing to write would take the platform down over a missing env var.
    assert encrypt(SECRET) == SECRET


def test_ciphertext_without_a_key_raises_rather_than_returning_rubbish(key, monkeypatch):
    stored = encrypt(SECRET)
    monkeypatch.delenv(KEY_ENV, raising=False)
    reset_cipher_cache()

    # Returning the ciphertext would send an unusable "credential" to a broker.
    with pytest.raises(EncryptionKeyMissing, match=KEY_ENV):
        decrypt(stored)


def test_the_wrong_key_raises_rather_than_returning_rubbish(key, monkeypatch):
    stored = encrypt(SECRET)
    monkeypatch.setenv(KEY_ENV, generate_key())
    reset_cipher_cache()

    with pytest.raises(EncryptionKeyMissing):
        decrypt(stored)


def test_a_rotated_key_still_reads_what_the_old_one_wrote(monkeypatch):
    old, new = generate_key(), generate_key()
    monkeypatch.setenv(KEY_ENV, old)
    monkeypatch.delenv(PREVIOUS_KEY_ENV, raising=False)
    reset_cipher_cache()
    written_under_old = encrypt(SECRET)

    # Rotate: the new key encrypts, the old one is kept only for reading.
    monkeypatch.setenv(KEY_ENV, new)
    monkeypatch.setenv(PREVIOUS_KEY_ENV, old)
    reset_cipher_cache()

    assert decrypt(written_under_old) == SECRET
    fresh = encrypt(SECRET)
    assert decrypt(fresh) == SECRET

    # Once re-encrypted, the old key is no longer needed.
    monkeypatch.delenv(PREVIOUS_KEY_ENV)
    reset_cipher_cache()
    assert decrypt(fresh) == SECRET
    reset_cipher_cache()


def test_generate_key_produces_a_usable_fernet_key():
    Fernet(generate_key().encode())  # does not raise


def test_looks_encrypted_only_matches_real_tokens():
    assert not looks_encrypted("9650063413")
    assert not looks_encrypted(None) and not looks_encrypted(12345)


def test_the_column_type_encrypts_on_write_and_decrypts_on_read(key):
    """What the ORM hands Postgres, and what it hands Python back."""
    column = EncryptedString()
    to_database = column.process_bind_param(SECRET, None)

    assert SECRET not in to_database and looks_encrypted(to_database)
    assert column.process_result_value(to_database, None) == SECRET


def test_the_column_type_is_backed_by_text_so_a_token_cannot_be_truncated(key):
    """A Fernet token outgrows the sized columns these replaced."""
    assert EncryptedString.impl is Text
    # A 36-character key encrypts well past the old String(100).
    assert len(encrypt("560bdeeb-8653-4034-8545-7a7055b5ae12")) > 100


def test_every_credential_column_on_the_model_is_encrypted():
    """A credential added later must not quietly land in plain text."""
    for name in CREDENTIAL_FIELDS:
        column = ClientAccount.__table__.columns[name]
        assert isinstance(column.type, EncryptedString), f"{name} is stored unencrypted"
