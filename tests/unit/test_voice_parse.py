"""Voice command parser for spoken expenses."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.entities.transaction import TransactionType
from lib.infrastructure.services.voice_parse import parse_voice_expense


def test_parse_expense_name_and_amount() -> None:
    draft = parse_voice_expense("расход кофе 15000")
    assert draft.tx_type is TransactionType.EXPENSE
    assert draft.amount == Decimal("15000.00")
    assert "кофе" in draft.category.casefold()


def test_parse_income_millions() -> None:
    draft = parse_voice_expense("доход зарплата 2 млн")
    assert draft.tx_type is TransactionType.INCOME
    assert draft.amount == Decimal("2000000.00")
    assert "зарплата" in draft.category.casefold()


def test_parse_thousands_without_type_defaults_to_expense() -> None:
    draft = parse_voice_expense("такси 25 тысяч")
    assert draft.tx_type is TransactionType.EXPENSE
    assert draft.amount == Decimal("25000.00")
    assert "такси" in draft.category.casefold()


def test_parse_expense_name_without_amount() -> None:
    draft = parse_voice_expense("расход кофе")
    assert draft.tx_type is TransactionType.EXPENSE
    assert draft.amount is None
    assert "кофе" in draft.category.casefold()
