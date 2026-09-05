"""MediaStore receipt path round-trip."""

from __future__ import annotations

from pathlib import Path

from lib.core.config import AppConfig
from lib.infrastructure.services.media_store import MediaStore


def test_save_and_delete_receipt(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path / "data")
    cfg.ensure_directories()
    store = MediaStore(cfg)
    rel = store.save_receipt(
        transaction_id="tx-1",
        filename="receipt.jpg",
        payload=b"\xff\xd8\xff" + b"jpeg-bytes",
    )
    assert rel.startswith("receipts/tx-1/")
    abs_path = store.absolute(rel)
    assert abs_path.is_file()
    store.delete_paths([rel])
    assert not abs_path.exists()
    store.delete_transaction_dir("tx-1")
    assert not (cfg.receipts_dir / "tx-1").exists()


def test_rejects_empty_and_huge(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path / "data")
    cfg.ensure_directories()
    store = MediaStore(cfg)
    try:
        store.save_receipt(transaction_id="t", filename="a.jpg", payload=b"")
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        store.save_receipt(
            transaction_id="t",
            filename="a.jpg",
            payload=b"x" * (12 * 1024 * 1024 + 1),
        )
        assert False, "expected ValueError"
    except ValueError:
        pass
