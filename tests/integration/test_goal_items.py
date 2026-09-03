"""Goal sub-items, close item, and early close."""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib.domain.entities.goal import GoalStatus
from tests.conftest import run_async
from tests.factories import make_account, make_goal


def test_goal_items_contribute_close_and_early(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.goal import GoalItem
        from uuid import uuid4

        acc = await container.create_account.execute(make_account(balance="2000"))
        item_a = GoalItem(id=str(uuid4()), name="Phone", target_amount=Decimal("600"))
        item_b = GoalItem(id=str(uuid4()), name="Case", target_amount=Decimal("100"))
        goal = await container.create_goal.execute(
            make_goal(name="Gadgets", target="700").model_copy(
                update={"items": [item_a, item_b]}
            )
        )
        assert goal.target_amount == Decimal("700.00")
        assert len(goal.items) == 2

        updated = await container.contribute_to_goal.execute(
            goal.id,
            Decimal("300"),
            account_id=acc.id,
            item_id=item_a.id,
        )
        assert updated.current_amount == Decimal("300.00")
        phone = next(i for i in updated.items if i.id == item_a.id)
        assert phone.current_amount == Decimal("300.00")
        assert len(updated.items) == 2

        closed = await container.close_goal_item.execute(goal.id, item_b.id)
        assert any(i.is_closed for i in closed.items if i.id == item_b.id)
        assert closed.status == GoalStatus.ACTIVE

        await container.contribute_to_goal.execute(
            goal.id,
            Decimal("300"),
            account_id=acc.id,
            item_id=item_a.id,
        )
        all_closed = await container.close_goal_item.execute(goal.id, item_a.id)
        assert all_closed.status == GoalStatus.COMPLETED

        fresh_goal = await container.create_goal.execute(make_goal(target="500"))
        archived = await container.close_goal_early.execute(fresh_goal.id)
        assert archived.status == GoalStatus.ARCHIVED
        assert archived.closed_early is True

    run_async(_run())


def test_contribute_to_goal_with_items_requires_item_id(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.goal import GoalItem
        from uuid import uuid4

        acc = await container.create_account.execute(make_account(balance="1000"))
        item = GoalItem(id=str(uuid4()), name="Part", target_amount=Decimal("200"))
        goal = await container.create_goal.execute(
            make_goal(target="200").model_copy(update={"items": [item]})
        )
        with pytest.raises(ValueError, match="Goal item is required"):
            await container.contribute_to_goal.execute(
                goal.id, Decimal("50"), account_id=acc.id
            )

    run_async(_run())


def test_withdraw_from_goal_with_items_requires_item_id(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.goal import GoalItem
        from uuid import uuid4

        acc = await container.create_account.execute(make_account(balance="1000"))
        item = GoalItem(id=str(uuid4()), name="Part", target_amount=Decimal("200"))
        goal = await container.create_goal.execute(
            make_goal(target="200").model_copy(update={"items": [item]})
        )
        await container.contribute_to_goal.execute(
            goal.id, Decimal("100"), account_id=acc.id, item_id=item.id
        )
        with pytest.raises(ValueError, match="Goal item is required"):
            await container.withdraw_from_goal.execute(
                goal.id, Decimal("50"), account_id=acc.id
            )

    run_async(_run())


def test_withdraw_from_goal_item_balance(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.goal import GoalItem
        from uuid import uuid4

        acc = await container.create_account.execute(make_account(balance="1000"))
        item = GoalItem(id=str(uuid4()), name="Part", target_amount=Decimal("200"))
        goal = await container.create_goal.execute(
            make_goal(target="200").model_copy(update={"items": [item]})
        )
        await container.contribute_to_goal.execute(
            goal.id, Decimal("50"), account_id=acc.id, item_id=item.id
        )
        with pytest.raises(ValueError, match="Withdrawal exceeds item balance"):
            await container.withdraw_from_goal.execute(
                goal.id, Decimal("100"), account_id=acc.id, item_id=item.id
            )
        updated = await container.withdraw_from_goal.execute(
            goal.id, Decimal("30"), account_id=acc.id, item_id=item.id
        )
        part = next(i for i in updated.items if i.id == item.id)
        assert part.current_amount == Decimal("20.00")
        assert updated.current_amount == Decimal("20.00")

    run_async(_run())
