"""BackupService filesystem roundtrip."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.core.config import AppConfig
from lib.infrastructure.services.backup_service import BackupService, BackupServiceError


def test_backup_restore_roundtrip(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    cfg.db_path.write_text("sqlite-payload", encoding="utf-8")
    from lib.infrastructure.services.secret_box import encrypt_secret, master_key_path

    encrypt_secret({"api_key": "k"}, config=cfg)
    assert master_key_path(cfg).is_file()

    svc = BackupService(cfg)
    backup = svc.backup(label="test")
    assert backup.exists()
    assert backup.name.endswith("_test.db")
    assert Path(str(backup) + ".key").is_file()

    cfg.db_path.write_text("changed", encoding="utf-8")
    master_key_path(cfg).unlink()
    restored = svc.restore(backup, make_safety_copy=True)
    assert restored.read_text(encoding="utf-8") == "sqlite-payload"
    assert master_key_path(cfg).is_file()
    assert svc.list_backups()


def test_daily_backup_overwrites_once_per_day(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    cfg.db_path.write_text("v1", encoding="utf-8")
    svc = BackupService(cfg)

    first = svc.ensure_daily_backup()
    assert first is not None
    assert first.name == "finanse_daily.db"
    assert first.read_text(encoding="utf-8") == "v1"
    assert svc.daily_stamp_path.read_text(encoding="utf-8").strip() == svc.today_local()

    cfg.db_path.write_text("v2", encoding="utf-8")
    skipped = svc.ensure_daily_backup()
    assert skipped is None
    assert first.read_text(encoding="utf-8") == "v1"

    forced = svc.ensure_daily_backup(force=True)
    assert forced is not None
    assert forced.read_text(encoding="utf-8") == "v2"
    assert forced.resolve() == first.resolve()


def test_backup_missing_db(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    svc = BackupService(cfg)
    with pytest.raises(BackupServiceError):
        svc.backup()
