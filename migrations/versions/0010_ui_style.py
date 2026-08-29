"""UI style column on settings.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
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
    if _has_table("settings") and not _has_column("settings", "ui_style"):
        op.add_column(
            "settings",
            sa.Column(
                "ui_style",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'classic'"),
            ),
        )


def downgrade() -> None:
    if _has_table("settings") and _has_column("settings", "ui_style"):
        op.drop_column("settings", "ui_style")
