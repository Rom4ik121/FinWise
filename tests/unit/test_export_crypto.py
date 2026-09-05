"""Encrypted export blob round-trip."""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from lib.domain.use_cases.export_data import _encrypt_export, decrypt_export_blob


def test_encrypt_decrypt_export_roundtrip() -> None:
    raw = b'{"version":1,"accounts":[]}'
    blob = _encrypt_export(raw, "secret-pass")
    assert blob.startswith(b"FWEX")
    assert decrypt_export_blob(blob, "secret-pass") == raw


def test_decrypt_export_bad_password_raises() -> None:
    blob = _encrypt_export(b"{}", "right")
    with pytest.raises((InvalidTag, ValueError)):
        decrypt_export_blob(blob, "wrong")


def test_decrypt_export_invalid_blob_raises() -> None:
    with pytest.raises(ValueError, match="Invalid encrypted export"):
        decrypt_export_blob(b"not-fwex", "x")
