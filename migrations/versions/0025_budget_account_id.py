"""Add budgets.account_id for corporate-scoped budgets.

Revision ID: 0025
Revises: 0024
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def _has_unique(table: str, name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(u.get("name") == name for u in inspector.get_unique_constraints(table))


def upgrade() -> None:
    if not _has_table("budgets"):
        return
    with op.batch_alter_table("budgets") as batch:
        if not _has_column("budgets", "account_id"):
            batch.add_column(
                sa.Column(
                    "account_id",
                    sa.String(length=36),
                    nullable=False,
                    server_default="",
                )
            )
        if _has_unique("budgets", "uq_budgets_category_month"):
            batch.drop_constraint("uq_budgets_category_month", type_="unique")
        if not _has_unique("budgets", "uq_budgets_category_month_account"):
            batch.create_unique_constraint(
                "uq_budgets_category_month_account",
                ["category_id", "month", "year", "account_id"],
            )


def downgrade() -> None:
    if not _has_table("budgets"):
        return
    with op.batch_alter_table("budgets") as batch:
        if _has_unique("budgets", "uq_budgets_category_month_account"):
            batch.drop_constraint(
                "uq_budgets_category_month_account", type_="unique"
            )
        if not _has_unique("budgets", "uq_budgets_category_month"):
            batch.create_unique_constraint(
                "uq_budgets_category_month",
                ["category_id", "month", "year"],
            )
        if _has_column("budgets", "account_id"):
            batch.drop_column("account_id")
