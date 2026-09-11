"""Domain ledger FX aggregation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from lib.domain.entities.account import Account
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.services.ledger_fx import aggregate_cashflow_period, amount_to_base
from lib.domain.services.rate_book import RateBook
from lib.domain.use_cases.transactions import GetTransactionStatsUseCase, StatsPeriod


def test_amount_to_base_same_currency() -> None:
    book = RateBook.from_pairs({})
    assert amount_to_base(book, Decimal("12.3"), "RUB", "RUB") == Decimal("12.30")


def test_sum_balances_in_base_skips_excluded() -> None:
    from lib.domain.services.ledger_fx import sum_balances_in_base

    included = Account(
        id=str(uuid4()),
        name="Cash",
        balance=Decimal("100.00"),
        currency="RUB",
        include_in_total=True,
    )
    excluded = Account(
        id=str(uuid4()),
        name="Hidden",
        balance=Decimal("999.00"),
        currency="RUB",
        include_in_total=False,
    )
    total, ok = sum_balances_in_base(
        [included, excluded], base="RUB", book=RateBook.from_pairs({})
    )
    assert ok is True
    assert total == Decimal("100.00")


def test_aggregate_skips_corporate_accounts() -> None:
    now = datetime.now(timezone.utc)
    personal = Account(
        id=str(uuid4()),
        name="Cash",
        balance=Decimal("100.00"),
        currency="RUB",
        include_in_total=True,
    )
    corporate = Account(
        id=str(uuid4()),
        name="LLC",
        balance=Decimal("900.00"),
        currency="RUB",
        include_in_total=False,
        is_corporate=True,
    )
    corp_tx = Transaction(
        account_id=corporate.id,
        amount=Decimal("50.00"),
        category="Revenue",
        date=now,
        type=TransactionType.INCOME,
        currency="RUB",
    )
    personal_tx = Transaction(
        account_id=personal.id,
        amount=Decimal("10.00"),
        category="Food",
        date=now,
        type=TransactionType.EXPENSE,
        currency="RUB",
    )
    book = RateBook.from_pairs({})
    total, inc, exp, *_rest, ok = aggregate_cashflow_period(
        [personal, corporate],
        [corp_tx, personal_tx],
        base="RUB",
        book=book,
        period_key=lambda d, _g: "x",
        group_by=StatsPeriod.DAY,
    )
    assert ok is True
    assert total == Decimal("100.00")
    assert inc == Decimal("0.00")
    assert exp == Decimal("10.00")


def test_aggregate_skips_transfers_and_sums() -> None:
    now = datetime.now(timezone.utc)
    acc = Account(
        id=str(uuid4()),
        name="Cash",
        balance=Decimal("100.00"),
        currency="RUB",
        include_in_total=True,
    )
    income = Transaction(
        account_id=acc.id,
        amount=Decimal("50.00"),
        category="Salary",
        date=now,
        type=TransactionType.INCOME,
        currency="RUB",
    )
    expense = Transaction(
        account_id=acc.id,
        amount=Decimal("20.00"),
        category="Food",
        date=now,
        type=TransactionType.EXPENSE,
        currency="RUB",
    )
    transfer = Transaction(
        account_id=acc.id,
        amount=Decimal("5.00"),
        category="Transfer",
        date=now,
        type=TransactionType.EXPENSE,
        currency="RUB",
        transfer_id=str(uuid4()),
    )
    book = RateBook.from_pairs({})
    total, inc, exp, by_e, by_i, by_p, ok = aggregate_cashflow_period(
        [acc],
        [income, expense, transfer],
        base="RUB",
        book=book,
        period_key=GetTransactionStatsUseCase._period_key,
        group_by=StatsPeriod.MONTH,
    )
    assert ok is True
    assert total == Decimal("100.00")
    assert inc == Decimal("50.00")
    assert exp == Decimal("20.00")
    assert by_e[0][0] == "Food"
    assert by_i[0][0] == "Salary"
    assert len(by_p) == 1


def test_aggregate_splits_expense_line_items() -> None:
    now = datetime.now(timezone.utc)
    acc = Account(
        id=str(uuid4()),
        name="Cash",
        balance=Decimal("100.00"),
        currency="RUB",
        include_in_total=True,
    )
    from lib.domain.entities.transaction import TransactionItem

    basket = Transaction(
        account_id=acc.id,
        amount=Decimal("150.00"),
        category="Header",
        date=now,
        type=TransactionType.EXPENSE,
        currency="RUB",
        items=[
            TransactionItem(name="Bread", amount=Decimal("100.00"), category="Food"),
            TransactionItem(name="Bus", amount=Decimal("50.00"), category="Transport"),
        ],
    )
    book = RateBook.from_pairs({})
    _total, _inc, exp, by_e, _by_i, _by_p, ok = aggregate_cashflow_period(
        [acc],
        [basket],
        base="RUB",
        book=book,
        period_key=lambda d, _g: "x",
        group_by=StatsPeriod.DAY,
    )
    assert ok is True
    assert exp == Decimal("150.00")
    cats = dict(by_e)
    assert cats["Food"] == Decimal("100.00")
    assert cats["Transport"] == Decimal("50.00")
    assert "Header" not in cats
