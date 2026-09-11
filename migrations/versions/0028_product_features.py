"""Product features: filters JSON, budget thresholds, recurring, net worth, FTS.

Revision ID: 0028
Revises: 0027
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
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
    if _has_table("settings"):
        with op.batch_alter_table("settings") as batch:
            if not _has_column("settings", "tx_filters_json"):
                batch.add_column(sa.Column("tx_filters_json", sa.Text(), nullable=True))
            if not _has_column("settings", "budget_warn_pct"):
                batch.add_column(
                    sa.Column(
                        "budget_warn_pct",
                        sa.Integer(),
                        nullable=False,
                        server_default="80",
                    )
                )
            if not _has_column("settings", "budget_limit_pct"):
                batch.add_column(
                    sa.Column(
                        "budget_limit_pct",
                        sa.Integer(),
                        nullable=False,
                        server_default="100",
                    )
                )

    bind = op.get_bind()
    if not _has_table("recurring_rules"):
        op.create_table(
            "recurring_rules",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sa.String(length=16), nullable=False),
            sa.Column("account_id", sa.String(length=36), nullable=False),
            sa.Column("category", sa.String(length=128), nullable=False),
            sa.Column("comment", sa.Text(), nullable=False, server_default=""),
            sa.Column("type", sa.String(length=16), nullable=False, server_default="expense"),
            sa.Column("interval", sa.String(length=16), nullable=False, server_default="monthly"),
            sa.Column("interval_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("next_run", sa.Date(), nullable=False),
            sa.Column("paused", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("skip_next", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("auto_create", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("last_created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["account_id"], ["accounts.id"], ondelete="CASCADE"
            ),
        )
        op.create_index("ix_recurring_rules_account_id", "recurring_rules", ["account_id"])
        op.create_index("ix_recurring_rules_next_run", "recurring_rules", ["next_run"])

    if not _has_table("net_worth_snapshots"):
        op.create_table(
            "net_worth_snapshots",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("captured_on", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sa.String(length=16), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("captured_on", name="uq_net_worth_captured_on"),
        )
        op.create_index(
            "ix_net_worth_captured_on", "net_worth_snapshots", ["captured_on"]
        )

    if bind.dialect.name == "sqlite" and _has_table("transactions"):
        # Rebuild FTS so amount / payee (receipt names) are searchable.
        op.execute("DROP TABLE IF EXISTS transactions_fts")
        op.execute(
            """
            CREATE VIRTUAL TABLE transactions_fts USING fts5(
                id UNINDEXED,
                category,
                comment,
                tags,
                payee,
                amount,
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """
        )
        op.execute(
            """
            INSERT INTO transactions_fts(id, category, comment, tags, payee, amount)
            SELECT
                id,
                COALESCE(category, ''),
                COALESCE(comment, ''),
                COALESCE(CAST(tags AS TEXT), ''),
                COALESCE(CAST(items AS TEXT), ''),
                COALESCE(CAST(amount AS TEXT), '')
            FROM transactions
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table("net_worth_snapshots"):
        op.drop_table("net_worth_snapshots")
    if _has_table("recurring_rules"):
        op.drop_table("recurring_rules")
    if _has_table("settings"):
        with op.batch_alter_table("settings") as batch:
            if _has_column("settings", "tx_filters_json"):
                batch.drop_column("tx_filters_json")
            if _has_column("settings", "budget_warn_pct"):
                batch.drop_column("budget_warn_pct")
            if _has_column("settings", "budget_limit_pct"):
                batch.drop_column("budget_limit_pct")
    if bind.dialect.name == "sqlite" and _has_table("transactions_fts"):
        op.execute("DROP TABLE IF EXISTS transactions_fts")
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
