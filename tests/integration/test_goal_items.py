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


def test_contribution_persists_goal_alloc_tags_and_exact_delete(container) -> None:
    """Interleaved item credits reverse exactly via stored goal_alloc tags."""

    async def _run() -> None:
        from lib.domain.entities.goal import GoalItem
        from lib.domain.use_cases.goals import (
            GOAL_ALLOC_TAG_PREFIX,
            parse_goal_allocation_tags,
        )
        from uuid import uuid4

        acc = await container.create_account.execute(make_account(balance="5000"))
        phone = GoalItem(
            id=str(uuid4()),
            name="Phone",
            target_amount=Decimal("600"),
            sort_order=0,
        )
        case = GoalItem(
            id=str(uuid4()),
            name="Case",
            target_amount=Decimal("100"),
            sort_order=1,
        )
        goal = await container.create_goal.execute(
            make_goal(name="Gadgets", target="700").model_copy(
                update={"items": [phone, case]}
            )
        )
        await container.contribute_to_goal.execute(
            goal.id,
            Decimal("50"),
            account_id=acc.id,
            item_id=case.id,
        )
        await container.contribute_to_goal.execute(
            goal.id,
            Decimal("650"),
            account_id=acc.id,
            item_id=phone.id,
        )
        txs = await container.list_transactions.execute(account_id=acc.id)
        phone_tx = next(
            t
            for t in txs
            if t.goal_id == goal.id and t.goal_item_id == phone.id
        )
        assert any(
            str(tag).startswith(GOAL_ALLOC_TAG_PREFIX) for tag in (phone_tx.tags or [])
        )
        alloc = parse_goal_allocation_tags(phone_tx.tags)
        assert alloc is not None
        assert alloc[phone.id] == Decimal("600.00")
        assert alloc[case.id] == Decimal("50.00")

        assert await container.delete_transaction.execute(phone_tx.id) is True
        after = await container.goal_repository.get_by_id(goal.id)
        assert after is not None
        phone_item = next(i for i in after.items if i.id == phone.id)
        case_item = next(i for i in after.items if i.id == case.id)
        assert phone_item.current_amount == Decimal("0.00")
        assert case_item.current_amount == Decimal("50.00")

    run_async(_run())


def test_delete_with_corrupt_goal_alloc_tags_preserves_sibling(container) -> None:
    """Corrupt goal_alloc markers reverse primary-only (no sibling wipe)."""

    async def _run() -> None:
        from lib.domain.entities.goal import GoalItem
        from uuid import uuid4

        acc = await container.create_account.execute(make_account(balance="5000"))
        phone = GoalItem(
            id=str(uuid4()),
            name="Phone",
            target_amount=Decimal("600"),
            sort_order=0,
        )
        case = GoalItem(
            id=str(uuid4()),
            name="Case",
            target_amount=Decimal("100"),
            sort_order=1,
        )
        goal = await container.create_goal.execute(
            make_goal(name="Gadgets", target="700").model_copy(
                update={"items": [phone, case]}
            )
        )
        await container.contribute_to_goal.execute(
            goal.id,
            Decimal("50"),
            account_id=acc.id,
            item_id=case.id,
        )
        await container.contribute_to_goal.execute(
            goal.id,
            Decimal("650"),
            account_id=acc.id,
            item_id=phone.id,
        )
        txs = await container.list_transactions.execute(account_id=acc.id)
        phone_tx = next(
            t
            for t in txs
            if t.goal_id == goal.id and t.goal_item_id == phone.id
        )
        # Simulate damaged tags while keeping markers.
        damaged = phone_tx.model_copy(
            update={"tags": ["goal_alloc:broken", "goal_alloc::x", "keep-me"]}
        )
        await container.transaction_repository.update(damaged)

        assert await container.delete_transaction.execute(phone_tx.id) is True
        after = await container.goal_repository.get_by_id(goal.id)
        assert after is not None
        phone_item = next(i for i in after.items if i.id == phone.id)
        case_item = next(i for i in after.items if i.id == case.id)
        assert phone_item.current_amount == Decimal("0.00")
        assert case_item.current_amount == Decimal("100.00")

    run_async(_run())


def test_goal_credit_rolls_back_when_tag_write_fails(container, monkeypatch) -> None:
    """If tag persistence fails mid-op, goal credit and ledger row roll back."""

    async def _run() -> None:
        from lib.domain.entities.goal import GoalItem
        from lib.domain.use_cases.goals import GOAL_ALLOC_TAG_PREFIX
        from uuid import uuid4

        acc = await container.create_account.execute(make_account(balance="5000"))
        phone = GoalItem(
            id=str(uuid4()),
            name="Phone",
            target_amount=Decimal("600"),
            sort_order=0,
        )
        case = GoalItem(
            id=str(uuid4()),
            name="Case",
            target_amount=Decimal("100"),
            sort_order=1,
        )
        goal = await container.create_goal.execute(
            make_goal(name="Gadgets", target="700").model_copy(
                update={"items": [phone, case]}
            )
        )
        balance_before = (await container.account_repository.get_by_id(acc.id)).balance
        real_update = container.transaction_repository.update

        async def _fail_on_alloc_tags(tx):
            if any(
                str(tag).startswith(GOAL_ALLOC_TAG_PREFIX) for tag in (tx.tags or [])
            ):
                raise RuntimeError("simulated tag write failure")
            return await real_update(tx)

        monkeypatch.setattr(container.transaction_repository, "update", _fail_on_alloc_tags)
        with pytest.raises(RuntimeError, match="simulated tag write failure"):
            await container.contribute_to_goal.execute(
                goal.id,
                Decimal("100"),
                account_id=acc.id,
                item_id=phone.id,
            )

        after_goal = await container.goal_repository.get_by_id(goal.id)
        assert after_goal is not None
        assert after_goal.current_amount == Decimal("0.00")
        phone_item = next(i for i in after_goal.items if i.id == phone.id)
        assert phone_item.current_amount == Decimal("0.00")

        after_acc = await container.account_repository.get_by_id(acc.id)
        assert after_acc is not None
        assert after_acc.balance == balance_before

        txs = await container.list_transactions.execute(account_id=acc.id)
        assert not any(t.goal_id == goal.id for t in txs)

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
