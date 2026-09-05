"""Unit tests for goal item contribution spillover reverse."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from lib.domain.entities.goal import Goal, GoalItem
from lib.domain.use_cases.goals import (
    allocate_goal_contribution_credit,
    apply_goal_contribution_credit,
    encode_goal_allocation_tags,
    parse_goal_allocation_tags,
    reverse_goal_contribution_credit,
)


def _goal_with_items() -> tuple[Goal, str, str]:
    a = str(uuid4())
    b = str(uuid4())
    goal = Goal(
        name="Gadgets",
        target_amount=Decimal("700.00"),
        current_amount=Decimal("0.00"),
        currency="UZS",
        items=[
            GoalItem(
                id=a,
                name="Phone",
                target_amount=Decimal("600.00"),
                current_amount=Decimal("0.00"),
                sort_order=0,
            ),
            GoalItem(
                id=b,
                name="Case",
                target_amount=Decimal("100.00"),
                current_amount=Decimal("0.00"),
                sort_order=1,
            ),
        ],
    )
    return goal, a, b


def test_reverse_undoes_sibling_spillover() -> None:
    goal, phone_id, case_id = _goal_with_items()
    # Fill phone to target, spill 50 onto case.
    credited = apply_goal_contribution_credit(
        goal, Decimal("650.00"), item_id=phone_id
    )
    phone = next(i for i in credited.items if i.id == phone_id)
    case = next(i for i in credited.items if i.id == case_id)
    assert phone.current_amount == Decimal("600.00")
    assert case.current_amount == Decimal("50.00")
    assert credited.current_amount == Decimal("650.00")

    reversed_goal = reverse_goal_contribution_credit(
        credited, Decimal("650.00"), item_id=phone_id
    )
    phone2 = next(i for i in reversed_goal.items if i.id == phone_id)
    case2 = next(i for i in reversed_goal.items if i.id == case_id)
    assert phone2.current_amount == Decimal("0.00")
    assert case2.current_amount == Decimal("0.00")
    assert reversed_goal.current_amount == Decimal("0.00")


def test_reverse_undoes_primary_overflow_dump() -> None:
    goal, phone_id, case_id = _goal_with_items()
    # Fill both items, dump remainder onto primary.
    credited = apply_goal_contribution_credit(
        goal, Decimal("800.00"), item_id=phone_id
    )
    phone = next(i for i in credited.items if i.id == phone_id)
    case = next(i for i in credited.items if i.id == case_id)
    assert case.current_amount == Decimal("100.00")
    assert phone.current_amount == Decimal("700.00")  # 600 + 100 overflow

    reversed_goal = reverse_goal_contribution_credit(
        credited, Decimal("800.00"), item_id=phone_id
    )
    phone2 = next(i for i in reversed_goal.items if i.id == phone_id)
    case2 = next(i for i in reversed_goal.items if i.id == case_id)
    assert phone2.current_amount == Decimal("0.00")
    assert case2.current_amount == Decimal("0.00")


def test_apply_spills_when_primary_already_at_target() -> None:
    goal, phone_id, case_id = _goal_with_items()
    filled, _ = allocate_goal_contribution_credit(
        goal, Decimal("600.00"), item_id=phone_id
    )
    phone = next(i for i in filled.items if i.id == phone_id)
    assert phone.current_amount == Decimal("600.00")

    # Primary has no room — must spill onto sibling, not dump onto primary.
    credited, allocations = allocate_goal_contribution_credit(
        filled, Decimal("40.00"), item_id=phone_id
    )
    phone2 = next(i for i in credited.items if i.id == phone_id)
    case2 = next(i for i in credited.items if i.id == case_id)
    assert phone2.current_amount == Decimal("600.00")
    assert case2.current_amount == Decimal("40.00")
    assert allocations.get(phone_id, Decimal("0")) == Decimal("0.00")
    assert allocations[case_id] == Decimal("40.00")


def test_reverse_partial_allocations_debits_leftover_on_primary_only() -> None:
    """Exact mode: partial tags debit listed items, leftover on primary — no LIFO wipe."""
    goal, phone_id, case_id = _goal_with_items()
    # Case owns 50 first, then phone spill fills case to 100.
    after_case, _ = allocate_goal_contribution_credit(
        goal, Decimal("50.00"), item_id=case_id
    )
    credited, full_alloc = allocate_goal_contribution_credit(
        after_case, Decimal("650.00"), item_id=phone_id
    )
    assert full_alloc[phone_id] == Decimal("600.00")
    assert full_alloc[case_id] == Decimal("50.00")
    case = next(i for i in credited.items if i.id == case_id)
    assert case.current_amount == Decimal("100.00")

    # Partial tags only list the spill onto case — leftover must hit primary only.
    partial = {case_id: Decimal("50.00")}
    reversed_goal = reverse_goal_contribution_credit(
        credited,
        Decimal("650.00"),
        item_id=phone_id,
        allocations=partial,
        allocation_mode="exact",
    )
    phone2 = next(i for i in reversed_goal.items if i.id == phone_id)
    case2 = next(i for i in reversed_goal.items if i.id == case_id)
    assert phone2.current_amount == Decimal("0.00")
    assert case2.current_amount == Decimal("50.00")  # case's own credit survives


def test_reverse_corrupt_markers_use_primary_only() -> None:
    """Corrupt goal_alloc markers must not LIFO-wipe sibling credits."""
    goal, phone_id, case_id = _goal_with_items()
    after_case, _ = allocate_goal_contribution_credit(
        goal, Decimal("50.00"), item_id=case_id
    )
    credited, _ = allocate_goal_contribution_credit(
        after_case, Decimal("650.00"), item_id=phone_id
    )
    reversed_goal = reverse_goal_contribution_credit(
        credited,
        Decimal("650.00"),
        item_id=phone_id,
        allocations=None,
        allocation_mode="primary_only",
    )
    phone2 = next(i for i in reversed_goal.items if i.id == phone_id)
    case2 = next(i for i in reversed_goal.items if i.id == case_id)
    assert phone2.current_amount == Decimal("0.00")
    assert case2.current_amount == Decimal("100.00")


def test_corrupt_alloc_tags_parse_as_none_but_markers_detected() -> None:
    from lib.domain.use_cases.goals import has_goal_allocation_tag_markers

    tags = [
        "goal_alloc:broken",
        "goal_alloc::10.00",
        "goal_alloc:abc:not-a-number",
        "user-tag",
    ]
    assert has_goal_allocation_tag_markers(tags) is True
    assert parse_goal_allocation_tags(tags) is None


def test_interleaved_reverse_uses_allocation_tags() -> None:
    goal, phone_id, case_id = _goal_with_items()
    # Case gets its own 50 first.
    after_case, _case_alloc = allocate_goal_contribution_credit(
        goal, Decimal("50.00"), item_id=case_id
    )
    case = next(i for i in after_case.items if i.id == case_id)
    assert case.current_amount == Decimal("50.00")

    # Phone contribution fills phone and spills 50 onto case.
    after_phone, phone_alloc = allocate_goal_contribution_credit(
        after_case, Decimal("650.00"), item_id=phone_id
    )
    phone = next(i for i in after_phone.items if i.id == phone_id)
    case2 = next(i for i in after_phone.items if i.id == case_id)
    assert phone.current_amount == Decimal("600.00")
    assert case2.current_amount == Decimal("100.00")
    assert phone_alloc[phone_id] == Decimal("600.00")
    assert phone_alloc[case_id] == Decimal("50.00")

    # Reverse only the phone contribution via stored allocations.
    reversed_goal = reverse_goal_contribution_credit(
        after_phone,
        Decimal("650.00"),
        item_id=phone_id,
        allocations=phone_alloc,
    )
    phone3 = next(i for i in reversed_goal.items if i.id == phone_id)
    case3 = next(i for i in reversed_goal.items if i.id == case_id)
    assert phone3.current_amount == Decimal("0.00")
    assert case3.current_amount == Decimal("50.00")  # case's own credit remains

    tags = encode_goal_allocation_tags(phone_alloc)
    assert parse_goal_allocation_tags(tags) == phone_alloc
    # Bare LIFO without allocations would wrongly wipe case's own 50.
    lifo = reverse_goal_contribution_credit(
        after_phone, Decimal("650.00"), item_id=phone_id
    )
    case_lifo = next(i for i in lifo.items if i.id == case_id)
    assert case_lifo.current_amount == Decimal("0.00")
