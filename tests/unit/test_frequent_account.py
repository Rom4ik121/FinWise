"""Tests for frequent-account picker helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from lib.domain.entities.account import Account
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.presentation.frequent_account import (
    account_option_label,
    frequent_account_id,
    order_accounts_frequent_first,
)


def _account(aid: str, name: str = "") -> Account:
    return Account(
        id=aid,
        name=name or aid,
        currency="UZS",
        balance=Decimal("0"),
    )


def _tx(
    account_id: str,
    *,
    days_ago: int = 0,
    transfer_id: str | None = None,
) -> Transaction:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return Transaction(
        account_id=account_id,
        type=TransactionType.EXPENSE,
        amount=Decimal("10"),
        currency="UZS",
        category="Еда",
        date=when,
        transfer_id=transfer_id,
    )


def test_frequent_account_id_picks_most_used() -> None:
    accounts = [_account("a"), _account("b"), _account("c")]
    txs = [
        _tx("b"),
        _tx("b", days_ago=1),
        _tx("a", days_ago=2),
        _tx("c", days_ago=3),
    ]
    assert frequent_account_id(accounts, txs) == "b"


def test_frequent_account_id_ignores_transfers() -> None:
    accounts = [_account("a"), _account("b")]
    txs = [
        _tx("a", transfer_id="t1"),
        _tx("a", transfer_id="t1"),
        _tx("b"),
    ]
    assert frequent_account_id(accounts, txs) == "b"


def test_frequent_account_id_tie_breaks_recent() -> None:
    accounts = [_account("a"), _account("b")]
    txs = [
        _tx("a"),
        _tx("b", days_ago=1),
    ]
    assert frequent_account_id(accounts, txs) == "a"


def test_order_accounts_frequent_first() -> None:
    accounts = [_account("a"), _account("b"), _account("c")]
    ordered = order_accounts_frequent_first(accounts, "c")
    assert [a.id for a in ordered] == ["c", "a", "b"]


def test_account_option_label_marks_frequent() -> None:
    account = _account("cash", "Наличные")
    labeled = account_option_label(account, frequent_id="cash", lang="ru")
    assert "часто" in labeled
    plain = account_option_label(account, frequent_id="other", lang="ru")
    assert "часто" not in plain
