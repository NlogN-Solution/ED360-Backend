"""Credential encryption round-trip. Real CREDENTIAL_ENCRYPTION_KEY is loaded
from .env by conftest/app startup already (see app/core/config.py) — these
tests exercise the actual configured key, matching how it's used in
production rather than a mocked one, since a mismatch between "what the
tests check" and "what encrypt_credential actually does at runtime" is
exactly the kind of gap that would let a broken key pass silently.
"""

import pytest

from app.core.encryption import CredentialEncryptionError, decrypt_credential, encrypt_credential


def test_round_trip():
    plaintext = "EAAsome-fake-permanent-access-token"
    ciphertext = encrypt_credential(plaintext)
    assert ciphertext != plaintext
    assert decrypt_credential(ciphertext) == plaintext


def test_ciphertext_is_not_reused_verbatim_across_calls():
    # Fernet includes a random IV/timestamp — encrypting the same plaintext
    # twice must not produce identical ciphertext (a static-nonce bug would).
    a = encrypt_credential("same-value")
    b = encrypt_credential("same-value")
    assert a != b
    assert decrypt_credential(a) == decrypt_credential(b) == "same-value"


def test_decrypting_garbage_raises_credential_encryption_error():
    with pytest.raises(CredentialEncryptionError):
        decrypt_credential("not-a-real-fernet-token")


def test_decrypting_plaintext_by_mistake_raises_not_silently_succeeds():
    with pytest.raises(CredentialEncryptionError):
        decrypt_credential("EAAsome-fake-permanent-access-token")
