"""Exchange API connections.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("exchange_connections"):
        return
    op.create_table(
        "exchange_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("holdings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id"),
    )
    op.create_index(
        "ix_exchange_connections_account_id",
        "exchange_connections",
        ["account_id"],
        unique=True,
    )
    op.create_index(
        "ix_exchange_connections_provider",
        "exchange_connections",
        ["provider"],
    )


def downgrade() -> None:
    if _has_table("exchange_connections"):
        op.drop_table("exchange_connections")
