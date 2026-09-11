"""Preview and commit CSV statement imports."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.entities.transaction import TransactionType
from tests.conftest import run_async
from tests.factories import make_account


def test_preview_and_commit_csv_import(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        payload = (
            b"date,amount,description\n"
            b"2026-01-15,25.00,Coffee\n"
            b"2026-01-16,-10.00,Groceries\n"
            b"bad,1.00,Skip me\n"
        )
        info, rows = await container.preview_csv_import.execute(payload)
        assert info.headers[0] == "date"
        assert sum(1 for row in rows if row.ok) == 2
        created = await container.commit_csv_import.execute(
            rows, account_id=acc.id, default_category="Прочее"
        )
        assert len(created) == 2
        types = {tx.type for tx in created}
        assert TransactionType.INCOME in types
        assert TransactionType.EXPENSE in types
        assert all("csv-import" in (tx.tags or []) for tx in created)
        listed = await container.list_transactions.execute(account_id=acc.id)
        comments = {tx.comment for tx in listed}
        assert "Coffee" in comments
        assert "Groceries" in comments
        refreshed = await container.account_repository.get_by_id(acc.id)
        assert refreshed is not None
        assert refreshed.balance == Decimal("1015.00")

    run_async(_run())
