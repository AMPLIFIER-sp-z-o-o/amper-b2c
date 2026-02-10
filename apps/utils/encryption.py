"""
Fernet encryption utility for storing sensitive data in the database.

Derives a URL-safe base64 Fernet key from Django's SECRET_KEY using PBKDF2.
No extra environment variable is needed.
"""

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings

logger = logging.getLogger(__name__)

_FIXED_SALT = b"amper-b2c-smtp"


def get_fernet_key() -> bytes:
    """
    Derive a URL-safe base64 Fernet key from ``settings.SECRET_KEY``
    using PBKDF2-HMAC-SHA256 with a fixed salt.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_FIXED_SALT,
        iterations=480_000,
    )
    key = kdf.derive(settings.SECRET_KEY.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt *plaintext* with Fernet and return the token as a string."""
    if not plaintext:
        return ""
    f = Fernet(get_fernet_key())
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet token.  Returns the plaintext string.
    On ``InvalidToken`` (corrupt or wrong key) returns an empty string.
    """
    if not ciphertext:
        return ""
    try:
        f = Fernet(get_fernet_key())
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        logger.warning("Failed to decrypt value – returning empty string.")
        return ""
