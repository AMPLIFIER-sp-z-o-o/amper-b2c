"""
Encryption utilities for sensitive storage provider credentials.
Uses Fernet symmetric encryption with graceful fallback on key rotation.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def get_encryption_key():
    """
    Get or derive the encryption key for credentials.

    Derives a key from SECRET_KEY using PBKDF2.
    """
    # Try dedicated encryption key first
    encryption_key = getattr(settings, "MEDIA_ENCRYPTION_KEY", None)
    if encryption_key:
        # Ensure it's bytes
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()
        return encryption_key

    # Derive key from SECRET_KEY using PBKDF2
    secret_key = settings.SECRET_KEY
    if isinstance(secret_key, str):
        secret_key = secret_key.encode()

    # Use PBKDF2 to derive a 32-byte key, then base64 encode for Fernet
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        secret_key,
        b"amper-b2c-media-storage",  # Salt
        100000,  # Iterations
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived_key)


def get_fernet():
    """Get Fernet instance with the encryption key."""
    return Fernet(get_encryption_key())


def encrypt_value(value):
    """
    Encrypt a string value.

    Args:
        value: String to encrypt

    Returns:
        Encrypted string (base64 encoded) or empty string if value is empty
    """
    if not value:
        return ""

    fernet = get_fernet()
    encrypted = fernet.encrypt(value.encode())
    return encrypted.decode()


def decrypt_value(encrypted_value):
    """
    Decrypt an encrypted string value.

    Args:
        encrypted_value: Encrypted string (base64 encoded)

    Returns:
        Decrypted string, or None if decryption fails (e.g., key changed)
    """
    if not encrypted_value:
        return ""

    try:
        fernet = get_fernet()
        decrypted = fernet.decrypt(encrypted_value.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.warning(
            "Failed to decrypt value - encryption key may have changed. User will need to re-enter the credential."
        )
        return None
    except Exception as e:
        logger.error(f"Unexpected error decrypting value: {e}")
        return None


class EncryptedCharField(models.CharField):
    """
    CharField that automatically encrypts values before saving to database
    and decrypts when reading.

    If decryption fails (e.g., after key rotation), returns None instead of
    raising an error. Forms should handle this by requiring re-entry.
    """

    description = "An encrypted CharField"

    def __init__(self, *args, **kwargs):
        # Encrypted values are longer than plain text
        # Fernet adds ~57 bytes overhead + base64 encoding
        kwargs.setdefault("max_length", 500)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Remove max_length from kwargs if it's our default
        if kwargs.get("max_length") == 500:
            del kwargs["max_length"]
        return name, path, args, kwargs

    def get_prep_value(self, value):
        """Encrypt value before saving to database."""
        if value is None:
            return None
        # Don't re-encrypt if already encrypted (starts with gAAAAA which is Fernet signature)
        if value and value.startswith("gAAAAA"):
            return value
        return encrypt_value(value)

    def from_db_value(self, value, expression, connection):
        """Decrypt value when reading from database."""
        if value is None:
            return None
        return decrypt_value(value)

    def to_python(self, value):
        """Convert value to Python object."""
        if value is None:
            return None
        # If it looks encrypted, decrypt it
        if isinstance(value, str) and value.startswith("gAAAAA"):
            return decrypt_value(value)
        return value
