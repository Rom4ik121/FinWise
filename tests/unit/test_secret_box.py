"""Local secret-box roundtrip for exchange API keys (FW2 AES-GCM + legacy FW1)."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

import pytest

from lib.core.config import AppConfig
from lib.infrastructure.services.secret_box import (
    decrypt_secret,
    delete_master_key,
    encrypt_secret,
    export_master_key_bytes,
    store_master_key,
)


def test_secret_box_roundtrip_fw2(tmp_path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    blob = encrypt_secret({"api_key": "k", "secret": "s", "passphrase": "p"}, config=cfg)
    assert blob
    assert bytes.fromhex(blob).startswith(b"FW2")
    assert decrypt_secret(blob, config=cfg) == {
        "api_key": "k",
        "secret": "s",
        "passphrase": "p",
    }


def test_secret_box_rejects_tampering(tmp_path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    blob = encrypt_secret({"api_key": "k"}, config=cfg)
    damaged = blob[:-2] + ("00" if blob[-2:] != "00" else "11")
    with pytest.raises(ValueError):
        decrypt_secret(damaged, config=cfg)


def test_legacy_fw1_still_decryptable(tmp_path) -> None:
    """FW1 XOR+HMAC blobs written by older builds must still decrypt."""
    cfg = AppConfig(data_dir=tmp_path)
    key_path = tmp_path / ".secret_box_key"
    key = secrets.token_bytes(32)
    key_path.write_bytes(key)

    magic = b"FW1"
    nonce = secrets.token_bytes(16)
    raw = json.dumps(
        {"api_key": "legacy", "secret": "old"},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    stream = bytearray()
    counter = 0
    while len(stream) < len(raw):
        stream.extend(
            hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        )
        counter += 1
    cipher = bytes(a ^ b for a, b in zip(raw, stream[: len(raw)]))
    mac = hmac.new(key, magic + nonce + cipher, hashlib.sha256).digest()
    blob = (magic + nonce + mac + cipher).hex()

    assert decrypt_secret(blob, config=cfg) == {
        "api_key": "legacy",
        "secret": "old",
    }


def test_delete_master_key(tmp_path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    encrypt_secret({"api_key": "k"}, config=cfg)
    key_path = tmp_path / ".secret_box_key"
    assert key_path.is_file()
    assert delete_master_key(cfg) is True
    assert not key_path.is_file()
    assert delete_master_key(cfg) is False


def test_ios_keychain_migrates_file_and_roundtrips(tmp_path, monkeypatch) -> None:
    from lib.infrastructure.services import ios_keychain

    store = ios_keychain.use_memory_backend(True)
    monkeypatch.setattr("lib.core.config._is_ios", lambda: True)
    try:
        cfg = AppConfig(data_dir=tmp_path)
        key_path = tmp_path / ".secret_box_key"
        blob = encrypt_secret({"api_key": "k"}, config=cfg)
        assert store
        assert any(store.values())
        assert not key_path.exists()
        assert decrypt_secret(blob, config=cfg) == {"api_key": "k"}
        exported = export_master_key_bytes(cfg)
        assert exported
        assert delete_master_key(cfg) is True
        assert export_master_key_bytes(cfg) is None
        store_master_key(exported, cfg)
        assert decrypt_secret(blob, config=cfg) == {"api_key": "k"}
        assert not key_path.exists()
    finally:
        ios_keychain.use_memory_backend(False)


def test_ios_migrates_existing_file_key(tmp_path, monkeypatch) -> None:
    from lib.infrastructure.services import ios_keychain

    cfg = AppConfig(data_dir=tmp_path)
    blob = encrypt_secret({"api_key": "legacy"}, config=cfg)
    key_path = tmp_path / ".secret_box_key"
    assert key_path.is_file()
    original = key_path.read_bytes()

    store = ios_keychain.use_memory_backend(True)
    monkeypatch.setattr("lib.core.config._is_ios", lambda: True)
    try:
        assert decrypt_secret(blob, config=cfg) == {"api_key": "legacy"}
        assert original in store.values()
        assert not key_path.exists()
    finally:
        ios_keychain.use_memory_backend(False)
