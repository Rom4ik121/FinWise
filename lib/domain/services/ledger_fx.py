"""Shared FX conversion + period cashflow aggregation (domain, no UI)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import TransactionType
from lib.domain.services.rate_book import RateBook


def amount_to_base(
    book: RateBook | None,
    amount: Decimal,
    currency: str | None,
    base: str,
) -> Decimal | None:
    """Convert ``amount`` to ``base``; ``None`` when the rate is missing."""
    src = normalize_currency_code(currency or base)
    dst = normalize_currency_code(base)
    if src == dst:
        return quantize_money(amount, currency=dst)
    if book is None:
        return None
    converted = book.convert(amount, src, dst)
    if converted is None:
        return None
    return quantize_money(converted, currency=dst)


def sum_balances_in_base(
    accounts: list[Any],
    *,
    base: str,
    book: RateBook,
) -> tuple[Decimal, bool]:
    """Sum ``include_in_total`` account balances in ``base``.

    Returns ``(total, fx_ok)``. Missing FX for a foreign account sets
    ``fx_ok=False`` and skips that balance.
    """
    base = normalize_currency_code(base)
    total = Decimal("0.00")
    ok = True
    for account in accounts:
        if getattr(account, "is_corporate", False):
            continue
        if not getattr(account, "include_in_total", True):
            continue
        converted = amount_to_base(book, account.balance, account.currency, base)
        if converted is not None:
            total += converted
        else:
            ok = False
    return total, ok


def aggregate_cashflow_period(
    accounts: list[Any],
    transactions: list[Any],
    *,
    base: str,
    book: RateBook,
    period_key: Callable[[datetime, Any], str],
    group_by: Any,
) -> tuple[
    Decimal,
    Decimal,
    Decimal,
    list[tuple[str, Decimal]],
    list[tuple[str, Decimal]],
    list[tuple[str, Decimal, Decimal]],
    bool,
]:
    """Single-pass KPI totals for analytics/dashboard (shared Desktop+Mobile).

    Returns ``(net_worth, income, expense, by_expense, by_income, by_period, fx_ok)``.
    Transfer legs and corporate-account activity are skipped. Missing FX sets
    ``fx_ok=False`` and omits that row.
    """
    base = normalize_currency_code(base)
    total = Decimal("0.00")
    income = Decimal("0.00")
    expense = Decimal("0.00")
    ok = True
    expense_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    income_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    period_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    period_expense: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    corporate_ids = {
        getattr(a, "id", None)
        for a in accounts
        if getattr(a, "is_corporate", False)
    }
    corporate_ids.discard(None)

    for account in accounts:
        if getattr(account, "is_corporate", False):
            continue
        if not getattr(account, "include_in_total", True):
            continue
        src = normalize_currency_code(account.currency)
        converted = book.convert(account.balance, src, base)
        if converted is not None:
            total += converted
        elif src == base:
            total += account.balance
        else:
            ok = False

    for tx in transactions:
        if getattr(tx, "transfer_id", None):
            continue
        if getattr(tx, "account_id", None) in corporate_ids:
            continue
        src = normalize_currency_code(tx.currency)
        converted = book.convert(tx.amount, src, base)
        if converted is None:
            if src == base:
                converted = tx.amount
            else:
                ok = False
                continue
        key = period_key(tx.date, group_by)
        if tx.type == TransactionType.INCOME:
            income += converted
            period_income[key] += converted
            income_totals[tx.category] += converted
        else:
            expense += converted
            period_expense[key] += converted
            if getattr(tx, "items", None):
                for item in tx.items:
                    line_amt = book.convert(item.amount, src, base) if src != base else item.amount
                    if line_amt is None:
                        if src == base:
                            line_amt = item.amount
                        else:
                            ok = False
                            continue
                    cat = (getattr(item, "category", None) or tx.category or "").strip()
                    expense_totals[cat] += line_amt
            else:
                expense_totals[tx.category] += converted

    by_expense = sorted(expense_totals.items(), key=lambda kv: kv[1], reverse=True)
    by_income = sorted(income_totals.items(), key=lambda kv: kv[1], reverse=True)
    keys = sorted(set(period_income) | set(period_expense))
    by_period = [(key, period_income[key], period_expense[key]) for key in keys]
    return total, income, expense, by_expense, by_income, by_period, ok
