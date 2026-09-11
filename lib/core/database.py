"""SQLAlchemy engine, session factory, and declarative base."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from lib.core.config import AppConfig, get_default_config

logger = logging.getLogger("finanse.database")

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _configure_sqlite(engine: Engine) -> None:
    """Enable foreign keys and WAL for SQLite connections."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def get_engine(config: Optional[AppConfig] = None, *, echo: bool = False) -> Engine:
    """Return a process-wide SQLAlchemy engine, creating it on first use.

    Args:
        config: Optional app config; defaults to :func:`get_default_config`.
        echo: Whether to echo SQL statements.

    Returns:
        Configured :class:`~sqlalchemy.engine.Engine`.
    """
    global _engine, _SessionLocal

    if _engine is not None:
        return _engine

    cfg = config or get_default_config()
    cfg.ensure_directories()

    _engine = create_engine(
        cfg.database_url,
        echo=echo,
        future=True,
        connect_args={"check_same_thread": False},
    )
    if _engine.url.get_backend_name() == "sqlite":
        _configure_sqlite(_engine)

    _SessionLocal = sessionmaker(
        bind=_engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    logger.info("Database engine created at %s", cfg.db_path)
    return _engine


def get_session_factory(config: Optional[AppConfig] = None) -> sessionmaker[Session]:
    """Return the session factory, initializing the engine if needed."""
    global _SessionLocal
    if _SessionLocal is None:
        get_engine(config)
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def get_session(config: Optional[AppConfig] = None) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

    Commits on success, rolls back on exception, and always closes the session.
    """
    session_factory = get_session_factory(config)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(config: Optional[AppConfig] = None, *, echo: bool = False) -> Engine:
    """Create all tables registered on :class:`Base`.

    Imports ORM models so they are registered with the metadata before
    ``create_all`` runs.

    Args:
        config: Optional app config.
        echo: Whether to echo SQL.

    Returns:
        The initialized engine.
    """
    engine = get_engine(config, echo=echo)

    # Register ORM mappers (infrastructure models).
    try:
        import lib.infrastructure.db_models  # noqa: F401
    except ImportError:
        logger.warning(
            "ORM models not importable yet; create_all will only cover "
            "already-registered tables."
        )

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_column_patches(engine)
    _ensure_sqlite_indexes(engine)
    _ensure_transactions_fts(engine)
    _try_alembic_upgrade(config)
    logger.info("Database schema initialized")
    return engine


def _try_alembic_upgrade(config: Optional[AppConfig] = None) -> None:
    """Best-effort ``alembic upgrade head`` (idempotent; warn on failure)."""
    try:
        from pathlib import Path

        from alembic import command
        from alembic.config import Config as AlembicConfig

        root = Path(__file__).resolve().parents[2]
        migrations = root / "migrations"
        if not (migrations / "env.py").is_file():
            return
        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", str(migrations))
        alembic_cfg.set_main_option("prepend_sys_path", str(root))
        cfg = config or get_default_config()
        alembic_cfg.set_main_option("sqlalchemy.url", cfg.database_url)
        command.upgrade(alembic_cfg, "head")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alembic upgrade head skipped: %s", exc)


def _apply_sqlite_column_patches(engine: Engine) -> None:
    """Add newly introduced columns to existing SQLite databases."""
    if engine.url.get_backend_name() != "sqlite":
        return
    patches = {
        "debts": [
            ("account_id", "VARCHAR(36)"),
            ("next_payment_date", "DATETIME"),
            ("next_payment_amount", "NUMERIC(18, 2)"),
            ("accrue_interest", "BOOLEAN NOT NULL DEFAULT 0"),
            ("accrued_interest", "NUMERIC(18, 2) NOT NULL DEFAULT 0"),
            ("last_interest_accrued_at", "DATETIME"),
            ("icon", "VARCHAR(64) NOT NULL DEFAULT 'credit_card'"),
            ("color", "VARCHAR(16) NOT NULL DEFAULT '#F87171'"),
            ("cached_projection", "JSON"),
            ("forgiven_early", "BOOLEAN NOT NULL DEFAULT 0"),
            ("payment_interval_months", "INTEGER NOT NULL DEFAULT 1"),
        ],
        "accounts": [
            ("include_in_total", "BOOLEAN NOT NULL DEFAULT 1"),
            ("is_corporate", "BOOLEAN NOT NULL DEFAULT 0"),
        ],
        "settings": [
            ("reminder_time", "VARCHAR(8) NOT NULL DEFAULT '09:00'"),
            ("reminder_days", "INTEGER NOT NULL DEFAULT 3"),
            ("check_balance_before_subscription", "BOOLEAN NOT NULL DEFAULT 1"),
            ("budget_alerts", "BOOLEAN NOT NULL DEFAULT 1"),
            ("ui_style", "VARCHAR(32) NOT NULL DEFAULT 'neon'"),
            ("dashboard_hide_chart", "BOOLEAN NOT NULL DEFAULT 0"),
            ("dashboard_chart_days", "INTEGER NOT NULL DEFAULT 30"),
            # Existing installs: mark tours completed so upgrades are not noisy.
            ("completed_onboarding", "BOOLEAN NOT NULL DEFAULT 1"),
            ("completed_tour_debts", "BOOLEAN NOT NULL DEFAULT 1"),
            ("completed_tour_analytics", "BOOLEAN NOT NULL DEFAULT 1"),
            ("completed_tour_goals", "BOOLEAN NOT NULL DEFAULT 1"),
            ("tx_filters_json", "TEXT"),
            ("budget_warn_pct", "INTEGER NOT NULL DEFAULT 80"),
            ("budget_limit_pct", "INTEGER NOT NULL DEFAULT 100"),
        ],
        "budgets": [
            ("last_alert_level", "INTEGER NOT NULL DEFAULT 0"),
            ("created_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ("account_id", "VARCHAR(36) NOT NULL DEFAULT ''"),
        ],
        "categories": [
            ("account_id", "VARCHAR(36) NOT NULL DEFAULT ''"),
        ],
        "transactions": [
            ("debt_id", "VARCHAR(36)"),
            ("goal_credit_amount", "NUMERIC(18, 2)"),
            ("goal_item_id", "VARCHAR(36)"),
            ("debt_credit_amount", "NUMERIC(18, 2)"),
            ("subscription_id", "VARCHAR(36)"),
            ("transfer_id", "VARCHAR(36)"),
            ("transfer_peer_account_id", "VARCHAR(36)"),
            ("items", "JSON NOT NULL DEFAULT '[]'"),
            ("attachments", "JSON NOT NULL DEFAULT '[]'"),
        ],
        "goals": [
            ("currency", "VARCHAR(16) NOT NULL DEFAULT 'RUB'"),
            ("status", "VARCHAR(16) NOT NULL DEFAULT 'active'"),
            ("cached_projection", "JSON"),
            ("items", "JSON NOT NULL DEFAULT '[]'"),
            ("closed_early", "BOOLEAN NOT NULL DEFAULT 0"),
            ("icon", "VARCHAR(64) NOT NULL DEFAULT 'flag'"),
            ("color", "VARCHAR(16) NOT NULL DEFAULT '#2DD4BF'"),
            ("planned_monthly_contribution", "NUMERIC(18, 2)"),
        ],
        "subscriptions": [
            ("custom_interval_days", "INTEGER"),
            ("start_date", "DATE"),
            ("end_date", "DATE"),
            ("max_payments", "INTEGER"),
            ("payments_made", "INTEGER NOT NULL DEFAULT 0"),
            ("status", "VARCHAR(16) NOT NULL DEFAULT 'active'"),
            ("last_skip_date", "DATE"),
            ("auto_charge", "BOOLEAN NOT NULL DEFAULT 1"),
            ("icon", "VARCHAR(64) NOT NULL DEFAULT 'autorenew'"),
            ("color", "VARCHAR(16) NOT NULL DEFAULT '#A78BFA'"),
        ],
    }
    with engine.begin() as conn:
        for table, columns in patches.items():
            existing = {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue
            for name, ddl in columns:
                if name in existing:
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                logger.info("Added column %s.%s", table, name)
        # Sync goal status from legacy is_completed flag.
        goals_cols = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(goals)").fetchall()
        }
        if "status" in goals_cols and "is_completed" in goals_cols:
            conn.exec_driver_sql(
                "UPDATE goals SET status = 'completed' "
                "WHERE is_completed = 1 AND status = 'active'"
            )
        sub_cols = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(subscriptions)").fetchall()
        }
        if "start_date" in sub_cols:
            conn.exec_driver_sql(
                "UPDATE subscriptions SET start_date = date(next_billing_date) "
                "WHERE start_date IS NULL"
            )
        if "status" in sub_cols:
            conn.exec_driver_sql(
                "UPDATE subscriptions SET status = CASE "
                "WHEN is_active = 1 THEN 'active' ELSE 'paused' END "
                "WHERE status IS NULL OR status = ''"
            )
        _migrate_categories_account_scope(conn)


def _migrate_categories_account_scope(conn) -> None:
    """Ensure categories uniqueness is (name, account_id); drop budgets FK.

    SQLite autoindexes for table UNIQUE/PK cannot be DROPped — rebuild instead.
    """
    cat_cols = {
        row[1]
        for row in conn.exec_driver_sql("PRAGMA table_info(categories)").fetchall()
    }
    if not cat_cols:
        return
    if "account_id" not in cat_cols:
        conn.exec_driver_sql(
            "ALTER TABLE categories ADD COLUMN account_id "
            "VARCHAR(36) NOT NULL DEFAULT ''"
        )
        logger.info("Added column categories.account_id")
        cat_cols.add("account_id")

    unique_sets: list[list[str]] = []
    for row in conn.exec_driver_sql("PRAGMA index_list(categories)").fetchall():
        if not bool(row[2]) or not row[1]:
            continue
        cols = [
            c[2]
            for c in conn.exec_driver_sql(f'PRAGMA index_info("{row[1]}")').fetchall()
        ]
        unique_sets.append(cols)

    needs_category_rebuild = ["name"] in unique_sets
    budget_cols = {
        row[1]
        for row in conn.exec_driver_sql("PRAGMA table_info(budgets)").fetchall()
    }
    needs_budget_rebuild = False
    if budget_cols:
        fks = conn.exec_driver_sql("PRAGMA foreign_key_list(budgets)").fetchall()
        needs_budget_rebuild = any(fk[2] == "categories" for fk in fks)

    if not needs_category_rebuild and not needs_budget_rebuild:
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_name_account "
            "ON categories (name, account_id)"
        )
        return

    conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        if needs_budget_rebuild:
            conn.exec_driver_sql(
                """
                CREATE TABLE budgets__new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    category_id VARCHAR(128) NOT NULL,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    amount_limit NUMERIC(18, 2) NOT NULL,
                    spent NUMERIC(18, 2) NOT NULL,
                    last_alert_level INTEGER NOT NULL DEFAULT 0,
                    account_id VARCHAR(36) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    UNIQUE (category_id, month, year, account_id)
                )
                """
            )
            src_cols = [
                c
                for c in (
                    "id",
                    "category_id",
                    "month",
                    "year",
                    "amount_limit",
                    "spent",
                    "last_alert_level",
                    "account_id",
                    "created_at",
                    "updated_at",
                )
                if c in budget_cols
            ]
            col_csv = ", ".join(src_cols)
            conn.exec_driver_sql(
                f"INSERT INTO budgets__new ({col_csv}) SELECT {col_csv} FROM budgets"
            )
            conn.exec_driver_sql("DROP TABLE budgets")
            conn.exec_driver_sql("ALTER TABLE budgets__new RENAME TO budgets")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_budgets_month_year "
                "ON budgets (month, year)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_budgets_category_month "
                "ON budgets (category_id, month, year)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_budgets_account_month "
                "ON budgets (account_id, month, year)"
            )
            logger.info("Rebuilt budgets table without categories.name foreign key")

        if needs_category_rebuild:
            conn.exec_driver_sql(
                """
                CREATE TABLE categories__new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    icon VARCHAR(64) NOT NULL,
                    color VARCHAR(16) NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    account_id VARCHAR(36) NOT NULL DEFAULT '',
                    is_system BOOLEAN NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    UNIQUE (name, account_id)
                )
                """
            )
            insert_cols = [
                c
                for c in (
                    "id",
                    "name",
                    "icon",
                    "color",
                    "kind",
                    "account_id",
                    "is_system",
                    "is_active",
                    "created_at",
                    "updated_at",
                )
                if c in cat_cols or c == "account_id"
            ]
            select_parts = [
                "''" if c == "account_id" and "account_id" not in cat_cols else c
                for c in insert_cols
            ]
            conn.exec_driver_sql(
                f"INSERT INTO categories__new ({', '.join(insert_cols)}) "
                f"SELECT {', '.join(select_parts)} FROM categories"
            )
            conn.exec_driver_sql("DROP TABLE categories")
            conn.exec_driver_sql("ALTER TABLE categories__new RENAME TO categories")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_categories_name ON categories (name)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_categories_kind ON categories (kind)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_categories_account_id "
                "ON categories (account_id)"
            )
            logger.info("Rebuilt categories table with UNIQUE(name, account_id)")
        else:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_name_account "
                "ON categories (name, account_id)"
            )
    finally:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def _ensure_sqlite_indexes(engine: Engine) -> None:
    """Create composite indexes that speed list/filter queries on large datasets."""
    if engine.url.get_backend_name() != "sqlite":
        return
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_transactions_date_desc ON transactions (date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_account_date "
        "ON transactions (account_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_type_date "
        "ON transactions (type, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_category_date "
        "ON transactions (category, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_goals_status ON goals (status)",
        "CREATE INDEX IF NOT EXISTS ix_goals_deadline ON goals (deadline)",
        "CREATE INDEX IF NOT EXISTS ix_debts_status ON debts (status)",
        "CREATE INDEX IF NOT EXISTS ix_debts_due_date ON debts (due_date)",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_status ON subscriptions (status)",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_start_date ON subscriptions (start_date)",
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_next_billing "
        "ON subscriptions (status, next_billing_date)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_subscription_id "
        "ON transactions (subscription_id)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_transfer_id "
        "ON transactions (transfer_id)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_goal_date "
        "ON transactions (goal_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_debt_date "
        "ON transactions (debt_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_subscription_date "
        "ON transactions (subscription_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_type_category_date "
        "ON transactions (type, category, date DESC)",
    )
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for sql in statements:
            conn.exec_driver_sql(sql)
        if "exchange_connections" in tables:
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_exchange_connections_provider "
                "ON exchange_connections (provider)"
            )
        if "budgets" in tables:
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_budgets_month_year "
                "ON budgets (month, year)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_budgets_category_month "
                "ON budgets (category_id, month, year)"
            )


def _ensure_transactions_fts(engine: Engine) -> None:
    """Create and backfill FTS5 index for transaction free-text search."""
    if engine.url.get_backend_name() != "sqlite":
        return
    create_sql = """
        CREATE VIRTUAL TABLE transactions_fts USING fts5(
            id UNINDEXED,
            category,
            comment,
            tags,
            payee,
            amount,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """
    fill_sql = """
        INSERT INTO transactions_fts(id, category, comment, tags, payee, amount)
        SELECT
            id,
            COALESCE(category, ''),
            COALESCE(comment, ''),
            COALESCE(CAST(tags AS TEXT), ''),
            COALESCE(CAST(items AS TEXT), ''),
            COALESCE(CAST(amount AS TEXT), '')
        FROM transactions
    """
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
        if "transactions" not in tables:
            return
        needs_rebuild = "transactions_fts" not in tables
        if "transactions_fts" in tables:
            try:
                cols = {
                    str(row[1])
                    for row in conn.exec_driver_sql(
                        "PRAGMA table_info(transactions_fts)"
                    ).fetchall()
                }
                if "amount" not in cols or "payee" not in cols:
                    needs_rebuild = True
            except Exception:  # noqa: BLE001
                needs_rebuild = True
        if not needs_rebuild:
            return
        try:
            if "transactions_fts" in tables:
                conn.exec_driver_sql("DROP TABLE IF EXISTS transactions_fts")
            conn.exec_driver_sql(create_sql)
            conn.exec_driver_sql(fill_sql)
            logger.info("Created transactions_fts FTS5 index")
        except Exception as exc:  # noqa: BLE001
            logger.warning("transactions_fts setup skipped: %s", exc)


def reset_engine() -> None:
    """Dispose the global engine (useful in tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
