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

    # SQLAlchemy column type — backed by TEXT, so no length math required.
    # Fernet ciphertext is ~1.5x the plaintext plus ~57 bytes of overhead;
    # storing in TEXT means callers never have to size the column for the
    # expansion.
    class MyModel(Base):
        secret = Column(EncryptedString, nullable=True)
"""
import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text, TypeDecorator

from app.core.license_cache import get_install_uuid

logger = logging.getLogger(__name__)

# Domain separation constant — change this to derive a different key
# for a different encryption context (e.g., backup encryption)
_TOKEN_ENCRYPTION_INFO = b"filaops-token-encryption-v1"

# Fernet tokens are URL-safe base64 of (version=0x80 || timestamp || IV || ciphertext || HMAC).
# Base64-encoding a leading 0x80 byte produces "gAAAAA" — every legitimate
# Fernet token starts with this prefix. We use it to distinguish "this row
# holds Fernet ciphertext" from "this row holds legacy plaintext from before
# encryption was enabled" during the migration grace window.
_FERNET_PREFIX = "gAAAAA"


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

    Backed by TEXT (no length cap) so callers don't have to size for Fernet's
    ~1.5x + 57-byte expansion. Application code sees plaintext; the database
    stores Fernet ciphertext.

    Migration grace: rows that pre-date encryption hold legacy plaintext that
    won't decode as Fernet. We detect that case via the Fernet prefix
    (`gAAAAA`) and return the raw value with a warning, letting the next save
    re-encrypt it. Anything that *looks* like a Fernet token but fails to
    decrypt (corrupted ciphertext, install_uuid changed) is treated as an
    operational failure: we log an error and return None rather than handing
    the application what it might mistake for a plaintext key.

    Other exceptions — most importantly RuntimeError from _derive_key when
    install_uuid is missing — propagate. They indicate a configuration
    problem that must be loud, not silently masked.

    Usage:
        class MyModel(Base):
            api_key = Column(EncryptedString, nullable=True)
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt on write."""
        if value is None or value == "":
            return value
        return encrypt_token(value)

    def process_result_value(self, value, dialect):
        """Decrypt on read.

        - Empty / None: passthrough.
        - Doesn't start with the Fernet prefix: treat as legacy plaintext
          (migration grace), return raw with a warning.
        - Looks like a Fernet token but fails to decrypt: corrupted ciphertext
          or key drift — log error, return None, do NOT return raw.
        - Any other exception (e.g., install_uuid missing): propagate.
        """
        if value is None or value == "":
            return value
        if not value.startswith(_FERNET_PREFIX):
            # Legacy plaintext from before EncryptedString was introduced.
            # The next write will encrypt it.
            logger.warning(
                "Stored value lacks Fernet prefix — assuming legacy plaintext "
                "(migration grace). Next save will encrypt it."
            )
            return value
        try:
            return decrypt_token(value)
        except InvalidToken:
            # Looks like ciphertext but won't decode: corruption, truncation,
            # or install_uuid change. Returning the raw blob would hand the
            # application a Fernet token masquerading as a real secret —
            # worse than returning None, which surfaces as "not configured."
            logger.error(
                "Fernet-shaped value failed to decrypt — possible corruption "
                "or install_uuid change. Returning None to avoid handing "
                "ciphertext to the application."
            )
            return None
