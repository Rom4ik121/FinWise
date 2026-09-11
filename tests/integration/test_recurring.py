"""Recurring templates: auto-create, skip, pause, catch-up."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from lib.domain.entities.recurring_rule import RecurringInterval, RecurringRule
from lib.domain.entities.transaction import TransactionType
from tests.conftest import run_async
from tests.factories import make_account


def test_process_due_recurring_catchup_skip_pause(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="5000"))
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=3)
        created_rule = await container.create_recurring_rule.execute(
            RecurringRule(
                name="Salary",
                amount=Decimal("100"),
                account_id=acc.id,
                category="Зарплата",
                type=TransactionType.INCOME,
                interval=RecurringInterval.DAILY,
                next_run=start,
            )
        )
        # Create defers the first posting; catch-up still runs for existing rules.
        assert created_rule.next_run == today + timedelta(days=1)
        none_on_create = await container.process_due_recurring.execute(max_creates=31)
        assert none_on_create == []
        await container.update_recurring_rule.execute(
            created_rule.model_copy(update={"next_run": start})
        )
        created = await container.process_due_recurring.execute(max_creates=31)
        assert len(created) == 4
        assert all(tx.type is TransactionType.INCOME for tx in created)
        refreshed = await container.list_recurring_rules.execute()
        assert refreshed[0].next_run == today + timedelta(days=1)
        txs = await container.list_transactions.execute(
            account_id=acc.id, query="Salary"
        )
        assert len(txs) == 4

        skip_rule = await container.create_recurring_rule.execute(
            RecurringRule(
                name="SkipCatch",
                amount=Decimal("5"),
                account_id=acc.id,
                interval=RecurringInterval.DAILY,
                next_run=today - timedelta(days=1),
                skip_next=True,
            )
        )
        skip_rule = await container.update_recurring_rule.execute(
            skip_rule.model_copy(
                update={"next_run": today - timedelta(days=1), "skip_next": True}
            )
        )
        skipped_creates = await container.process_due_recurring.execute(
            max_creates=31
        )
        assert len(skipped_creates) == 1
        assert skipped_creates[0].comment == "SkipCatch"
        after_skip = await container.list_recurring_rules.execute()
        skip_row = next(r for r in after_skip if r.id == skip_rule.id)
        assert skip_row.skip_next is False
        assert skip_row.next_run == today + timedelta(days=1)

        future = RecurringRule(
            name="Rent",
            amount=Decimal("50"),
            account_id=acc.id,
            interval=RecurringInterval.DAILY,
            next_run=today,
        )
        paused = await container.create_recurring_rule.execute(future)
        await container.pause_recurring_rule.execute(paused.id, paused=True)
        none = await container.process_due_recurring.execute(max_creates=31)
        assert none == []

    run_async(_run())


def test_recurring_skip_when_already_due(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account())
        today = date.today()
        rule = await container.create_recurring_rule.execute(
            RecurringRule(
                name="Gym",
                amount=Decimal("20"),
                account_id=acc.id,
                interval=RecurringInterval.WEEKLY,
                next_run=today,
            )
        )
        rule = await container.update_recurring_rule.execute(
            rule.model_copy(update={"next_run": today})
        )
        skipped = await container.skip_recurring_occurrence.execute(rule.id)
        assert skipped.next_run == today + timedelta(days=7)
        assert skipped.skip_next is False
        created = await container.process_due_recurring.execute(max_creates=31)
        assert created == []


def test_create_template_today_does_not_post(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="5000"))
        today = date.today()
        before = acc.balance
        rule = await container.create_recurring_rule.execute(
            RecurringRule(
                name="Rent",
                amount=Decimal("50"),
                account_id=acc.id,
                type=TransactionType.EXPENSE,
                interval=RecurringInterval.MONTHLY,
                next_run=today,
            )
        )
        assert rule.next_run > today
        posted = await container.process_due_recurring.execute(max_creates=31)
        assert posted == []
        txs = await container.list_transactions.execute(account_id=acc.id)
        assert txs == []
        refreshed = await container.list_accounts.execute(active_only=False)
        cash = next(a for a in refreshed if a.id == acc.id)
        assert cash.balance == before

    run_async(_run())
