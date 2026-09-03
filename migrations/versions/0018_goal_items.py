"""Goal sub-items and early-close flag; link contributions to items.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
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


def upgrade() -> None:
    if _has_table("goals"):
        with op.batch_alter_table("goals") as batch:
            if not _has_column("goals", "items"):
                batch.add_column(
                    sa.Column("items", sa.JSON(), nullable=False, server_default="[]")
                )
            if not _has_column("goals", "closed_early"):
                batch.add_column(
                    sa.Column(
                        "closed_early",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.text("0"),
                    )
                )
    if _has_table("transactions") and not _has_column("transactions", "goal_item_id"):
        with op.batch_alter_table("transactions") as batch:
            batch.add_column(sa.Column("goal_item_id", sa.String(length=36), nullable=True))
        op.create_index(
            "ix_transactions_goal_item_id",
            "transactions",
            ["goal_item_id"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("transactions") and _has_column("transactions", "goal_item_id"):
        op.drop_index("ix_transactions_goal_item_id", table_name="transactions")
        with op.batch_alter_table("transactions") as batch:
            batch.drop_column("goal_item_id")
    if _has_table("goals"):
        with op.batch_alter_table("goals") as batch:
            if _has_column("goals", "closed_early"):
                batch.drop_column("closed_early")
            if _has_column("goals", "items"):
                batch.drop_column("items")
