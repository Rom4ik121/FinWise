"""Budget recalculate parity with multi-line items and goal contributions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lib.domain.entities.category import CategoryKind
from lib.domain.entities.transaction import TransactionItem
from lib.domain.use_cases.budgets import _sum_expenses
from tests.conftest import run_async
from tests.factories import make_account, make_category, make_goal, make_transaction


def test_sum_expenses_respects_items_and_skips_goals(container) -> None:
    async def _run() -> None:
        now = datetime.now(timezone.utc)
        await container.create_category.execute(
            make_category(name="Еда", kind=CategoryKind.EXPENSE)
        )
        await container.create_category.execute(
            make_category(name="Транспорт", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account())
        tx = make_transaction(acc.id, amount="100", category="Еда").model_copy(
            update={
                "items": [
                    TransactionItem(name="A", amount=Decimal("40"), category="Еда"),
                    TransactionItem(
                        name="B", amount=Decimal("60"), category="Транспорт"
                    ),
                ],
                "date": now,
            }
        )
        await container.add_transaction.execute(tx)
        food = await _sum_expenses(
            container.transaction_repository,
            "Еда",
            now.month,
            now.year,
            currencies=container.currency_repository,
            settings=container.settings_repository,
        )
        transport = await _sum_expenses(
            container.transaction_repository,
            "Транспорт",
            now.month,
            now.year,
            currencies=container.currency_repository,
            settings=container.settings_repository,
        )
        assert food == Decimal("40.00")
        assert transport == Decimal("60.00")

        goal = await container.create_goal.execute(make_goal(target="1000"))
        await container.contribute_to_goal.execute(
            goal.id, Decimal("25"), account_id=acc.id
        )
        after = await _sum_expenses(
            container.transaction_repository,
            "Еда",
            now.month,
            now.year,
            currencies=container.currency_repository,
            settings=container.settings_repository,
        )
        assert after == Decimal("40.00")

    run_async(_run())
