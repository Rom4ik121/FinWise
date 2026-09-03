"""Budget entity validation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib.domain.entities.budget import Budget, BudgetProgress


def test_budget_progress_and_overspend() -> None:
    budget = Budget(
        category_id="Food",
        month=8,
        year=2026,
        amount_limit=Decimal("100"),
        spent=Decimal("80"),
    )
    assert budget.percent_used == Decimal("80")
    assert budget.remaining == Decimal("20.00")
    assert budget.is_over_budget is False

    over = budget.model_copy(update={"spent": Decimal("150")})
    assert over.is_over_budget is True
    assert over.remaining == Decimal("-50.00")
    assert over.overspend == Decimal("50.00")
    progress = BudgetProgress.from_budget(over)
    assert progress.is_over_budget is True
    assert progress.percent > 100
    assert progress.remaining == Decimal("-50.00")


def test_budget_accepts_half_alert_level() -> None:
    budget = Budget(
        category_id="Food",
        month=8,
        year=2026,
        amount_limit=Decimal("100"),
        spent=Decimal("50"),
        last_alert_level=50,
    )
    assert budget.last_alert_level == 50


def test_budget_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        Budget(category_id="Food", month=13, year=2026, amount_limit=Decimal("10"))
    with pytest.raises(ValueError):
        Budget(category_id="Food", month=1, year=2026, amount_limit=Decimal("0"))
    with pytest.raises(ValueError):
        Budget(category_id="  ", month=1, year=2026, amount_limit=Decimal("10"))
