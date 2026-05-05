"""
Token encryption via Fernet + HKDF.

Root key material: install_uuid (persisted at /var/lib/filaops/config/install_uuid).
Key derivation: HKDF-SHA256 with domain separation via `info` parameter.
Encryption: Fernet (symmetric, authenticated, timestamped).

Usage:
    from app.core.crypto import encrypt_token, decrypt_token, EncryptedString

    # Direct use:
    ciphertext = encrypt_token("my-secret-api-key")
    plaintext = decrypt_token(ciphertext)

    # SQLAlchemy column type:
    class MyModel(Base):
        secret = Column(EncryptedString(length=500), nullable=True)
"""
import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import String, TypeDecorator

from app.core.license_cache import get_install_uuid

logger = logging.getLogger(__name__)

# Domain separation constant — change this to derive a different key
# for a different encryption context (e.g., backup encryption)
_TOKEN_ENCRYPTION_INFO = b"filaops-token-encryption-v1"


def _derive_key() -> bytes:
    """Derive a Fernet key from install_uuid via HKDF."""
    install_uuid = get_install_uuid()
    if not install_uuid:
        raise RuntimeError(
            "install_uuid not available — cannot derive encryption key. "
            "Ensure the license cache is initialized before encrypting tokens."
        )
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        info=_TOKEN_ENCRYPTION_INFO,
        salt=None,  # install_uuid is unique per install; salt not needed
    )
    raw_key = hkdf.derive(install_uuid.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns base64 Fernet token."""
    if not plaintext:
        return plaintext
    key = _derive_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a Fernet token. Returns plaintext string."""
    if not ciphertext:
        return ciphertext
    key = _derive_key()
    f = Fernet(key)
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


class EncryptedString(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts/decrypts string values.

    Stores Fernet tokens in the database. Application code sees plaintext.
    Handles migration gracefully: if a stored value fails to decrypt
    (e.g., it's still plaintext from before encryption was added),
    returns the raw value and logs a warning.

    Usage:
        class MyModel(Base):
            api_key = Column(EncryptedString(length=500), nullable=True)
    """

    impl = String
    cache_ok = True

    def __init__(self, length=500, **kwargs):
        super().__init__(**kwargs)
        self.impl = String(length)

    def process_bind_param(self, value, dialect):
        """Encrypt on write."""
        if value is None or value == "":
            return value
        try:
            return encrypt_token(value)
        except Exception as e:
            logger.error(f"Failed to encrypt token: {e}")
            raise

    def process_result_value(self, value, dialect):
        """Decrypt on read. Falls back to raw value if decryption fails (migration grace)."""
        if value is None or value == "":
            return value
        try:
            return decrypt_token(value)
        except InvalidToken:
            # Value is probably plaintext from before encryption was added.
            # Return as-is — next write will encrypt it.
            logger.warning(
                "Token decryption failed — returning raw value. "
                "This is expected during migration from plaintext to encrypted storage."
            )
            return value
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            return value
