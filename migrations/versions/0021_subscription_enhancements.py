"""Subscription icon/color and audit log.

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
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
    if _has_table("subscriptions"):
        with op.batch_alter_table("subscriptions") as batch:
            if not _has_column("subscriptions", "icon"):
                batch.add_column(
                    sa.Column(
                        "icon",
                        sa.String(length=64),
                        nullable=False,
                        server_default="autorenew",
                    )
                )
            if not _has_column("subscriptions", "color"):
                batch.add_column(
                    sa.Column(
                        "color",
                        sa.String(length=16),
                        nullable=False,
                        server_default="#A78BFA",
                    )
                )
    if not _has_table("subscription_audit_logs"):
        op.create_table(
            "subscription_audit_logs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("subscription_id", sa.String(length=36), nullable=False, index=True),
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
            "ix_subscription_audit_logs_sub_created",
            "subscription_audit_logs",
            ["subscription_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("subscription_audit_logs"):
        op.drop_index(
            "ix_subscription_audit_logs_sub_created",
            table_name="subscription_audit_logs",
        )
        op.drop_table("subscription_audit_logs")
    if _has_table("subscriptions"):
        with op.batch_alter_table("subscriptions") as batch:
            for col in ("color", "icon"):
                if _has_column("subscriptions", col):
                    batch.drop_column(col)
