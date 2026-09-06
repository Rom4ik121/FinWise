"""Forward spillover of excess goal-item contributions."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from lib.domain.entities.goal import Goal, GoalItem
from lib.domain.use_cases.goals import allocate_goal_contribution_credit


def test_spillover_goes_to_next_open_item() -> None:
    a, b, c = str(uuid4()), str(uuid4()), str(uuid4())
    goal = Goal(
        name="Kit",
        target_amount=Decimal("300"),
        current_amount=Decimal("0"),
        currency="RUB",
        items=[
            GoalItem(
                id=a, name="A", target_amount=Decimal("100"), sort_order=0
            ),
            GoalItem(
                id=b, name="B", target_amount=Decimal("100"), sort_order=1
            ),
            GoalItem(
                id=c, name="C", target_amount=Decimal("100"), sort_order=2
            ),
        ],
    )
    # Overfund A by 150 → fill A (100) then B (100) then C (50).
    updated, alloc = allocate_goal_contribution_credit(
        goal, Decimal("250"), item_id=a
    )
    assert next(i for i in updated.items if i.id == a).current_amount == Decimal(
        "100.00"
    )
    assert next(i for i in updated.items if i.id == b).current_amount == Decimal(
        "100.00"
    )
    assert next(i for i in updated.items if i.id == c).current_amount == Decimal(
        "50.00"
    )
    assert alloc[a] == Decimal("100.00")
    assert alloc[b] == Decimal("100.00")
    assert alloc[c] == Decimal("50.00")


def test_spillover_from_middle_item_wraps_forward() -> None:
    a, b, c = str(uuid4()), str(uuid4()), str(uuid4())
    goal = Goal(
        name="Kit",
        target_amount=Decimal("300"),
        current_amount=Decimal("0"),
        currency="RUB",
        items=[
            GoalItem(
                id=a,
                name="A",
                target_amount=Decimal("100"),
                current_amount=Decimal("100"),
                sort_order=0,
            ),
            GoalItem(
                id=b, name="B", target_amount=Decimal("100"), sort_order=1
            ),
            GoalItem(
                id=c, name="C", target_amount=Decimal("100"), sort_order=2
            ),
        ],
    )
    # Contribute to B with 150 → B 100, then C 50 (not back to full A).
    updated, alloc = allocate_goal_contribution_credit(
        goal, Decimal("150"), item_id=b
    )
    assert next(i for i in updated.items if i.id == a).current_amount == Decimal(
        "100.00"
    )
    assert next(i for i in updated.items if i.id == b).current_amount == Decimal(
        "100.00"
    )
    assert next(i for i in updated.items if i.id == c).current_amount == Decimal(
        "50.00"
    )
    assert a not in alloc
    assert alloc[b] == Decimal("100.00")
    assert alloc[c] == Decimal("50.00")
