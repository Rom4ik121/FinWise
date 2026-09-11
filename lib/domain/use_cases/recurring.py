"""Recurring template use cases (income/expense auto-create)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from lib.domain.entities.recurring_rule import RecurringInterval, RecurringRule
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.recurring_rule_repository import RecurringRuleRepository
from lib.domain.unit_of_work import in_unit_of_work, unit_of_work

if TYPE_CHECKING:
    from lib.domain.use_cases.transactions import AddTransactionUseCase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    clamped = min(day.day, calendar.monthrange(year, month)[1])
    return date(year, month, clamped)


def advance_recurring_date(
    current: date,
    interval: RecurringInterval,
    *,
    interval_count: int = 1,
) -> date:
    """Move ``current`` forward by one template interval."""
    count = max(1, int(interval_count or 1))
    kind = (
        interval
        if isinstance(interval, RecurringInterval)
        else RecurringInterval(str(interval))
    )
    if kind == RecurringInterval.DAILY:
        return current + timedelta(days=count)
    if kind == RecurringInterval.WEEKLY:
        return current + timedelta(weeks=count)
    if kind == RecurringInterval.YEARLY:
        return _add_months(current, 12 * count)
    return _add_months(current, count)


def preview_recurring_dates(
    start: date,
    interval: RecurringInterval,
    *,
    interval_count: int = 1,
    count: int = 3,
) -> list[date]:
    """Next ``count`` occurrence dates including ``start``."""
    cursor = start
    out: list[date] = []
    for _ in range(max(1, count)):
        out.append(cursor)
        cursor = advance_recurring_date(
            cursor, interval, interval_count=interval_count
        )
    return out


def first_scheduled_run(
    start: date,
    interval: RecurringInterval,
    *,
    interval_count: int = 1,
    today: Optional[date] = None,
) -> date:
    """First auto-create date that does not post on the save day.

    Creating a template with ``next_run`` today (or in the past) used to
    fire ``process_due_recurring`` on the same launch and change balances
    immediately. Catch-up of *existing* rules is unchanged.
    """
    moment = today or _utc_now().date()
    cursor = start
    if cursor > moment:
        return cursor
    safety = 0
    while cursor <= moment and safety < 500:
        cursor = advance_recurring_date(
            cursor, interval, interval_count=interval_count
        )
        safety += 1
    return cursor


class CreateRecurringRuleUseCase:
    """Persist a new recurring template."""

    def __init__(self, rules: RecurringRuleRepository) -> None:
        self._rules = rules

    async def execute(self, rule: RecurringRule) -> RecurringRule:
        now = _utc_now()
        nxt = first_scheduled_run(
            rule.next_run,
            rule.interval,
            interval_count=rule.interval_count,
            today=now.date(),
        )
        created = rule.model_copy(
            update={"created_at": now, "updated_at": now, "next_run": nxt}
        )
        return await self._rules.create(created)


class UpdateRecurringRuleUseCase:
    """Update an existing template."""

    def __init__(self, rules: RecurringRuleRepository) -> None:
        self._rules = rules

    async def execute(self, rule: RecurringRule) -> RecurringRule:
        existing = await self._rules.get_by_id(rule.id)
        if existing is None:
            raise ValueError("Recurring rule not found")
        updated = rule.model_copy(update={"updated_at": _utc_now()})
        return await self._rules.update(updated)


class DeleteRecurringRuleUseCase:
    """Remove a template."""

    def __init__(self, rules: RecurringRuleRepository) -> None:
        self._rules = rules

    async def execute(self, rule_id: str) -> bool:
        return await self._rules.delete(rule_id)


class ListRecurringRulesUseCase:
    """List templates."""

    def __init__(self, rules: RecurringRuleRepository) -> None:
        self._rules = rules

    async def execute(self, *, include_paused: bool = True) -> list[RecurringRule]:
        return await self._rules.list(include_paused=include_paused)


class PauseRecurringRuleUseCase:
    """Pause auto-create without deleting the template."""

    def __init__(self, rules: RecurringRuleRepository) -> None:
        self._rules = rules

    async def execute(self, rule_id: str, *, paused: bool = True) -> RecurringRule:
        rule = await self._rules.get_by_id(rule_id)
        if rule is None:
            raise ValueError("Recurring rule not found")
        return await self._rules.update(
            rule.model_copy(update={"paused": paused, "updated_at": _utc_now()})
        )


class SkipRecurringOccurrenceUseCase:
    """Skip the next due date (or mark skip_next if not yet due)."""

    def __init__(self, rules: RecurringRuleRepository) -> None:
        self._rules = rules

    async def execute(self, rule_id: str, *, as_of: Optional[date] = None) -> RecurringRule:
        rule = await self._rules.get_by_id(rule_id)
        if rule is None:
            raise ValueError("Recurring rule not found")
        today = as_of or _utc_now().date()
        if rule.next_run <= today:
            nxt = advance_recurring_date(
                rule.next_run, rule.interval, interval_count=rule.interval_count
            )
            return await self._rules.update(
                rule.model_copy(
                    update={
                        "next_run": nxt,
                        "skip_next": False,
                        "updated_at": _utc_now(),
                    }
                )
            )
        return await self._rules.update(
            rule.model_copy(update={"skip_next": True, "updated_at": _utc_now()})
        )


class ProcessDueRecurringRulesUseCase:
    """Create ledger rows for due templates and catch up missed days."""

    def __init__(
        self,
        rules: RecurringRuleRepository,
        accounts: AccountRepository,
        add_transaction: "AddTransactionUseCase",
        session_factory: object = None,
    ) -> None:
        self._rules = rules
        self._accounts = accounts
        self._add = add_transaction
        self._session_factory = session_factory

    async def execute(
        self,
        *,
        as_of: Optional[date] = None,
        max_creates: int = 31,
    ) -> list[Transaction]:
        today = as_of or _utc_now().date()
        cap = 10_000 if max_creates <= 0 else max(1, int(max_creates))
        due = await self._rules.list_due(today)
        created: list[Transaction] = []
        accounts = await self._accounts.list(active_only=False)
        by_id = {a.id: a for a in accounts}

        async def _process(rule: RecurringRule) -> None:
            nonlocal created
            account = by_id.get(rule.account_id)
            if account is None:
                return
            cursor = rule.next_run
            made = 0
            skip_next = bool(rule.skip_next)
            last_created = rule.last_created_at
            while cursor <= today and made < cap:
                if skip_next:
                    skip_next = False
                    cursor = advance_recurring_date(
                        cursor, rule.interval, interval_count=rule.interval_count
                    )
                    continue
                tx_type = (
                    rule.type
                    if isinstance(rule.type, TransactionType)
                    else TransactionType(str(rule.type))
                )
                stamp = datetime(
                    cursor.year, cursor.month, cursor.day, tzinfo=timezone.utc
                )
                saved = await self._add.execute(
                    Transaction(
                        account_id=rule.account_id,
                        amount=rule.amount,
                        category=rule.category or rule.name,
                        comment=rule.comment or rule.name,
                        date=stamp,
                        type=tx_type,
                        currency=account.currency or rule.currency,
                        tags=["recurring"],
                    )
                )
                created.append(saved)
                last_created = _utc_now()
                made += 1
                cursor = advance_recurring_date(
                    cursor, rule.interval, interval_count=rule.interval_count
                )
            if made or rule.next_run != cursor or rule.skip_next != skip_next:
                await self._rules.update(
                    rule.model_copy(
                        update={
                            "next_run": cursor,
                            "skip_next": skip_next,
                            "last_created_at": last_created,
                            "updated_at": _utc_now(),
                        }
                    )
                )

        for rule in due:
            if self._session_factory is not None and not in_unit_of_work():
                with unit_of_work(self._session_factory):  # type: ignore[arg-type]
                    await _process(rule)
            else:
                await _process(rule)
        return created
