"""Monthly category budgets: repository, use cases, transaction hooks."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from lib.domain.entities.category import CategoryKind
from lib.domain.entities.transaction import TransactionType
from lib.infrastructure.services.notification_service import NotificationKind
from tests.conftest import run_async
from tests.factories import make_account, make_category, make_debt, make_transaction


def test_set_and_list_budget(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        budget = await container.set_budget.execute(
            "Food", 8, 2026, Decimal("300")
        )
        assert budget.amount_limit == Decimal("300.00")
        assert budget.spent == Decimal("0.00")

        again = await container.set_budget.execute(
            "Food", 8, 2026, Decimal("400")
        )
        assert again.id == budget.id
        assert again.amount_limit == Decimal("400.00")

        listed = await container.get_budgets_for_month.execute(8, 2026)
        assert len(listed) == 1
        assert listed[0].limit == Decimal("400.00")

        progress = await container.get_budget_progress.execute(budget_id=budget.id)
        assert progress.category_id == "Food"

        assert await container.delete_budget.execute(budget.id) is True
        assert await container.get_budgets_for_month.execute(8, 2026) == []

    run_async(_run())


def test_corporate_budget_isolated_from_personal(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Office", kind=CategoryKind.EXPENSE)
        )
        personal = await container.create_account.execute(make_account(name="Cash"))
        corporate = await container.create_account.execute(
            make_account(name="LLC").model_copy(update={"is_corporate": True})
        )
        now = datetime.now(timezone.utc)
        personal_b = await container.set_budget.execute(
            "Office", now.month, now.year, Decimal("100")
        )
        corp_b = await container.set_budget.execute(
            "Office",
            now.month,
            now.year,
            Decimal("500"),
            account_id=corporate.id,
        )
        assert personal_b.account_id is None
        assert corp_b.account_id == corporate.id
        assert personal_b.id != corp_b.id

        await container.add_transaction.execute(
            make_transaction(corporate.id, amount="50", category="Office")
        )
        await container.add_transaction.execute(
            make_transaction(personal.id, amount="20", category="Office")
        )

        personal_p = await container.get_budget_progress.execute(
            category_id="Office", month=now.month, year=now.year
        )
        corp_p = await container.get_budget_progress.execute(
            category_id="Office",
            month=now.month,
            year=now.year,
            account_id=corporate.id,
        )
        assert personal_p.spent == Decimal("20.00")
        assert corp_p.spent == Decimal("50.00")

        personal_list = await container.get_budgets_for_month.execute(
            now.month, now.year
        )
        corp_list = await container.get_budgets_for_month.execute(
            now.month, now.year, account_id=corporate.id
        )
        assert all(p.budget.account_id is None for p in personal_list)
        assert all(p.budget.account_id == corporate.id for p in corp_list)

    run_async(_run())


def test_income_category_cannot_have_budget(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Salary", kind=CategoryKind.INCOME)
        )
        with pytest.raises(ValueError, match="expense"):
            await container.set_budget.execute("Salary", 8, 2026, Decimal("100"))

    run_async(_run())


def test_transaction_updates_spent_and_alerts(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account(balance="5000"))
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Food", now.month, now.year, Decimal("100"))

        tx = await container.add_transaction.execute(
            make_transaction(acc.id, amount="80", category="Food")
        )
        progress = await container.get_budget_progress.execute(
            category_id="Food", month=now.month, year=now.year
        )
        assert progress.spent == Decimal("80.00")
        assert progress.percent == Decimal("80.00")
        pending = container.notification_service.list_pending()
        assert any(m.kind is NotificationKind.BUDGET_WARNING for m in pending)

        await container.update_transaction.execute(
            tx.model_copy(update={"amount": Decimal("120")})
        )
        progress = await container.get_budget_progress.execute(
            category_id="Food", month=now.month, year=now.year
        )
        assert progress.spent == Decimal("120.00")
        assert progress.is_over_budget is True
        pending = container.notification_service.list_pending()
        assert any(m.kind is NotificationKind.BUDGET_OVER for m in pending)

        await container.delete_transaction.execute(tx.id)
        progress = await container.get_budget_progress.execute(
            category_id="Food", month=now.month, year=now.year
        )
        assert progress.spent == Decimal("0.00")

    run_async(_run())


def test_income_transaction_does_not_change_spent(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Both", kind=CategoryKind.BOTH)
        )
        acc = await container.create_account.execute(make_account())
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Both", now.month, now.year, Decimal("50"))
        await container.add_transaction.execute(
            make_transaction(
                acc.id,
                amount="40",
                category="Both",
                tx_type=TransactionType.INCOME,
            )
        )
        progress = await container.get_budget_progress.execute(
            category_id="Both", month=now.month, year=now.year
        )
        assert progress.spent == Decimal("0.00")

    run_async(_run())


def test_recalculate_spent(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account())
        now = datetime.now(timezone.utc)
        budget = await container.set_budget.execute(
            "Food", now.month, now.year, Decimal("200")
        )
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="30", category="Food")
        )
        await container.budget_repository.update_spent(budget.id, Decimal("999"))
        updated = await container.recalculate_budget_spent.execute(
            month=now.month, year=now.year
        )
        assert updated[0].spent == Decimal("30.00")

    run_async(_run())


def test_budget_alerts_respect_settings(container) -> None:
    async def _run() -> None:
        settings = await container.get_settings.execute()
        await container.update_settings.execute(
            settings.model_copy(update={"budget_alerts": False})
        )
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account())
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Food", now.month, now.year, Decimal("10"))
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="10", category="Food")
        )
        kinds = {m.kind for m in container.notification_service.list_pending()}
        assert NotificationKind.BUDGET_OVER not in kinds
        assert NotificationKind.BUDGET_WARNING not in kinds

    run_async(_run())


def test_delete_category_removes_budgets(container) -> None:
    async def _run() -> None:
        cat = await container.create_category.execute(
            make_category(name="Snacks", kind=CategoryKind.EXPENSE)
        )
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Snacks", now.month, now.year, Decimal("20"))
        assert await container.delete_category.execute(cat.id) is True
        listed = await container.get_budgets_for_month.execute(now.month, now.year)
        assert listed == []

    run_async(_run())


def test_budget_spent_converts_to_base_currency(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.currency import ExchangeRate

        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="USD",
                quote="RUB",
                rate=Decimal("100"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        settings = await container.get_settings.execute()
        settings.default_currency = "RUB"
        await container.update_settings.execute(settings)
        # Anchor RUB as first account so USD create does not steal default_currency.
        await container.create_account.execute(make_account(name="Cash"))

        await container.create_category.execute(
            make_category(name="Travel", kind=CategoryKind.EXPENSE)
        )
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Travel", now.month, now.year, Decimal("1000"))
        usd = await container.create_account.execute(
            make_account(name="USD", currency="USD", balance="50")
        )
        await container.add_transaction.execute(
            make_transaction(
                usd.id,
                amount="5",
                category="Travel",
                currency="USD",
                tx_type=TransactionType.EXPENSE,
            )
        )
        progress = await container.get_budgets_for_month.execute(now.month, now.year)
        assert progress[0].spent == Decimal("500.00")

    run_async(_run())


def test_copy_budgets_from_previous_month(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        await container.set_budget.execute("Food", 7, 2026, Decimal("300"))
        created = await container.copy_budgets_from_previous.execute(8, 2026)
        assert created == 1
        listed = await container.get_budgets_for_month.execute(8, 2026)
        assert len(listed) == 1
        assert listed[0].limit == Decimal("300.00")
        assert listed[0].category_id == "Food"
        again = await container.copy_budgets_from_previous.execute(8, 2026)
        assert again == 0
        with pytest.raises(ValueError, match="previous month"):
            await container.copy_budgets_from_previous.execute(1, 2026)

    run_async(_run())


def test_copy_corporate_budgets_from_previous_month(container) -> None:
    async def _run() -> None:
        corp = await container.create_account.execute(
            make_account(name="Corp", is_corporate=True)
        )
        await container.create_category.execute(
            make_category(name="Office", kind=CategoryKind.EXPENSE)
        )
        await container.set_budget.execute(
            "Office", 7, 2026, Decimal("500"), account_id=corp.id
        )
        # Personal budget with same category must not be copied into corporate scope.
        await container.set_budget.execute("Office", 7, 2026, Decimal("100"))
        created = await container.copy_budgets_from_previous.execute(
            8, 2026, account_id=corp.id
        )
        assert created == 1
        listed = await container.get_budgets_for_month.execute(
            8, 2026, account_id=corp.id
        )
        assert len(listed) == 1
        assert listed[0].limit == Decimal("500.00")
        assert listed[0].budget.account_id == corp.id
        personal = await container.get_budgets_for_month.execute(8, 2026)
        assert all(p.budget.account_id in (None, "") for p in personal)

    run_async(_run())


def test_budget_half_alert(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account(balance="5000"))
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Food", now.month, now.year, Decimal("100"))
        settings = await container.get_settings.execute()
        await container.update_settings.execute(
            settings.model_copy(update={"budget_warn_pct": 50})
        )
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="50", category="Food")
        )
        progress = await container.get_budget_progress.execute(
            category_id="Food", month=now.month, year=now.year
        )
        assert progress.percent == Decimal("50.00")
        assert progress.budget.last_alert_level == 50
        pending = container.notification_service.list_pending()
        assert any(m.kind is NotificationKind.BUDGET_HALF for m in pending)

    run_async(_run())


def test_suggest_budget_limit_averages_previous_months(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account(balance="5000"))
        amounts = {
            5: Decimal("30"),
            6: Decimal("60"),
            7: Decimal("90"),
        }
        for month, amount in amounts.items():
            tx = make_transaction(acc.id, amount=str(amount), category="Food")
            tx = tx.model_copy(
                update={"date": datetime(2026, month, 10, tzinfo=timezone.utc)}
            )
            await container.add_transaction.execute(tx)
        avg = await container.suggest_budget_limit.execute("Food", 8, 2026)
        assert avg == Decimal("60.00")

    run_async(_run())


def test_get_budget_analytics(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        await container.create_category.execute(
            make_category(name="Transport", kind=CategoryKind.EXPENSE)
        )
        await container.set_budget.execute("Food", 8, 2026, Decimal("100"))
        await container.set_budget.execute("Transport", 8, 2026, Decimal("50"))
        snapshot = await container.get_budget_analytics.execute(
            8, 2026, now=datetime(2026, 8, 15, tzinfo=timezone.utc)
        )
        assert snapshot.count == 2
        assert snapshot.total_limit == Decimal("150.00")
        assert snapshot.total_spent == Decimal("0.00")
        assert snapshot.remaining == Decimal("150.00")
        assert any(row["month"] == "2026-08" for row in snapshot.monthly_trend)

    run_async(_run())


def test_suggest_subscription_budgets(container) -> None:
    async def _run() -> None:
        from tests.factories import make_subscription

        acc = await container.create_account.execute(make_account(balance="5000"))
        await container.create_subscription.execute(
            make_subscription(acc.id, name="Netflix", amount="15")
        )
        hints = await container.suggest_subscription_budgets.execute(8, 2026)
        names = {h.name for h in hints}
        assert "Netflix" in names
        netflix = next(h for h in hints if h.name == "Netflix")
        assert netflix.monthly == Decimal("15.00")
        assert netflix.has_budget is False

    run_async(_run())


def test_recalculate_missing_fx_raises(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Travel", kind=CategoryKind.EXPENSE)
        )
        now = datetime.now(timezone.utc)
        await container.set_budget.execute(
            "Travel", now.month, now.year, Decimal("1000")
        )
        # Keep display currency RUB so a USD expense needs a rate.
        await container.create_account.execute(make_account(name="Cash"))
        usd = await container.create_account.execute(
            make_account(name="USD", currency="USD", balance="50")
        )
        with pytest.raises(ValueError, match="No exchange rate"):
            await container.add_transaction.execute(
                make_transaction(
                    usd.id,
                    amount="5",
                    category="Travel",
                    currency="USD",
                    tx_type=TransactionType.EXPENSE,
                )
            )

    run_async(_run())


def test_debt_payment_does_not_hit_category_budget(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Долг", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account(balance="1000"))
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Долг", now.month, now.year, Decimal("500"))
        debt = await container.create_debt.execute(
            make_debt(amount="80"), account_id=acc.id
        )
        await container.repay_debt.execute(debt.id, Decimal("40"), account_id=acc.id)
        progress = await container.get_budget_progress.execute(
            category_id="Долг", month=now.month, year=now.year
        )
        assert progress is not None
        assert progress.spent == Decimal("0.00")

    run_async(_run())


def test_budget_matches_category_case_insensitively(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account())
        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Food", now.month, now.year, Decimal("100"))
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="25", category="FOOD")
        )
        progress = await container.get_budget_progress.execute(
            category_id="Food", month=now.month, year=now.year
        )
        assert progress is not None
        assert progress.spent == Decimal("25.00")

    run_async(_run())
