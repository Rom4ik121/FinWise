"""Interactive tour flags and catalog (domain — no Flet).

Revision ID: 0023
Revises: 0022
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = (
    "completed_onboarding",
    "completed_tour_debts",
    "completed_tour_analytics",
    "completed_tour_goals",
)


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
        for name in _COLS:
            if _has_column("settings", name):
                continue
            # server_default=1 → existing users skip tours; new AppSettings still False.
            batch.add_column(
                sa.Column(
                    name,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )


def downgrade() -> None:
    if not _has_table("settings"):
        return
    with op.batch_alter_table("settings") as batch:
        for name in reversed(_COLS):
            if _has_column("settings", name):
                batch.drop_column(name)
