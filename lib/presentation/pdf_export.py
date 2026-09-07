"""Gather ledger data and write a configured PDF report."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from lib.domain.entities.account import Account
from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.services.rate_book import RateBook
from lib.infrastructure.services.export_service import ExportService, PdfSectionFlags
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.account_stats import aggregate_account_period
from lib.presentation.analytics_period import (
    enumerate_period_keys,
    fill_time_series,
    resolve_export_period,
)
from lib.presentation.tx_query import fetch_transactions_paged
from lib.presentation.utils import format_date, load_rate_book
from lib.presentation.widgets.pdf_export_sheet import PdfExportChoice


def _must_convert(book: RateBook, amount: Decimal, src: str, dest: str) -> Decimal:
    src_c = (src or dest).upper()
    dest_c = dest.upper()
    if src_c == dest_c:
        return quantize_money(amount)
    converted = book.convert(amount, src_c, dest_c)
    if converted is None:
        raise ValueError("No exchange rate for this currency pair")
    return quantize_money(converted)


def _scope_label(choice: PdfExportChoice, lang: str) -> str:
    from lib.presentation.utils import tr

    if choice.account_scope == "personal":
        return tr("settings.export_scope_personal", lang)
    if choice.account_scope == "corporate":
        return tr("settings.export_scope_corporate", lang)
    if choice.account_scope == "selected":
        return tr("settings.export_scope_selected", lang)
    return tr("settings.export_scope_all", lang)


async def export_configured_pdf(
    container: Any,
    choice: PdfExportChoice,
    *,
    language: str,
    locked_account: Account | None = None,
) -> Path:
    """Build a global or single-account PDF from sheet options."""
    lang = (language or "en").lower()
    c = container
    book = await load_rate_book(c)
    base = (
        getattr(getattr(c, "config", None), "default_currency", None)
        or "USD"
    )
    settings = None
    get_settings = getattr(c, "get_settings", None)
    if get_settings is not None:
        settings = await get_settings.execute()
        base = getattr(settings, "default_currency", base) or base

    accounts = await c.list_accounts.execute()
    selected = [a for a in accounts if a.id in choice.account_ids]
    if locked_account is not None:
        selected = [a for a in selected if a.id == locked_account.id] or [locked_account]

    txs: list[Transaction] = await fetch_transactions_paged(
        c.list_transactions,
        date_from=choice.date_from,
        date_to=choice.date_to,
    )
    selected_ids = {a.id for a in selected}
    txs = [t for t in txs if t.account_id in selected_ids]
    names = {a.id: a.name for a in selected}

    cfg = resolve_export_period(
        choice.period_key,
        datetime.now(timezone.utc),
        custom_from=choice.date_from,
        custom_to=choice.date_to,
    )
    svc = ExportService(c.config)

    if locked_account is not None:
        account = locked_account
        stats = aggregate_account_period(txs, cfg.group_by)
        series = fill_time_series(
            stats.by_period,
            enumerate_period_keys(cfg, existing=[p[0] for p in stats.by_period]),
        )
        expense_rows: list[tuple[str, str, Decimal]] = []
        if choice.sections.transactions:
            for tx in txs:
                if tx.transfer_id or tx.type != TransactionType.EXPENSE:
                    continue
                expense_rows.append(
                    (
                        format_date(tx.date, with_time=False),
                        localize_category_name(tx.category, lang),
                        tx.amount,
                    )
                )
        cats = [
            (localize_category_name(cat, lang), amt)
            for cat, amt in stats.by_category
        ]
        return svc.export_account_period_pdf(
            account_name=account.name,
            currency=account.currency,
            period_label=choice.period_label,
            balance=account.balance,
            income=stats.income,
            expense=stats.expense,
            ops_income=stats.income if account.is_corporate else stats.ops_income,
            ops_expense=stats.expense if account.is_corporate else stats.ops_expense,
            by_category=cats if choice.sections.categories else (),
            expenses=expense_rows,
            by_period=series if choice.sections.charts else (),
            language=lang,
            sections=choice.sections,
        )

    income = Decimal("0")
    expense = Decimal("0")
    balance = Decimal("0")
    for account in selected:
        if choice.account_scope == "all" and not account.include_in_total:
            continue
        balance += _must_convert(book, account.balance, account.currency, base)

    cat_map: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    period_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    period_expense: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    from lib.domain.use_cases.transactions import GetTransactionStatsUseCase

    tx_rows: list[tuple[str, str, str, Decimal, str, str]] = []
    for tx in txs:
        kind = str(getattr(tx.type, "value", tx.type))
        converted = _must_convert(book, tx.amount, tx.currency, base)
        bucket = GetTransactionStatsUseCase._period_key(tx.date, cfg.group_by)
        if kind == "income":
            income += converted
            period_income[bucket] += converted
        else:
            expense += converted
            period_expense[bucket] += converted
        if (
            choice.sections.categories
            and kind == "expense"
            and not tx.transfer_id
        ):
            cat_map[localize_category_name(tx.category, lang)] += converted
        if choice.sections.transactions and not tx.transfer_id:
            tx_rows.append(
                (
                    format_date(tx.date, with_time=False),
                    names.get(tx.account_id, tx.account_id)[:24],
                    localize_category_name(tx.category, lang),
                    tx.amount,
                    tx.currency,
                    kind,
                )
            )
    tx_rows.sort(key=lambda row: row[0], reverse=True)
    by_category = sorted(cat_map.items(), key=lambda item: item[1], reverse=True)
    keys = enumerate_period_keys(
        cfg, existing=list(set(period_income) | set(period_expense))
    )
    by_period = fill_time_series(
        [
            (key, period_income[key], period_expense[key])
            for key in sorted(set(period_income) | set(period_expense))
        ],
        keys,
    )

    goals = []
    debts = []
    subs = []
    flags: PdfSectionFlags = choice.sections
    if flags.goals and getattr(c, "list_goals", None) is not None:
        goals = await c.list_goals.execute()
    if flags.debts and getattr(c, "list_debts", None) is not None:
        debts = await c.list_debts.execute()
    if flags.subscriptions and getattr(c, "list_subscriptions", None) is not None:
        subs = await c.list_subscriptions.execute()

    return svc.export_summary_pdf(
        accounts=selected if flags.accounts else (),
        transactions=txs,
        goals=goals,
        debts=debts,
        subscriptions=subs,
        language=lang,
        period_label=choice.period_label,
        scope_label=_scope_label(choice, lang),
        currency=base,
        total_balance=quantize_money(balance),
        income=quantize_money(income),
        expense=quantize_money(expense),
        by_category=by_category,
        by_period=by_period,
        tx_rows=tx_rows,
        sections=flags,
    )
