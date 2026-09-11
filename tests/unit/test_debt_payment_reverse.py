"""Untagged debt-payment reverse must not invent accrued interest."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.use_cases.debts import (
    apply_debt_payment_credit,
    reverse_debt_payment_credit,
    with_debt_interest_tag,
)
from tests.factories import make_debt, make_transaction


def test_untagged_reverse_does_not_inflate_accrued() -> None:
    debt = make_debt(amount="100").model_copy(
        update={
            "accrue_interest": True,
            "accrued_interest": Decimal("10.00"),
            "remaining_amount": Decimal("100.00"),
        }
    )
    applied = apply_debt_payment_credit(debt, Decimal("50.00"))
    assert applied.accrued_interest == Decimal("0.00")
    assert applied.remaining_amount == Decimal("50.00")
    restored = reverse_debt_payment_credit(applied, Decimal("50.00"))
    assert restored.accrued_interest == Decimal("0.00")
    assert restored.remaining_amount == Decimal("100.00")


def test_tagged_reverse_restores_interest_slice() -> None:
    debt = make_debt(amount="100").model_copy(
        update={
            "accrue_interest": True,
            "accrued_interest": Decimal("10.00"),
            "remaining_amount": Decimal("100.00"),
        }
    )
    tx = with_debt_interest_tag(
        make_transaction("acc", amount="50", debt_id=debt.id),
        debt,
        Decimal("50.00"),
    )
    assert "debt_interest:10.00" in (tx.tags or [])
    applied = apply_debt_payment_credit(debt, Decimal("50.00"), transaction=tx)
    assert applied.accrued_interest == Decimal("0.00")
    restored = reverse_debt_payment_credit(
        applied, Decimal("50.00"), transaction=tx
    )
    assert restored.accrued_interest == Decimal("10.00")
    assert restored.remaining_amount == Decimal("100.00")
