"""Settings: currency_user_set (first-run auto region vs explicit picker).

Revision ID: 0030
Revises: 0029
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
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
    if not _has_table("settings"):
        return
    if _has_column("settings", "currency_user_set"):
        return
    with op.batch_alter_table("settings") as batch:
        # Existing rows: treat current default_currency as a user choice (DEFAULT 1).
        batch.add_column(
            sa.Column(
                "currency_user_set",
                sa.Boolean(),
                nullable=False,
                server_default="1",
            )
        )


def downgrade() -> None:
    if not _has_table("settings"):
        return
    if not _has_column("settings", "currency_user_set"):
        return
    with op.batch_alter_table("settings") as batch:
        batch.drop_column("currency_user_set")
