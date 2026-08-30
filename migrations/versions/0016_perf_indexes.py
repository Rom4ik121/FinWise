"""Composite indexes for hot transaction/list queries.

Revision ID: 0016
Revises: 0015

Runtime also creates these via ``_ensure_sqlite_indexes``; this revision
keeps Alembic chain in sync for developer upgrades.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if not _has_table("transactions"):
        return
    for sql in (
        "CREATE INDEX IF NOT EXISTS ix_transactions_goal_date "
        "ON transactions (goal_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_debt_date "
        "ON transactions (debt_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_subscription_date "
        "ON transactions (subscription_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_type_category_date "
        "ON transactions (type, category, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_account_date "
        "ON transactions (account_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_type_date "
        "ON transactions (type, date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_category_date "
        "ON transactions (category, date DESC)",
    ):
        op.execute(sa.text(sql))


def downgrade() -> None:
    if not _has_table("transactions"):
        return
    for name in (
        "ix_transactions_goal_date",
        "ix_transactions_debt_date",
        "ix_transactions_subscription_date",
        "ix_transactions_type_category_date",
    ):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
