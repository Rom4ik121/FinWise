"""Alembic revision graph is a single chain ending at 0029."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from lib.core.config import AppConfig
from lib.core.database import rewrite_legacy_alembic_revisions

_ROOT = Path(__file__).resolve().parents[2]
_HEAD = "0029"


def _alembic_config(*, sqlalchemy_url: str | None = None) -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(_ROOT))
    if sqlalchemy_url:
        cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return cfg


def test_alembic_single_head_0029() -> None:
    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    assert heads == [_HEAD]
    ids = {rev.revision for rev in script.walk_revisions()}
    assert "0002" in ids
    assert "0002_reminder_time" not in ids
    rev_0003 = script.get_revision("0003")
    assert rev_0003.down_revision == "0002"


def test_alembic_upgrade_head_empty_sqlite(tmp_path: Path) -> None:
    from alembic import command

    db = tmp_path / "fresh.db"
    url = f"sqlite:///{db}"
    command.upgrade(_alembic_config(sqlalchemy_url=url), "head")
    conn = sqlite3.connect(str(db))
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version is not None
        assert version[0] == _HEAD
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert "accounts" in tables
    assert "settings" in tables
    assert "transactions" in tables


def test_rewrite_legacy_0002_reminder_time_stamp(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    conn = sqlite3.connect(str(cfg.db_path))
    try:
        conn.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        conn.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('0002_reminder_time')"
        )
        conn.commit()
    finally:
        conn.close()
    assert rewrite_legacy_alembic_revisions(cfg.db_path) is True
    conn = sqlite3.connect(str(cfg.db_path))
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()
    assert version is not None
    assert version[0] == "0002"
    assert rewrite_legacy_alembic_revisions(cfg.db_path) is False
