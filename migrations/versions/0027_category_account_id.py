"""Scope categories per corporate account (personal = empty account_id).

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
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


def _fk_names(table: str, *, referred: str | None = None) -> list[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return []
    out: list[str] = []
    for fk in inspector.get_foreign_keys(table):
        if referred is not None and fk.get("referred_table") != referred:
            continue
        name = fk.get("name")
        if name:
            out.append(name)
    return out


def upgrade() -> None:
    if not _has_table("categories"):
        return
    with op.batch_alter_table("categories") as batch:
        if not _has_column("categories", "account_id"):
            batch.add_column(
                sa.Column(
                    "account_id",
                    sa.String(length=36),
                    nullable=False,
                    server_default="",
                )
            )
        if _has_unique("categories", "uq_categories_name"):
            batch.drop_constraint("uq_categories_name", type_="unique")
        if not _has_unique("categories", "uq_categories_name_account"):
            batch.create_unique_constraint(
                "uq_categories_name_account",
                ["name", "account_id"],
            )

    # budgets.category_id → categories.name FK is invalid once name is no longer
    # uniquely constrained alone; app deletes budgets via DeleteCategoryUseCase.
    if _has_table("budgets"):
        for fk_name in _fk_names("budgets", referred="categories"):
            with op.batch_alter_table("budgets") as batch:
                batch.drop_constraint(fk_name, type_="foreignkey")


def downgrade() -> None:
    if not _has_table("categories"):
        return
    with op.batch_alter_table("categories") as batch:
        if _has_unique("categories", "uq_categories_name_account"):
            batch.drop_constraint("uq_categories_name_account", type_="unique")
        if not _has_unique("categories", "uq_categories_name"):
            batch.create_unique_constraint("uq_categories_name", ["name"])
        if _has_column("categories", "account_id"):
            batch.drop_column("account_id")
    if _has_table("budgets") and not _fk_names("budgets", referred="categories"):
        with op.batch_alter_table("budgets") as batch:
            batch.create_foreign_key(
                "fk_budgets_category_name",
                "categories",
                ["category_id"],
                ["name"],
                ondelete="CASCADE",
                onupdate="CASCADE",
            )
