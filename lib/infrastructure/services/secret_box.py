"""Local secret encryption for API keys (AES-GCM + legacy FW1 decrypt)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from lib.core.config import AppConfig, get_default_config

_MAGIC_V1 = b"FW1"
_MAGIC_V2 = b"FW2"


def _key_path(config: AppConfig | None = None) -> Path:
    cfg = config or get_default_config()
    cfg.ensure_directories()
    return cfg.data_dir / ".secret_box_key"


def _load_master_key(config: AppConfig | None = None) -> bytes:
    path = _key_path(config)
    if path.is_file():
        return path.read_bytes()
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Legacy FW1 keystream (kept for decrypting older blobs)."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def master_key_path(config: AppConfig | None = None) -> Path:
    """Return the path of the device master key used by secret_box."""
    return _key_path(config)


def delete_master_key(config: AppConfig | None = None) -> bool:
    """Remove the device master key used by :func:`encrypt_secret`.

    Returns ``True`` when a key file was deleted.
    """
    path = _key_path(config)
    if not path.is_file():
        return False
    path.unlink()
    return True


def encrypt_secret(payload: dict[str, Any], *, config: AppConfig | None = None) -> str:
    """Encrypt a JSON object with AES-256-GCM and return a hex blob (FW2)."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    key = _load_master_key(config)
    nonce = secrets.token_bytes(12)
    cipher = AESGCM(key).encrypt(nonce, raw, _MAGIC_V2)
    return (_MAGIC_V2 + nonce + cipher).hex()


def decrypt_secret(blob: str, *, config: AppConfig | None = None) -> dict[str, Any]:
    """Decrypt a hex blob produced by :func:`encrypt_secret` (FW2 or legacy FW1)."""
    data = bytes.fromhex(blob)
    key = _load_master_key(config)
    if data.startswith(_MAGIC_V2):
        if len(data) < 3 + 12 + 16:
            raise ValueError("Invalid secret blob")
        nonce = data[3:15]
        cipher = data[15:]
        try:
            raw = AESGCM(key).decrypt(nonce, cipher, _MAGIC_V2)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Secret decrypt failed") from exc
    elif data.startswith(_MAGIC_V1):
        if len(data) < 3 + 16 + 32:
            raise ValueError("Invalid secret blob")
        nonce = data[3:19]
        mac = data[19:51]
        cipher = data[51:]
        expected = hmac.new(key, _MAGIC_V1 + nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("Secret MAC mismatch")
        raw = bytes(a ^ b for a, b in zip(cipher, _stream(key, nonce, len(cipher))))
    else:
        raise ValueError("Invalid secret blob")
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Secret payload must be an object")
    return parsed
