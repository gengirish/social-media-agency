"""Fernet symmetric encryption for OAuth tokens at rest."""

import structlog
from cryptography.fernet import Fernet, InvalidToken

from agency.config import get_settings

logger = structlog.get_logger()

# Used only when APP_ENV=dev and TOKEN_ENCRYPTION_KEY is unset (local development).
_DEV_FALLBACK_FERNET_KEY = "BrzKBk4ZcUtgmSLCuiTrCXPF-idmkdWqnzD6XHY8Y5Y="


def _effective_token_encryption_key() -> str:
    settings = get_settings()
    if settings.token_encryption_key:
        return settings.token_encryption_key
    if settings.app_env == "dev":
        return _DEV_FALLBACK_FERNET_KEY
    raise ValueError(
        "TOKEN_ENCRYPTION_KEY must be set when APP_ENV is not dev "
        "(generate with: python -c \"from cryptography.fernet import Fernet; "
        'print(Fernet.generate_key().decode())")'
    )


def get_fernet() -> Fernet:
    key = _effective_token_encryption_key()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.warning(
            "token_decrypt_legacy_plaintext",
            hint="Re-save OAuth connection to encrypt at rest",
        )
        return ciphertext
