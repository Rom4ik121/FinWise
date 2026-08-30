"""Goals CRUD, FX contributions, projection, and archival."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from lib.domain.entities.currency import ExchangeRate
from lib.domain.entities.goal import GoalStatus
from tests.conftest import run_async
from tests.factories import make_account, make_goal


def test_goal_crud(container) -> None:
    async def _run() -> None:
        goal = await container.create_goal.execute(make_goal(name="Laptop"))
        listed = await container.list_goals.execute()
        assert any(g.id == goal.id for g in listed)

        updated = await container.update_goal.execute(
            goal.model_copy(update={"name": "Laptop Pro", "target_amount": Decimal("900")})
        )
        assert updated.name == "Laptop Pro"
        assert updated.target_amount == Decimal("900.00")
        assert updated.status == GoalStatus.ACTIVE

        assert await container.delete_goal.execute(goal.id) is True

    run_async(_run())


def test_contribute_to_completed_goal_fails(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        goal = await container.create_goal.execute(make_goal(target="100"))
        await container.contribute_to_goal.execute(
            goal.id, Decimal("100"), account_id=acc.id
        )
        with pytest.raises(ValueError, match="already completed"):
            await container.contribute_to_goal.execute(
                goal.id, Decimal("10"), account_id=acc.id
            )

    run_async(_run())


def test_contribute_completes_goal(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        goal = await container.create_goal.execute(make_goal(target="200"))
        updated = await container.contribute_to_goal.execute(
            goal.id, Decimal("200"), account_id=acc.id
        )
        assert updated.is_completed is True
        assert updated.status == GoalStatus.COMPLETED
        assert updated.current_amount == Decimal("200.00")

    run_async(_run())


def test_contribute_converts_foreign_currency(container) -> None:
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
            make_account(name="USD Cash", currency="USD", balance="50")
        )
        goal = await container.create_goal.execute(
            make_goal(target="500", currency="RUB")
        )
        updated = await container.contribute_to_goal.execute(
            goal.id, Decimal("5"), account_id=usd.id
        )
        assert updated.current_amount == Decimal("500.00")
        assert updated.status == GoalStatus.COMPLETED
        txs = await container.list_transactions.execute(goal_id=goal.id)
        assert len(txs) == 1
        assert txs[0].amount == Decimal("5.00")
        assert txs[0].currency == "USD"
        assert txs[0].goal_credit_amount == Decimal("500.00")

    run_async(_run())


def test_contribute_blocks_missing_rate(container) -> None:
    async def _run() -> None:
        eur = await container.create_account.execute(
            make_account(name="EUR", currency="EUR", balance="100")
        )
        goal = await container.create_goal.execute(
            make_goal(target="100", currency="RUB")
        )
        with pytest.raises(ValueError, match="No exchange rate"):
            await container.contribute_to_goal.execute(
                goal.id, Decimal("10"), account_id=eur.id
            )

    run_async(_run())


def test_archive_and_duplicate_goal(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        goal = await container.create_goal.execute(make_goal(target="100"))
        await container.contribute_to_goal.execute(
            goal.id, Decimal("100"), account_id=acc.id
        )
        archived = await container.archive_goal.execute(goal.id)
        assert archived.status == GoalStatus.ARCHIVED

        active = await container.list_goals.execute(status=GoalStatus.ACTIVE)
        assert all(g.id != goal.id for g in active)

        archived_list = await container.list_goals.execute(status=GoalStatus.ARCHIVED)
        assert any(g.id == goal.id for g in archived_list)

        copy = await container.duplicate_goal.execute(goal.id, name_suffix=" (copy)")
        assert copy.id != goal.id
        assert copy.current_amount == Decimal("0.00")
        assert copy.status == GoalStatus.ACTIVE
        assert copy.name.endswith("(copy)")

    run_async(_run())


def test_goal_projection_and_delete_contribution(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="5000"))
        deadline = datetime.now(timezone.utc) + timedelta(days=60)
        goal = await container.create_goal.execute(
            make_goal(target="600").model_copy(update={"deadline": deadline})
        )
        await container.contribute_to_goal.execute(
            goal.id, Decimal("100"), account_id=acc.id
        )
        projection = await container.get_goal_projection.execute(goal.id)
        assert projection.remaining_amount == Decimal("500.00")
        assert projection.required_monthly_contribution is not None
        assert projection.required_monthly_contribution > 0

        txs = await container.list_transactions.execute(goal_id=goal.id)
        assert len(txs) == 1
        deleted = await container.delete_goal_contribution.execute(
            txs[0].id, goal_id=goal.id
        )
        assert deleted is True
        refreshed = await container.goal_repository.get_by_id(goal.id)
        assert refreshed is not None
        assert refreshed.current_amount == Decimal("0.00")
        assert refreshed.status == GoalStatus.ACTIVE

    run_async(_run())


def test_add_transaction_fills_goal_credit_fx(container) -> None:
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
        goal = await container.create_goal.execute(
            make_goal(target="1000", currency="RUB")
        )
        from tests.factories import make_transaction

        tx = await container.add_transaction.execute(
            make_transaction(
                usd.id,
                amount="5",
                currency="USD",
                category="Сбережения",
                goal_id=goal.id,
            )
        )
        assert tx.goal_credit_amount == Decimal("500.00")
        refreshed = await container.goal_repository.get_by_id(goal.id)
        assert refreshed is not None
        assert refreshed.current_amount == Decimal("500.00")

    run_async(_run())


def test_update_goal_currency_converts_progress(container) -> None:
    async def _run() -> None:
        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="USD",
                quote="RUB",
                rate=Decimal("100"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        acc = await container.create_account.execute(make_account(balance="1000"))
        goal = await container.create_goal.execute(
            make_goal(target="1000", currency="RUB")
        )
        await container.contribute_to_goal.execute(
            goal.id, Decimal("500"), account_id=acc.id
        )
        updated = await container.update_goal.execute(
            goal.model_copy(
                update={
                    "currency": "USD",
                    "target_amount": Decimal("20"),
                    "current_amount": Decimal("500"),
                }
            )
        )
        assert updated.currency == "USD"
        assert updated.current_amount == Decimal("5.00")

    run_async(_run())


def test_delete_goal_unlinks_contributions(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        goal = await container.create_goal.execute(make_goal(target="200"))
        await container.contribute_to_goal.execute(
            goal.id, Decimal("50"), account_id=acc.id
        )
        txs = await container.list_transactions.execute(goal_id=goal.id)
        assert len(txs) == 1
        tx_id = txs[0].id
        assert await container.delete_goal.execute(goal.id) is True
        leftover = await container.transaction_repository.get_by_id(tx_id)
        assert leftover is not None
        assert leftover.goal_id is None
        # Credit kept so budget recalculate never treats savings as spend.
        assert leftover.goal_credit_amount == Decimal("50.00")
        bal = await container.account_repository.get_by_id(acc.id)
        assert bal is not None
        assert bal.balance == Decimal("950.00")

    run_async(_run())


def test_goal_contribution_skips_budget_spent(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.category import CategoryKind
        from tests.factories import make_category, make_transaction

        cat = "Накопление"
        await container.create_category.execute(
            make_category(name=cat, kind=CategoryKind.EXPENSE)
        )
        now = datetime.now(timezone.utc)
        await container.set_budget.execute(cat, now.month, now.year, Decimal("500"))
        acc = await container.create_account.execute(make_account(balance="1000"))
        goal = await container.create_goal.execute(make_goal(target="200"))
        await container.contribute_to_goal.execute(
            goal.id, Decimal("80"), account_id=acc.id
        )
        progress = await container.get_budget_progress.execute(
            category_id=cat, month=now.month, year=now.year
        )
        assert progress.spent == Decimal("0.00")

        # Same category without goal_id still hits the budget.
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="40", category=cat)
        )
        progress2 = await container.get_budget_progress.execute(
            category_id=cat, month=now.month, year=now.year
        )
        assert progress2.spent == Decimal("40.00")

    run_async(_run())
