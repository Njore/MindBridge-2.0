"""
Shared application-layer encryption helpers (Fernet / AES-128-CBC + HMAC).

Used to encrypt sensitive text fields at rest (e.g. Private Pocket entries,
capsule messages). The DB stores ciphertext only — the app decrypts on read
using ENCRYPTION_KEY from the environment.

IMPORTANT:
- ENCRYPTION_KEY must be set and identical across all app instances, or
  previously-encrypted data becomes unreadable.
- If ENCRYPTION_KEY is missing, a key is generated at process startup
  (development only) — anything encrypted with it will NOT be decryptable
  after a restart. Never rely on this in production.
"""

import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

if ENCRYPTION_KEY:
    cipher_suite = Fernet(ENCRYPTION_KEY.encode())
else:
    logger.warning(
        "ENCRYPTION_KEY not set — generating an ephemeral key for this "
        "process. Encrypted data will be UNREADABLE after restart. "
        "Set ENCRYPTION_KEY in your environment for any persistent data."
    )
    cipher_suite = Fernet(Fernet.generate_key())


def encrypt_content(content: str) -> str:
    """Encrypt a plaintext string for storage at rest."""
    if content is None:
        return None
    return cipher_suite.encrypt(content.encode('utf-8')).decode('utf-8')


def decrypt_content(encrypted_content: str) -> str:
    """
    Decrypt a ciphertext string read from storage.

    Handles two cases gracefully:
    1. Legacy plaintext rows written before encryption was enabled —
       detected by the absence of the Fernet 'gAAAAA' prefix and
       returned as-is so old data stays readable.
    2. Genuinely corrupt / wrong-key tokens — logged and returned as
       the original value so the UI still shows something useful rather
       than a placeholder.
    """
    if encrypted_content is None:
        return None

    # Fernet tokens always start with 'gAAAAA' (base64-encoded version byte).
    # If the stored value doesn't have this prefix it was written as plaintext
    # (before encryption was wired in) — just return it directly.
    if not encrypted_content.startswith('gAAAAA'):
        return encrypted_content

    try:
        return cipher_suite.decrypt(encrypted_content.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        logger.error("Failed to decrypt content — invalid token or wrong key")
        return encrypted_content   # return raw value rather than a useless placeholder
    except Exception as e:
        logger.error(f"Failed to decrypt content: {e}")
        return encrypted_content