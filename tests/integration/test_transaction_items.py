"""Multi-line transaction items: amount sum, balance, and repo round-trip."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.entities.transaction import (
    Transaction,
    TransactionItem,
    TransactionType,
)
from tests.conftest import run_async
from tests.factories import make_account, make_transaction


def test_expense_with_items_sums_and_roundtrips(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        items = [
            TransactionItem(name="Bread", amount=Decimal("40"), category="Еда"),
            TransactionItem(name="Milk", amount=Decimal("60"), category="Еда"),
            TransactionItem(name="Eggs", amount=Decimal("50"), category="Еда"),
        ]
        tx = make_transaction(
            acc.id,
            amount="150",
            category="Еда",
            tx_type=TransactionType.EXPENSE,
        )
        # Rebuild so the after-validator syncs amount from items.
        tx = Transaction(
            account_id=tx.account_id,
            amount=Decimal("1"),
            category=tx.category,
            date=tx.date,
            type=tx.type,
            currency=tx.currency,
            items=items,
        )

        created = await container.add_transaction.execute(tx)
        assert created.amount == Decimal("150.00")
        assert len(created.items) == 3
        assert [i.name for i in created.items] == ["Bread", "Milk", "Eggs"]
        assert sum((i.amount for i in created.items), Decimal("0")) == Decimal(
            "150.00"
        )

        after = await container.account_repository.get_by_id(acc.id)
        assert after is not None
        assert after.balance == Decimal("850.00")

        loaded = await container.transaction_repository.get_by_id(created.id)
        assert loaded is not None
        assert loaded.amount == Decimal("150.00")
        assert len(loaded.items) == 3
        assert [(i.name, i.amount, i.category) for i in loaded.items] == [
            ("Bread", Decimal("40.00"), "Еда"),
            ("Milk", Decimal("60.00"), "Еда"),
            ("Eggs", Decimal("50.00"), "Еда"),
        ]

    run_async(_run())
