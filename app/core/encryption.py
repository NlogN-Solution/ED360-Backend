from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class CredentialEncryptionError(RuntimeError):
    """Raised when CREDENTIAL_ENCRYPTION_KEY is missing/invalid, or a
    ciphertext fails to decrypt (wrong key, corrupted data, or a plaintext
    value passed in by mistake). Deliberately loud and immediate — silently
    storing a credential nothing can ever decrypt again is worse than a
    startup/request failure."""


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().CREDENTIAL_ENCRYPTION_KEY
    if not key:
        raise CredentialEncryptionError(
            "CREDENTIAL_ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            "and add it to .env."
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise CredentialEncryptionError("CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def encrypt_credential(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialEncryptionError("Could not decrypt credential — wrong key or corrupted data.") from exc
