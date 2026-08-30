"""Add accounts.include_in_total for dashboard sum filter.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
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
    if not _has_table("accounts"):
        return
    if not _has_column("accounts", "include_in_total"):
        op.add_column(
            "accounts",
            sa.Column(
                "include_in_total",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )


def downgrade() -> None:
    if not _has_table("accounts"):
        return
    if _has_column("accounts", "include_in_total"):
        op.drop_column("accounts", "include_in_total")
