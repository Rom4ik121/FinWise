"""Local secret-box roundtrip for exchange API keys."""

from __future__ import annotations

import pytest

from lib.core.config import AppConfig
from lib.infrastructure.services.secret_box import decrypt_secret, encrypt_secret


def test_secret_box_roundtrip(tmp_path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    blob = encrypt_secret({"api_key": "k", "secret": "s", "passphrase": "p"}, config=cfg)
    assert blob
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
