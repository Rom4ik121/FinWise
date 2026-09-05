"""Add accounts.is_corporate for isolated corporate workspaces.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
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
    if not _has_column("accounts", "is_corporate"):
        op.add_column(
            "accounts",
            sa.Column(
                "is_corporate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    if not _has_table("accounts"):
        return
    if _has_column("accounts", "is_corporate"):
        op.drop_column("accounts", "is_corporate")
