"""Account CRUD and balance recalculation."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.entities.currency import ExchangeRate
from lib.domain.entities.transaction import TransactionType
from tests.conftest import run_async
from tests.factories import make_account, make_transaction


def test_create_list_update_delete_account(container) -> None:
    async def _run() -> None:
        created = await container.create_account.execute(make_account(name="Wallet"))
        listed = await container.list_accounts.execute()
        assert any(a.id == created.id for a in listed)

        updated = await container.update_account.execute(
            created.model_copy(update={"name": "Main"})
        )
        assert updated.name == "Main"

        assert await container.delete_account.execute(created.id) is True
        remaining = await container.list_accounts.execute()
        assert all(a.id != created.id for a in remaining)

    run_async(_run())


def test_include_in_total_persists(container) -> None:
    async def _run() -> None:
        created = await container.create_account.execute(
            make_account(name="Crypto stash")
        )
        assert created.include_in_total is True
        updated = await container.update_account.execute(
            created.model_copy(update={"include_in_total": False})
        )
        assert updated.include_in_total is False
        loaded = await container.account_repository.get_by_id(created.id)
        assert loaded is not None
        assert loaded.include_in_total is False

    run_async(_run())


def test_recalculate_account_balance(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="100"))
        await container.add_transaction.execute(
            make_transaction(
                acc.id,
                amount="50",
                tx_type=TransactionType.INCOME,
                category="Зарплата",
            )
        )
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="30", category="Еда")
        )
        refreshed = await container.account_repository.get_by_id(acc.id)
        assert refreshed is not None
        assert refreshed.balance == Decimal("120.00")

        # Corrupt balance then recalculate from ledger.
        await container.account_repository.update(
            refreshed.model_copy(update={"balance": Decimal("0")})
        )
        fixed = await container.recalculate_account_balance.execute(acc.id)
        assert fixed.balance == Decimal("120.00")

    run_async(_run())


def test_update_account_currency_converts(container) -> None:
    async def _run() -> None:
        await container.currency_repository.upsert_rates(
            [
                ExchangeRate(base="USD", quote="UZS", rate=Decimal("10000")),
            ]
        )
        acc = await container.create_account.execute(
            make_account(name="USD cash", currency="USD", balance="10")
        )
        await container.add_transaction.execute(
            make_transaction(
                acc.id,
                amount="5",
                tx_type=TransactionType.INCOME,
                category="Зарплата",
                currency="USD",
            )
        )
        updated = await container.update_account.execute(
            acc.model_copy(update={"currency": "UZS"})
        )
        assert updated.currency == "UZS"
        assert updated.initial_balance == Decimal("100000.00")
        assert updated.balance == Decimal("150000.00")
        txs = await container.list_transactions.execute(account_id=acc.id)
        assert all(tx.currency == "UZS" for tx in txs)
        assert txs[0].amount == Decimal("50000.00")

    run_async(_run())


def test_update_account_currency_refuses_without_rate(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(
            make_account(name="Exotic", currency="USD", balance="10")
        )
        try:
            await container.update_account.execute(
                acc.model_copy(update={"currency": "UZS"})
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "No exchange rate" in str(exc)

    run_async(_run())
