"""Debt icon/color, cached projection, audit log, schedule interval.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
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
    if _has_table("debts"):
        with op.batch_alter_table("debts") as batch:
            if not _has_column("debts", "icon"):
                batch.add_column(
                    sa.Column("icon", sa.String(length=64), nullable=False, server_default="credit_card")
                )
            if not _has_column("debts", "color"):
                batch.add_column(
                    sa.Column("color", sa.String(length=16), nullable=False, server_default="#F87171")
                )
            if not _has_column("debts", "cached_projection"):
                batch.add_column(sa.Column("cached_projection", sa.JSON(), nullable=True))
            if not _has_column("debts", "forgiven_early"):
                batch.add_column(
                    sa.Column("forgiven_early", sa.Boolean(), nullable=False, server_default="0")
                )
            if not _has_column("debts", "payment_interval_months"):
                batch.add_column(
                    sa.Column("payment_interval_months", sa.Integer(), nullable=False, server_default="1")
                )
    if not _has_table("debt_audit_logs"):
        op.create_table(
            "debt_audit_logs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("debt_id", sa.String(length=36), nullable=False, index=True),
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
            "ix_debt_audit_logs_debt_created",
            "debt_audit_logs",
            ["debt_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("debt_audit_logs"):
        op.drop_index("ix_debt_audit_logs_debt_created", table_name="debt_audit_logs")
        op.drop_table("debt_audit_logs")
    if _has_table("debts"):
        with op.batch_alter_table("debts") as batch:
            for col in (
                "payment_interval_months",
                "forgiven_early",
                "cached_projection",
                "color",
                "icon",
            ):
                if _has_column("debts", col):
                    batch.drop_column(col)
