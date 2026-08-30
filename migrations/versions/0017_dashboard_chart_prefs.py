"""Persist home-chart preferences and keep defaults aligned with Neon.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
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
    with op.batch_alter_table("settings") as batch:
        if not _has_column("settings", "dashboard_hide_chart"):
            batch.add_column(
                sa.Column(
                    "dashboard_hide_chart",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )
        if not _has_column("settings", "dashboard_chart_days"):
            batch.add_column(
                sa.Column(
                    "dashboard_chart_days",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("30"),
                )
            )


def downgrade() -> None:
    if not _has_table("settings"):
        return
    with op.batch_alter_table("settings") as batch:
        if _has_column("settings", "dashboard_chart_days"):
            batch.drop_column("dashboard_chart_days")
        if _has_column("settings", "dashboard_hide_chart"):
            batch.drop_column("dashboard_hide_chart")
