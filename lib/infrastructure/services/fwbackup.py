"""Encrypted ``.fwbackup`` container (zip of db + key + media).

On-disk layout::

    FWBK | version:u8 | kdf:u8 | [dek:32 | salt:16] | nonce:12 | AES-GCM(zip)

``kdf=0`` (embedded DEK) still authenticates the zip so a shared file is not a
raw SQLite + key dump. ``kdf=1`` derives the DEK with PBKDF2-HMAC-SHA256.
"""

from __future__ import annotations

import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"FWBK"
VERSION = 1
KDF_EMBEDDED = 0
KDF_PBKDF2 = 1
PBKDF2_ROUNDS = 120_000
_NONCE_LEN = 12
_DEK_LEN = 32
_SALT_LEN = 16


def is_fwbackup(data: bytes) -> bool:
    """True when ``data`` starts with the FinWise backup magic."""
    return bool(data) and data.startswith(MAGIC)


def needs_password(data: bytes) -> bool:
    """True when decrypting requires the user password (PBKDF2 wrap)."""
    return len(data) >= 6 and data[:4] == MAGIC and data[5] == KDF_PBKDF2


def encrypt_bundle(zip_bytes: bytes, password: str = "") -> bytes:
    """AES-GCM wrap a zip payload. Empty password → embedded DEK."""
    if not zip_bytes:
        raise ValueError("Backup bundle is empty")
    version = bytes([VERSION])
    secret = (password or "").encode("utf-8")
    nonce = secrets.token_bytes(_NONCE_LEN)
    if secret:
        kdf = bytes([KDF_PBKDF2])
        salt = secrets.token_bytes(_SALT_LEN)
        key = hashlib.pbkdf2_hmac(
            "sha256", secret, salt, PBKDF2_ROUNDS, dklen=_DEK_LEN
        )
        aad = MAGIC + version + kdf
        cipher = AESGCM(key).encrypt(nonce, zip_bytes, aad)
        return MAGIC + version + kdf + salt + nonce + cipher
    kdf = bytes([KDF_EMBEDDED])
    dek = secrets.token_bytes(_DEK_LEN)
    aad = MAGIC + version + kdf
    cipher = AESGCM(dek).encrypt(nonce, zip_bytes, aad)
    return MAGIC + version + kdf + dek + nonce + cipher


def decrypt_bundle(blob: bytes, password: str = "") -> bytes:
    """Unwrap a blob from :func:`encrypt_bundle` to zip bytes."""
    if not is_fwbackup(blob) or len(blob) < 6:
        raise ValueError("Not a FinWise backup bundle")
    version = blob[4]
    if version != VERSION:
        raise ValueError(f"Unsupported backup version {version}")
    kdf = blob[5]
    aad = blob[:6]
    if kdf == KDF_EMBEDDED:
        need = 6 + _DEK_LEN + _NONCE_LEN + 16
        if len(blob) < need:
            raise ValueError("Truncated backup bundle")
        dek = blob[6 : 6 + _DEK_LEN]
        nonce = blob[6 + _DEK_LEN : 6 + _DEK_LEN + _NONCE_LEN]
        cipher = blob[6 + _DEK_LEN + _NONCE_LEN :]
        try:
            return AESGCM(dek).decrypt(nonce, cipher, aad)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Backup decrypt failed") from exc
    if kdf == KDF_PBKDF2:
        secret = (password or "").encode("utf-8")
        if not secret:
            raise ValueError("Password required")
        need = 6 + _SALT_LEN + _NONCE_LEN + 16
        if len(blob) < need:
            raise ValueError("Truncated backup bundle")
        salt = blob[6 : 6 + _SALT_LEN]
        nonce = blob[6 + _SALT_LEN : 6 + _SALT_LEN + _NONCE_LEN]
        cipher = blob[6 + _SALT_LEN + _NONCE_LEN :]
        key = hashlib.pbkdf2_hmac(
            "sha256", secret, salt, PBKDF2_ROUNDS, dklen=_DEK_LEN
        )
        try:
            return AESGCM(key).decrypt(nonce, cipher, aad)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Backup decrypt failed") from exc
    raise ValueError(f"Unknown backup key derivation {kdf}")
