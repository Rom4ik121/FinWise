"""Legacy SQLite category scope migration."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from lib.core.database import _migrate_categories_account_scope


def test_migrate_categories_rebuilds_name_unique(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE categories (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    icon VARCHAR(64) NOT NULL,
                    color VARCHAR(16) NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    is_system BOOLEAN NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    UNIQUE (name)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO categories
                (id, name, icon, color, kind, is_system, is_active, created_at, updated_at)
                VALUES
                ('c1', 'Food', 'fastfood', '#000', 'expense', 0, 1, '2026-01-01', '2026-01-01')
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE budgets (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    category_id VARCHAR(128) NOT NULL
                        REFERENCES categories(name) ON DELETE CASCADE,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    amount_limit NUMERIC(18, 2) NOT NULL,
                    spent NUMERIC(18, 2) NOT NULL,
                    last_alert_level INTEGER NOT NULL DEFAULT 0,
                    account_id VARCHAR(36) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO budgets
                (id, category_id, month, year, amount_limit, spent,
                 last_alert_level, account_id, created_at, updated_at)
                VALUES
                ('b1', 'Food', 9, 2026, 100, 0, 0, '', '2026-01-01', '2026-01-01')
                """
            )
        )
        # Partial upgrade like the crashed run: column added, UNIQUE(name) still there.
        conn.execute(
            text(
                "ALTER TABLE categories ADD COLUMN account_id "
                "VARCHAR(36) NOT NULL DEFAULT ''"
            )
        )
        _migrate_categories_account_scope(conn)

        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(categories)")).fetchall()
        }
        assert "account_id" in cols
        unique_sets = []
        for row in conn.execute(text("PRAGMA index_list(categories)")).fetchall():
            if not row[2]:
                continue
            unique_sets.append(
                [
                    c[2]
                    for c in conn.execute(
                        text(f'PRAGMA index_info("{row[1]}")')
                    ).fetchall()
                ]
            )
        assert ["name"] not in unique_sets
        assert any(s == ["name", "account_id"] for s in unique_sets)
        fks = conn.execute(text("PRAGMA foreign_key_list(budgets)")).fetchall()
        assert not any(fk[2] == "categories" for fk in fks)
        # Same name on different scopes must be allowed after migrate.
        conn.execute(
            text(
                """
                INSERT INTO categories
                (id, name, icon, color, kind, account_id, is_system, is_active,
                 created_at, updated_at)
                VALUES
                ('c2', 'Food', 'fastfood', '#000', 'expense', 'corp-1', 0, 1,
                 '2026-01-01', '2026-01-01')
                """
            )
        )
        n = conn.execute(text("SELECT COUNT(*) FROM categories")).scalar()
        assert n == 2
