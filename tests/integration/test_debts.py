"""Debt interest, FX repay, archive, projection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from lib.domain.entities.currency import ExchangeRate
from lib.domain.entities.debt import DebtDirection, DebtStatus
from lib.domain.entities.transaction import TransactionType
from tests.conftest import run_async
from tests.factories import make_account, make_debt


def test_debt_crud_and_list(container) -> None:
    async def _run() -> None:
        debt = await container.create_debt.execute(make_debt())
        listed = await container.list_debts.execute()
        assert any(d.id == debt.id for d in listed)
        assert await container.delete_debt.execute(debt.id) is True

    run_async(_run())


def test_create_debt_rolls_back_when_principal_tx_fails(container, monkeypatch) -> None:
    """Debt row + principal cash must share one UoW."""

    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        real = container.add_transaction.execute

        async def boom(tx):
            raise RuntimeError("simulated principal write failure")

        monkeypatch.setattr(container.add_transaction, "execute", boom)
        with pytest.raises(RuntimeError, match="simulated principal"):
            await container.create_debt.execute(
                make_debt(amount="100", direction=DebtDirection.I_OWE),
                account_id=acc.id,
            )
        debts = await container.list_debts.execute()
        assert debts == []
        after = await container.account_repository.get_by_id(acc.id)
        assert after is not None
        assert after.balance == Decimal("1000.00")
        monkeypatch.setattr(container.add_transaction, "execute", real)

    run_async(_run())


def test_repay_clamps_to_remaining(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        debt = await container.create_debt.execute(
            make_debt(amount="100", direction=DebtDirection.I_OWE),
            account_id=acc.id,
        )
        paid = await container.repay_debt.execute(
            debt.id, Decimal("999"), account_id=acc.id
        )
        assert paid.remaining_amount == Decimal("0.00")
        assert paid.status == DebtStatus.PAID

    run_async(_run())


def test_repay_converts_foreign_currency(container) -> None:
    async def _run() -> None:
        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="USD",
                quote="RUB",
                rate=Decimal("100"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        usd = await container.create_account.execute(
            make_account(name="USD", currency="USD", balance="50")
        )
        debt = await container.create_debt.execute(
            make_debt(amount="500", currency="RUB", direction=DebtDirection.I_OWE)
        )
        paid = await container.repay_debt.execute(
            debt.id, Decimal("5"), account_id=usd.id
        )
        assert paid.remaining_amount == Decimal("0.00")
        assert paid.status == DebtStatus.PAID
        txs = await container.list_transactions.execute(debt_id=debt.id)
        assert len(txs) == 1
        assert txs[0].amount == Decimal("5.00")
        assert txs[0].currency == "USD"
        assert txs[0].debt_credit_amount == Decimal("500.00")

    run_async(_run())


def test_repay_blocks_missing_rate(container) -> None:
    async def _run() -> None:
        eur = await container.create_account.execute(
            make_account(name="EUR", currency="EUR", balance="100")
        )
        debt = await container.create_debt.execute(
            make_debt(amount="100", currency="RUB")
        )
        with pytest.raises(ValueError, match="No exchange rate"):
            await container.repay_debt.execute(
                debt.id, Decimal("10"), account_id=eur.id
            )

    run_async(_run())


def test_archive_and_filter_status(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        debt = await container.create_debt.execute(
            make_debt(amount="50"), account_id=acc.id
        )
        await container.repay_debt.execute(debt.id, Decimal("50"), account_id=acc.id)
        archived = await container.archive_debt.execute(debt.id)
        assert archived.status == DebtStatus.ARCHIVED
        active = await container.list_debts.execute(status=DebtStatus.ACTIVE)
        assert all(d.id != debt.id for d in active)
        archived_list = await container.list_debts.execute(status=DebtStatus.ARCHIVED)
        assert any(d.id == debt.id for d in archived_list)

    run_async(_run())


def test_mark_overdue_and_projection(container) -> None:
    async def _run() -> None:
        past = datetime.now(timezone.utc) - timedelta(days=5)
        debt = await container.create_debt.execute(
            make_debt(amount="300").model_copy(update={"due_date": past})
        )
        changed = await container.mark_overdue_debts.execute()
        assert any(d.id == debt.id for d in changed)
        refreshed = await container.debt_repository.get_by_id(debt.id)
        assert refreshed is not None
        assert refreshed.status == DebtStatus.OVERDUE

        future = datetime.now(timezone.utc) + timedelta(days=90)
        debt2 = await container.create_debt.execute(
            make_debt(amount="900").model_copy(update={"due_date": future})
        )
        projection = await container.get_debt_projection.execute(debt2.id)
        assert projection.remaining_amount == Decimal("900.00")
        assert projection.recommended_monthly_payment is not None
        assert projection.recommended_monthly_payment > 0

    run_async(_run())


def test_delete_debt_payment_restores_remaining(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        debt = await container.create_debt.execute(
            make_debt(amount="200"), account_id=acc.id
        )
        await container.repay_debt.execute(debt.id, Decimal("80"), account_id=acc.id)
        txs = await container.list_transactions.execute(debt_id=debt.id)
        payments = [t for t in txs if "debt_principal" not in (t.tags or [])]
        assert len(payments) == 1
        deleted = await container.delete_debt_payment.execute(
            payments[0].id, debt_id=debt.id
        )
        assert deleted is True
        refreshed = await container.debt_repository.get_by_id(debt.id)
        assert refreshed is not None
        assert refreshed.remaining_amount == Decimal("200.00")
        assert refreshed.status == DebtStatus.ACTIVE

    run_async(_run())


def test_calculate_interest(container) -> None:
    async def _run() -> None:
        started = datetime.now(timezone.utc) - timedelta(days=365)
        debt = await container.create_debt.execute(
            make_debt(amount="1000", interest_rate=Decimal("10"))
        )
        await container.update_debt.execute(
            debt.model_copy(update={"started_at": started})
        )
        result = await container.calculate_debt_interest.execute(debt.id)
        assert result.days >= 365
        assert result.interest_amount >= Decimal("100.00")

    run_async(_run())


def test_interest_requires_rate(container) -> None:
    async def _run() -> None:
        debt = await container.create_debt.execute(make_debt())
        with pytest.raises(ValueError):
            await container.calculate_debt_interest.execute(debt.id)

    run_async(_run())


def test_create_debt_principal_converts_fx(container) -> None:
    async def _run() -> None:
        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="USD",
                quote="RUB",
                rate=Decimal("90"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        usd = await container.create_account.execute(
            make_account(name="USD", currency="USD", balance="0")
        )
        debt = await container.create_debt.execute(
            make_debt(amount="900", currency="RUB", direction=DebtDirection.I_OWE),
            account_id=usd.id,
        )
        assert debt.remaining_amount == Decimal("900.00")
        account = await container.account_repository.get_by_id(usd.id)
        assert account.balance == Decimal("10.00")
        txs = await container.list_transactions.execute(account_id=usd.id)
        assert len(txs) == 1
        assert txs[0].amount == Decimal("10.00")
        assert txs[0].currency == "USD"
        assert txs[0].debt_id == debt.id
        assert "debt_principal" in txs[0].tags

    run_async(_run())


def test_delete_debt_reverses_principal_cash(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="0"))
        debt = await container.create_debt.execute(
            make_debt(amount="100", direction=DebtDirection.I_OWE),
            account_id=acc.id,
        )
        assert debt.remaining_amount == Decimal("100.00")
        account = await container.account_repository.get_by_id(acc.id)
        assert account.balance == Decimal("100.00")
        assert await container.delete_debt.execute(debt.id) is True
        account2 = await container.account_repository.get_by_id(acc.id)
        assert account2.balance == Decimal("0.00")
        assert await container.list_transactions.execute(debt_id=debt.id) == []

    run_async(_run())


def test_create_debt_principal_blocks_missing_rate(container) -> None:
    async def _run() -> None:
        eur = await container.create_account.execute(
            make_account(name="EUR", currency="EUR", balance="0")
        )
        with pytest.raises(ValueError, match="No exchange rate"):
            await container.create_debt.execute(
                make_debt(amount="100", currency="RUB"),
                account_id=eur.id,
            )

    run_async(_run())


def test_accrue_interest_increases_remaining(container) -> None:
    async def _run() -> None:
        past = datetime.now(timezone.utc) - timedelta(days=40)
        debt = await container.create_debt.execute(
            make_debt(amount="1200", interest_rate=Decimal("12")).model_copy(
                update={"started_at": past}
            )
        )
        debt = await container.update_debt.execute(
            debt.model_copy(
                update={
                    "accrue_interest": True,
                    "interest_rate": Decimal("12"),
                    "last_interest_accrued_at": past,
                }
            )
        )
        before = debt.remaining_amount
        changed = await container.accrue_debt_interest.execute()
        assert any(d.id == debt.id for d in changed)
        refreshed = await container.debt_repository.get_by_id(debt.id)
        assert refreshed is not None
        assert refreshed.remaining_amount > before
        assert refreshed.accrued_interest > 0

    run_async(_run())


def test_undo_last_debt_payment(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        debt = await container.create_debt.execute(
            make_debt(amount="200"), account_id=acc.id
        )
        await container.repay_debt.execute(debt.id, Decimal("50"), account_id=acc.id)
        mid = await container.debt_repository.get_by_id(debt.id)
        assert mid is not None
        assert mid.remaining_amount == Decimal("150.00")
        assert await container.undo_last_debt_payment.execute(debt.id) is True
        back = await container.debt_repository.get_by_id(debt.id)
        assert back is not None
        assert back.remaining_amount == Decimal("200.00")

    run_async(_run())


def test_update_debt_currency_converts_remaining(container) -> None:
    async def _run() -> None:
        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="USD",
                quote="RUB",
                rate=Decimal("100"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        debt = await container.create_debt.execute(
            make_debt(amount="1000", currency="RUB")
        )
        updated = await container.update_debt.execute(
            debt.model_copy(
                update={
                    "currency": "USD",
                    "amount": Decimal("1000"),
                    "remaining_amount": Decimal("1000"),
                }
            )
        )
        assert updated.currency == "USD"
        assert updated.remaining_amount == Decimal("10.00")

    run_async(_run())


def test_forgive_debt_closes_without_payment(container) -> None:
    async def _run() -> None:
        debt = await container.create_debt.execute(make_debt(amount="100"))
        forgiven = await container.forgive_debt.execute(debt.id)
        assert forgiven.remaining_amount == Decimal("0.00")
        assert forgiven.accrued_interest == Decimal("0.00")
        assert forgiven.status == DebtStatus.PAID
        assert forgiven.forgiven_early is True

    run_async(_run())


def test_duplicate_debt_resets_balance(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        debt = await container.create_debt.execute(
            make_debt(amount="200"), account_id=acc.id
        )
        await container.repay_debt.execute(debt.id, Decimal("50"), account_id=acc.id)
        copy = await container.duplicate_debt.execute(debt.id)
        assert copy.id != debt.id
        assert copy.remaining_amount == copy.amount
        assert copy.status == DebtStatus.ACTIVE

    run_async(_run())


def test_add_transaction_to_paid_debt_fails(container) -> None:
    async def _run() -> None:
        from tests.factories import make_transaction

        acc = await container.create_account.execute(make_account(balance="1000"))
        debt = await container.create_debt.execute(
            make_debt(amount="50"), account_id=acc.id
        )
        await container.repay_debt.execute(debt.id, Decimal("50"), account_id=acc.id)
        with pytest.raises(ValueError, match="already paid"):
            await container.add_transaction.execute(
                make_transaction(
                    acc.id,
                    amount="10",
                    category="Долг",
                    tx_type=TransactionType.EXPENSE,
                    debt_id=debt.id,
                )
            )

    run_async(_run())


def test_next_payment_marks_overdue(container) -> None:
    async def _run() -> None:
        past = datetime.now(timezone.utc) - timedelta(days=2)
        debt = await container.create_debt.execute(make_debt(amount="100"))
        updated = await container.update_debt.execute(
            debt.model_copy(update={"next_payment_date": past, "due_date": None})
        )
        assert updated.status == DebtStatus.OVERDUE
        # Scheduler path still flips ACTIVE → OVERDUE for next-payment dates.
        active = await container.create_debt.execute(
            make_debt(amount="50", counterparty="B")
        )
        # Bypass resolve by writing ACTIVE + past next payment through repo.
        raw = active.model_copy(
            update={
                "next_payment_date": past,
                "due_date": None,
                "status": DebtStatus.ACTIVE,
            }
        )
        await container.debt_repository.update(raw)
        changed = await container.mark_overdue_debts.execute()
        assert any(d.id == active.id for d in changed)

    run_async(_run())


def test_delete_debt_with_repayments_blocked(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        debt = await container.create_debt.execute(
            make_debt(amount="200"), account_id=acc.id
        )
        await container.repay_debt.execute(debt.id, Decimal("50"), account_id=acc.id)
        with pytest.raises(ValueError, match="repayments"):
            await container.delete_debt.execute(debt.id)

    run_async(_run())


def test_archive_unpaid_debt_blocked(container) -> None:
    async def _run() -> None:
        debt = await container.create_debt.execute(make_debt(amount="100"))
        with pytest.raises(ValueError, match="fully paid"):
            await container.update_debt.execute(
                debt.model_copy(update={"status": DebtStatus.ARCHIVED})
            )

    run_async(_run())


def test_delete_payment_restores_accrued_interest(container) -> None:
    async def _run() -> None:
        past = datetime.now(timezone.utc) - timedelta(days=40)
        acc = await container.create_account.execute(make_account(balance="10000"))
        debt = await container.create_debt.execute(
            make_debt(amount="1200", interest_rate=Decimal("12")).model_copy(
                update={"started_at": past}
            )
        )
        debt = await container.update_debt.execute(
            debt.model_copy(
                update={
                    "accrue_interest": True,
                    "last_interest_accrued_at": past,
                }
            )
        )
        await container.accrue_debt_interest.execute()
        before_pay = await container.debt_repository.get_by_id(debt.id)
        assert before_pay is not None
        accrued_before = before_pay.accrued_interest
        assert accrued_before > 0
        await container.repay_debt.execute(
            debt.id, Decimal("200"), account_id=acc.id
        )
        after_pay = await container.debt_repository.get_by_id(debt.id)
        assert after_pay is not None
        assert after_pay.accrued_interest < accrued_before
        txs = await container.list_transactions.execute(debt_id=debt.id)
        payment = next(
            t for t in txs if "debt_principal" not in (t.tags or [])
        )
        await container.delete_transaction.execute(payment.id)
        restored = await container.debt_repository.get_by_id(debt.id)
        assert restored is not None
        assert restored.accrued_interest == accrued_before

    run_async(_run())


def test_manual_debt_payment_sets_fx_credit(container) -> None:
    async def _run() -> None:
        from tests.factories import make_transaction

        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="USD",
                quote="RUB",
                rate=Decimal("100"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        usd = await container.create_account.execute(
            make_account(name="USD", currency="USD", balance="50")
        )
        debt = await container.create_debt.execute(
            make_debt(amount="500", currency="RUB", direction=DebtDirection.I_OWE)
        )
        tx = await container.add_transaction.execute(
            make_transaction(
                usd.id,
                amount="5",
                category="Долг",
                tx_type=TransactionType.EXPENSE,
                debt_id=debt.id,
                currency="USD",
            )
        )
        assert tx.debt_credit_amount == Decimal("500.00")
        refreshed = await container.debt_repository.get_by_id(debt.id)
        assert refreshed is not None
        assert refreshed.remaining_amount == Decimal("0.00")

    run_async(_run())
