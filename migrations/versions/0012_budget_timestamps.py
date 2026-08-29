"""Add missing budget created_at / last_alert_level columns.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
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
    if not _has_table("budgets"):
        return
    if not _has_column("budgets", "last_alert_level"):
        op.add_column(
            "budgets",
            sa.Column(
                "last_alert_level",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if not _has_column("budgets", "created_at"):
        op.add_column(
            "budgets",
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )


def downgrade() -> None:
    if _has_table("budgets") and _has_column("budgets", "created_at"):
        op.drop_column("budgets", "created_at")
