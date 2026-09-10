"""BackupService filesystem roundtrip."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.core.config import AppConfig
from lib.infrastructure.services.backup_service import BackupService, BackupServiceError


def test_backup_restore_roundtrip(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    # Real SQLite header so restore magic-check accepts the file.
    cfg.db_path.write_bytes(b"SQLite format 3\x00payload")
    from lib.infrastructure.services.secret_box import encrypt_secret, master_key_path

    encrypt_secret({"api_key": "k"}, config=cfg)
    assert master_key_path(cfg).is_file()

    svc = BackupService(cfg)
    backup = svc.backup(label="test")
    assert backup.exists()
    assert backup.name.endswith("_test.db")
    assert Path(str(backup) + ".key").is_file()

    cfg.db_path.write_bytes(b"SQLite format 3\x00changed")
    master_key_path(cfg).unlink()
    restored = svc.restore(backup, make_safety_copy=True)
    assert restored.read_bytes() == b"SQLite format 3\x00payload"
    assert master_key_path(cfg).is_file()
    assert svc.list_backups()


def test_restore_rejects_non_sqlite(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    cfg.db_path.write_bytes(b"SQLite format 3\x00ok")
    fake = cfg.backup_dir / "finanse_bad.db"
    fake.write_text("not-a-db", encoding="utf-8")
    svc = BackupService(cfg)
    with pytest.raises(BackupServiceError, match="Not a SQLite"):
        svc.restore(fake, make_safety_copy=False)


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


def test_backup_embeds_secret_key_when_sidecar_missing(tmp_path: Path) -> None:
    import sqlite3

    from lib.infrastructure.services.secret_box import encrypt_secret, master_key_path

    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    conn = sqlite3.connect(str(cfg.db_path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()
    encrypt_secret({"api_key": "k"}, config=cfg)
    original_key = master_key_path(cfg).read_bytes()

    svc = BackupService(cfg)
    backup = svc.backup(label="embed")
    Path(str(backup) + ".key").unlink()
    master_key_path(cfg).unlink()

    svc.restore(backup, make_safety_copy=False)
    assert master_key_path(cfg).is_file()
    assert master_key_path(cfg).read_bytes() == original_key
    live = sqlite3.connect(str(cfg.db_path))
    names = {row[0] for row in live.execute("SELECT name FROM sqlite_master")}
    live.close()
    assert "_finanse_secret_box" not in names


def test_sqlite_online_backup_ignores_later_wal_writes(tmp_path: Path) -> None:
    import sqlite3

    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    conn = sqlite3.connect(str(cfg.db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    svc = BackupService(cfg)
    backup = svc.backup(label="wal")
    conn.execute("INSERT INTO t VALUES (99)")
    conn.commit()
    conn.close()
    cfg.db_path.write_bytes(b"SQLite format 3\x00changed")
    svc.restore(backup, make_safety_copy=False)
    restored = sqlite3.connect(str(cfg.db_path))
    try:
        rows = [row[0] for row in restored.execute("SELECT x FROM t ORDER BY x")]
    finally:
        restored.close()
    assert rows == [1]


def test_fwbackup_roundtrip_restores_db_key_and_media(tmp_path: Path) -> None:
    import sqlite3

    from lib.infrastructure.services.fwbackup import is_fwbackup, needs_password
    from lib.infrastructure.services.secret_box import encrypt_secret, export_master_key_bytes

    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    conn = sqlite3.connect(str(cfg.db_path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (7)")
    conn.commit()
    conn.close()
    encrypt_secret({"api_key": "k"}, config=cfg)
    original_key = export_master_key_bytes(cfg)
    assert original_key
    receipt = cfg.receipts_dir / "tx1"
    receipt.mkdir(parents=True, exist_ok=True)
    (receipt / "shot.jpg").write_bytes(b"\xff\xd8\xff")

    svc = BackupService(cfg)
    bundle = svc.backup(label="share", bundle=True)
    assert bundle.suffix == ".fwbackup"
    blob = bundle.read_bytes()
    assert is_fwbackup(blob)
    assert needs_password(blob) is False

    cfg.db_path.unlink()
    from lib.infrastructure.services.secret_box import delete_master_key

    delete_master_key(cfg)
    (receipt / "shot.jpg").unlink()

    svc.restore(bundle, make_safety_copy=False)
    live = sqlite3.connect(str(cfg.db_path))
    try:
        assert live.execute("SELECT x FROM t").fetchone() == (7,)
        names = {row[0] for row in live.execute("SELECT name FROM sqlite_master")}
    finally:
        live.close()
    assert "_finanse_secret_box" not in names
    assert export_master_key_bytes(cfg) == original_key
    assert (cfg.receipts_dir / "tx1" / "shot.jpg").read_bytes() == b"\xff\xd8\xff"


def test_fwbackup_password_roundtrip(tmp_path: Path) -> None:
    from lib.infrastructure.services.fwbackup import decrypt_bundle, encrypt_bundle, needs_password

    wrapped = encrypt_bundle(b"PK\x03\x04payload", "secret")
    assert needs_password(wrapped)
    assert decrypt_bundle(wrapped, "secret").startswith(b"PK")
    with pytest.raises(ValueError, match="Password required"):
        decrypt_bundle(wrapped, "")
    with pytest.raises(ValueError, match="Backup decrypt failed"):
        decrypt_bundle(wrapped, "wrong")
