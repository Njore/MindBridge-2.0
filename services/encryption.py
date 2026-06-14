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

    Returns a placeholder string instead of raising if the value can't be
    decrypted (e.g. wrong key, or legacy plaintext rows that predate
    encryption being enabled) — this prevents one bad row from 500'ing
    an entire conversation/list view.
    """
    if encrypted_content is None:
        return None
    try:
        return cipher_suite.decrypt(encrypted_content.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        logger.error("Failed to decrypt content — invalid token or wrong key")
        return '[Unable to decrypt message]'
    except Exception as e:
        logger.error(f"Failed to decrypt content: {e}")
        return '[Unable to decrypt message]'