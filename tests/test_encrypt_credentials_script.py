# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
# pylint: disable=unused-argument        # fixtures requested purely for their side effects
"""The credential back-fill script: idempotent, reversible, rotation-aware."""

import importlib.util
import pathlib

import pytest

from tb_utils.security import (
    KEY_ENV,
    PREVIOUS_KEY_ENV,
    decrypt,
    encrypt,
    generate_key,
    looks_encrypted,
    reset_cipher_cache,
)

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "encrypt_client_credentials.py"
spec = importlib.util.spec_from_file_location("encrypt_client_credentials", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

SECRET = "PFL65K4XWVMIG4NCYUUROKBWXPQOQDO4"


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv(KEY_ENV, generate_key())
    monkeypatch.delenv(PREVIOUS_KEY_ENV, raising=False)
    reset_cipher_cache()
    yield
    reset_cipher_cache()


def target(raw, **kw):
    kw.setdefault("decrypt_mode", False)
    kw.setdefault("rotate", False)
    return script.target_value(raw, **kw)


def test_plaintext_is_encrypted(key):
    out = target(SECRET)

    assert looks_encrypted(out) and decrypt(out) == SECRET


def test_an_already_encrypted_value_is_left_alone(key):
    """Re-running must not churn rows, nor double-wrap them."""
    assert target(encrypt(SECRET)) is None


def test_empty_values_are_skipped(key):
    assert target(None) is None and target("") is None


def test_rotation_rewrites_under_the_new_key(monkeypatch):
    old, new = generate_key(), generate_key()
    monkeypatch.setenv(KEY_ENV, old)
    monkeypatch.delenv(PREVIOUS_KEY_ENV, raising=False)
    reset_cipher_cache()
    stored = encrypt(SECRET)

    monkeypatch.setenv(KEY_ENV, new)
    monkeypatch.setenv(PREVIOUS_KEY_ENV, old)
    reset_cipher_cache()

    rotated = target(stored, rotate=True)
    assert rotated is not None and rotated != stored

    # Readable with the new key alone, so the old one can be retired.
    monkeypatch.delenv(PREVIOUS_KEY_ENV)
    reset_cipher_cache()
    assert decrypt(rotated) == SECRET
    reset_cipher_cache()


def test_decrypt_returns_the_plaintext(key):
    assert target(encrypt(SECRET), decrypt_mode=True) == SECRET


def test_decrypt_skips_a_row_that_is_already_plaintext(key):
    assert target(SECRET, decrypt_mode=True) is None


def test_the_blob_keeps_non_credentials_and_loses_the_rest():
    blob, dropped = script.blob_without_credentials(
        {"MOBILE": "9650063413", "TOTP_SECRET": "seed", "exchange": "NSE"}
    )

    assert blob == {"exchange": "NSE"}
    assert sorted(dropped) == ["MOBILE", "TOTP_SECRET"]


def test_a_blob_with_nothing_to_drop_is_returned_unchanged():
    original = {"exchange": "NSE"}

    blob, dropped = script.blob_without_credentials(original)

    assert blob is original and dropped == []


def test_an_empty_blob_is_handled():
    assert script.blob_without_credentials(None) == (None, [])
    assert script.blob_without_credentials({}) == ({}, [])


def test_a_blob_arriving_as_json_text_is_parsed():
    blob, dropped = script.blob_without_credentials('{"pin": "1111", "exchange": "NSE"}')

    assert blob == {"exchange": "NSE"} and dropped == ["pin"]
