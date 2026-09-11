"""Performance-sensitive path tests: tags paging, rate cache, analytics all bound."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

from lib.domain.entities.category import CategoryKind
from lib.domain.entities.transaction import TransactionType
from lib.domain.services.rate_book import RateBook
from lib.domain.services.rate_cache import (
    get_cached_rate_book,
    invalidate_rate_book_cache,
)
from lib.domain.use_cases.transactions import StatsPeriod
from lib.infrastructure.services.notification_service import NotificationKind
from lib.presentation.analytics_period import resolve_analytics_period
from lib.presentation.notification_badges import (
    BUDGET_ALERT_KINDS,
    DEBT_ALERT_KINDS,
    GOAL_ALERT_KINDS,
    SUBSCRIPTION_ALERT_KINDS,
    pending_counts,
)
from tests.conftest import run_async
from tests.factories import make_account, make_category, make_goal, make_transaction


def test_resolve_analytics_period_all_is_bounded_to_five_years() -> None:
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    cfg = resolve_analytics_period("all", now)

    assert cfg.key == "all"
    assert cfg.date_from is not None
    assert (now - cfg.date_from).days == 365 * 5
    assert cfg.group_by == StatsPeriod.MONTH
    assert cfg.max_chart_points == 36


def test_tags_filter_applies_before_limit(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="10000"))
        base = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
        plain = make_transaction(acc.id, amount="10", category="Food")
        plain = plain.model_copy(update={"date": base, "tags": []})
        await container.add_transaction.execute(plain)
        fee = make_transaction(acc.id, amount="5", category="Комиссия")
        fee = fee.model_copy(
            update={"date": base.replace(hour=13), "tags": ["fee"]}
        )
        fee = await container.add_transaction.execute(fee)
        rows = await container.transaction_repository.list(tags=["fee"], limit=1)
        assert len(rows) == 1
        assert rows[0].id == fee.id
        assert "fee" in rows[0].tags

    run_async(_run())


def test_tags_filter_limit_skips_newer_untagged_rows(container) -> None:
    """Tagged LIMIT/OFFSET must not full-scan then slice in Python only.

    Many newer untagged rows would win a naive ``ORDER BY date LIMIT 1``.
    """

    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="100000"))
        base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        older = make_transaction(acc.id, amount="5", category="Fee")
        older = older.model_copy(
            update={"date": base, "tags": ["fee", "csv-import"]}
        )
        older = await container.add_transaction.execute(older)
        newer_tagged = make_transaction(acc.id, amount="7", category="Fee")
        newer_tagged = newer_tagged.model_copy(
            update={"date": base.replace(day=10), "tags": ["fee"]}
        )
        newer_tagged = await container.add_transaction.execute(newer_tagged)
        for i in range(40):
            plain = make_transaction(acc.id, amount="1", category="Food")
            plain = plain.model_copy(
                update={"date": base.replace(day=min(11 + (i % 18), 28)), "tags": []}
            )
            await container.add_transaction.execute(plain)
        page = await container.transaction_repository.list(tags=["fee"], limit=1)
        assert len(page) == 1
        assert page[0].id == newer_tagged.id
        page2 = await container.transaction_repository.list(
            tags=["fee"], limit=1, offset=1
        )
        assert len(page2) == 1
        assert page2[0].id == older.id
        both = await container.transaction_repository.list(tags=["fee", "csv-import"])
        assert [row.id for row in both] == [older.id]

    run_async(_run())


def test_rate_book_cache_reuses_list_rates() -> None:
    async def _run() -> None:
        invalidate_rate_book_cache()
        currencies = AsyncMock()
        currencies.list_rates = AsyncMock(return_value=[])
        first = await get_cached_rate_book(currencies)
        second = await get_cached_rate_book(currencies)
        assert isinstance(first, RateBook)
        assert second is first
        assert currencies.list_rates.await_count == 1
        invalidate_rate_book_cache()
        await get_cached_rate_book(currencies)
        assert currencies.list_rates.await_count == 2

    run_async(_run())


def test_pending_counts_single_list_pending_pass(container) -> None:
    ns = container.notification_service
    ns.push("g", "b", kind=NotificationKind.GOAL_MILESTONE, related_id="g1")
    ns.push("d", "b", kind=NotificationKind.DEBT_OVERDUE, related_id="d1")
    ns.push("s", "b", kind=NotificationKind.SUBSCRIPTION_REMINDER, related_id="s1")
    ns.push("bu", "b", kind=NotificationKind.BUDGET_OVER, related_id="Food")

    calls = {"n": 0}
    original = ns.list_pending

    def _counting(*, now=None):
        calls["n"] += 1
        return original(now=now)

    ns.list_pending = _counting  # type: ignore[method-assign]
    settings = type(
        "S",
        (),
        {
            "notifications_enabled": True,
            "goal_milestones": True,
            "debt_reminders": True,
            "subscription_reminders": True,
            "budget_alerts": True,
        },
    )()
    counts = pending_counts(
        container,
        settings,
        {
            "goals": GOAL_ALERT_KINDS,
            "debts": DEBT_ALERT_KINDS,
            "subs": SUBSCRIPTION_ALERT_KINDS,
            "budgets": BUDGET_ALERT_KINDS,
        },
    )
    assert calls["n"] == 1
    assert counts["goals"] == 1
    assert counts["debts"] == 1
    assert counts["subs"] == 1
    assert counts["budgets"] == 1


def test_recalculate_budgets_one_month_scan(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        await container.create_category.execute(
            make_category(name="Transport", kind=CategoryKind.EXPENSE)
        )
        acc = await container.create_account.execute(make_account(balance="5000"))
        when = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
        await container.set_budget.execute("Food", 8, 2026, Decimal("200"))
        await container.set_budget.execute("Transport", 8, 2026, Decimal("150"))
        food = make_transaction(acc.id, amount="40", category="Food")
        food = food.model_copy(update={"date": when})
        await container.add_transaction.execute(food)
        transport = make_transaction(acc.id, amount="25", category="Transport")
        transport = transport.model_copy(update={"date": when})
        await container.add_transaction.execute(transport)
        updated = await container.recalculate_budget_spent.execute(month=8, year=2026)
        by_cat = {b.category_id: b.spent for b in updated}
        assert by_cat["Food"] == Decimal("40.00")
        assert by_cat["Transport"] == Decimal("25.00")

    run_async(_run())


def test_clear_goal_links_bulk(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="5000"))
        goal = await container.create_goal.execute(
            make_goal(target="1000", current="0")
        )
        tx = await container.add_transaction.execute(
            make_transaction(
                acc.id,
                amount="100",
                category="Savings",
                goal_id=goal.id,
                tx_type=TransactionType.EXPENSE,
            )
        )
        assert tx.goal_id == goal.id
        assert await container.delete_goal.execute(goal.id) is True
        refreshed = await container.transaction_repository.get_by_id(tx.id)
        assert refreshed is not None
        assert refreshed.goal_id is None
        assert refreshed.goal_credit_amount is not None

    run_async(_run())


def test_fetch_transactions_paged_covers_all_rows(container) -> None:
    async def _run() -> None:
        from lib.presentation.tx_query import fetch_transactions_paged

        acc = await container.create_account.execute(make_account(balance="10000"))
        base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(12):
            tx = make_transaction(acc.id, amount="1", category="Food")
            tx = tx.model_copy(update={"date": base.replace(day=min(i + 1, 28))})
            await container.add_transaction.execute(tx)
        rows = await fetch_transactions_paged(
            container.list_transactions,
            account_id=acc.id,
            page_size=5,
        )
        assert len(rows) == 12

    run_async(_run())


def test_list_has_debt_filter(container) -> None:
    async def _run() -> None:
        from tests.factories import make_debt

        acc = await container.create_account.execute(make_account(balance="5000"))
        debt = await container.create_debt.execute(make_debt(amount="100"))
        plain = await container.add_transaction.execute(
            make_transaction(acc.id, amount="10", category="Food")
        )
        linked = make_transaction(acc.id, amount="20", category="Долг")
        linked = linked.model_copy(update={"debt_id": debt.id})
        linked = await container.add_transaction.execute(linked)
        debt_rows = await container.list_transactions.execute(has_debt=True)
        ids = {tx.id for tx in debt_rows}
        assert linked.id in ids
        assert plain.id not in ids

    run_async(_run())
