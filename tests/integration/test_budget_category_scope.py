"""Budget category rename/delete stays within account scope."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lib.domain.entities.budget import Budget
from lib.domain.entities.category import CategoryKind
from tests.conftest import run_async
from tests.factories import make_category


def test_category_rename_does_not_touch_other_account_budgets(container) -> None:
    async def _run() -> None:
        now = datetime.now(timezone.utc)
        await container.budget_repository.save(
            Budget(
                category_id="Food",
                month=now.month,
                year=now.year,
                amount_limit=Decimal("100"),
                account_id=None,
            )
        )
        await container.budget_repository.save(
            Budget(
                category_id="Food",
                month=now.month,
                year=now.year,
                amount_limit=Decimal("200"),
                account_id="corp-1",
            )
        )
        cat = await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE, account_id="corp-1")
        )
        await container.update_category.execute(
            cat.model_copy(update={"name": "Meals"})
        )
        still_personal = await container.budget_repository.get_by_category_and_month(
            "Food", now.month, now.year, account_id=None
        )
        moved_corp = await container.budget_repository.get_by_category_and_month(
            "Meals", now.month, now.year, account_id="corp-1"
        )
        assert still_personal is not None
        assert still_personal.category_id == "Food"
        assert moved_corp is not None
        assert moved_corp.category_id == "Meals"

    run_async(_run())


def test_category_delete_scoped_to_account_budgets(container) -> None:
    async def _run() -> None:
        now = datetime.now(timezone.utc)
        await container.budget_repository.save(
            Budget(
                category_id="Taxi",
                month=now.month,
                year=now.year,
                amount_limit=Decimal("50"),
                account_id=None,
            )
        )
        await container.budget_repository.save(
            Budget(
                category_id="Taxi",
                month=now.month,
                year=now.year,
                amount_limit=Decimal("80"),
                account_id="corp-2",
            )
        )
        cat = await container.create_category.execute(
            make_category(name="Taxi", kind=CategoryKind.EXPENSE, account_id="corp-2")
        )
        await container.delete_category.execute(cat.id)
        still_personal = await container.budget_repository.get_by_category_and_month(
            "Taxi", now.month, now.year, account_id=None
        )
        gone_corp = await container.budget_repository.get_by_category_and_month(
            "Taxi", now.month, now.year, account_id="corp-2"
        )
        assert still_personal is not None
        assert gone_corp is None

    run_async(_run())
