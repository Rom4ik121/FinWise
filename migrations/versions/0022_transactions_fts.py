"""FTS5 index for transaction free-text search.

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    if not _has_table("transactions"):
        return
    if _has_table("transactions_fts"):
        return
    # External-content FTS keyed by transaction UUID (UNINDEXED).
    op.execute(
        """
        CREATE VIRTUAL TABLE transactions_fts USING fts5(
            id UNINDEXED,
            category,
            comment,
            tags,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        INSERT INTO transactions_fts(id, category, comment, tags)
        SELECT
            id,
            COALESCE(category, ''),
            COALESCE(comment, ''),
            COALESCE(CAST(tags AS TEXT), '')
        FROM transactions
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    if _has_table("transactions_fts"):
        op.execute("DROP TABLE IF EXISTS transactions_fts")
