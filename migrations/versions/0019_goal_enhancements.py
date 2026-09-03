"""Goal icon/color, planned monthly, audit log table.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
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
            if not _has_column("goals", "icon"):
                batch.add_column(
                    sa.Column("icon", sa.String(length=64), nullable=False, server_default="flag")
                )
            if not _has_column("goals", "color"):
                batch.add_column(
                    sa.Column("color", sa.String(length=16), nullable=False, server_default="#2DD4BF")
                )
            if not _has_column("goals", "planned_monthly_contribution"):
                batch.add_column(
                    sa.Column("planned_monthly_contribution", sa.Numeric(18, 2), nullable=True)
                )
    if not _has_table("goal_audit_logs"):
        op.create_table(
            "goal_audit_logs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("goal_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index(
            "ix_goal_audit_logs_goal_created",
            "goal_audit_logs",
            ["goal_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("goal_audit_logs"):
        op.drop_index("ix_goal_audit_logs_goal_created", table_name="goal_audit_logs")
        op.drop_table("goal_audit_logs")
    if _has_table("goals"):
        with op.batch_alter_table("goals") as batch:
            if _has_column("goals", "planned_monthly_contribution"):
                batch.drop_column("planned_monthly_contribution")
            if _has_column("goals", "color"):
                batch.drop_column("color")
            if _has_column("goals", "icon"):
                batch.drop_column("icon")
