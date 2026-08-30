"""Add debt schedule, default account, and interest accrual columns.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
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
    if not _has_table("debts"):
        return
    cols = [
        ("account_id", sa.Column("account_id", sa.String(36), nullable=True)),
        (
            "next_payment_date",
            sa.Column("next_payment_date", sa.DateTime(timezone=True), nullable=True),
        ),
        (
            "next_payment_amount",
            sa.Column("next_payment_amount", sa.Numeric(18, 2), nullable=True),
        ),
        (
            "accrue_interest",
            sa.Column(
                "accrue_interest",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        ),
        (
            "accrued_interest",
            sa.Column(
                "accrued_interest",
                sa.Numeric(18, 2),
                nullable=False,
                server_default=sa.text("0"),
            ),
        ),
        (
            "last_interest_accrued_at",
            sa.Column(
                "last_interest_accrued_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        ),
    ]
    for name, column in cols:
        if not _has_column("debts", name):
            op.add_column("debts", column)


def downgrade() -> None:
    if not _has_table("debts"):
        return
    for name in (
        "last_interest_accrued_at",
        "accrued_interest",
        "accrue_interest",
        "next_payment_amount",
        "next_payment_date",
        "account_id",
    ):
        if _has_column("debts", name):
            op.drop_column("debts", name)
