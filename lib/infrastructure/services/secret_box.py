"""Local secret encryption for API keys (device file + HMAC stream)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

from lib.core.config import AppConfig, get_default_config

_MAGIC = b"FW1"


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
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_secret(payload: dict[str, Any], *, config: AppConfig | None = None) -> str:
    """Encrypt a JSON object and return a hex blob."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    key = _load_master_key(config)
    nonce = secrets.token_bytes(16)
    cipher = bytes(a ^ b for a, b in zip(raw, _stream(key, nonce, len(raw))))
    mac = hmac.new(key, _MAGIC + nonce + cipher, hashlib.sha256).digest()
    return (_MAGIC + nonce + mac + cipher).hex()


def decrypt_secret(blob: str, *, config: AppConfig | None = None) -> dict[str, Any]:
    """Decrypt a hex blob produced by :func:`encrypt_secret`."""
    data = bytes.fromhex(blob)
    if len(data) < 3 + 16 + 32 or not data.startswith(_MAGIC):
        raise ValueError("Invalid secret blob")
    nonce = data[3:19]
    mac = data[19:51]
    cipher = data[51:]
    key = _load_master_key(config)
    expected = hmac.new(key, _MAGIC + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Secret MAC mismatch")
    raw = bytes(a ^ b for a, b in zip(cipher, _stream(key, nonce, len(cipher))))
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Secret payload must be an object")
    return parsed
