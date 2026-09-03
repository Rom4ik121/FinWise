"""Subscriptions CRUD and due processing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from lib.domain.entities.subscription import Periodicity, SubscriptionStatus
from tests.conftest import run_async
from tests.factories import make_account, make_subscription


def test_subscription_crud(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account())
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, name="Spotify", amount="15")
        )
        listed = await container.list_subscriptions.execute(active_only=True)
        assert any(s.id == sub.id for s in listed)
        assert sub.category == "Spotify"
        cat = await container.category_repository.get_by_name("Spotify")
        assert cat is not None
        assert cat.icon == (sub.icon or "autorenew")

        updated = await container.update_subscription.execute(
            sub.model_copy(update={"amount": Decimal("20"), "icon": "movie"})
        )
        assert updated.amount == Decimal("20.00")
        assert updated.category == "Spotify"
        cat = await container.category_repository.get_by_name("Spotify")
        assert cat is not None
        assert cat.icon == "movie"
        assert await container.delete_subscription.execute(sub.id) is True

    run_async(_run())


def test_process_due_subscriptions_charges_account(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=1)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="50",
                next_billing=due,
                periodicity=Periodicity.MONTHLY,
            )
        )
        txs = await container.process_due_subscriptions.execute()
        assert len(txs) >= 1
        assert all(tx.subscription_id == sub.id for tx in txs)
        assert all(tx.category == sub.name for tx in txs)
        account = await container.account_repository.get_by_id(acc.id)
        assert account is not None
        assert account.balance == Decimal("450.00")

        refreshed = await container.subscription_repository.get_by_id(sub.id)
        assert refreshed is not None
        assert refreshed.next_billing_date > due
        assert refreshed.last_charged_at is not None
        assert refreshed.payments_made >= 1

    run_async(_run())


def test_process_due_subscriptions_catchup_multiple_periods(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        due = datetime.now(timezone.utc) - timedelta(days=95)
        await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="100",
                next_billing=due,
                periodicity=Periodicity.MONTHLY,
            )
        )
        txs = await container.process_due_subscriptions.execute()
        assert len(txs) == 1
        account = await container.account_repository.get_by_id(acc.id)
        assert account is not None
        assert account.balance == Decimal("900.00")

    run_async(_run())


def test_process_due_skips_when_insufficient_balance(container) -> None:
    async def _run() -> None:
        settings = await container.get_settings.execute()
        await container.update_settings.execute(
            settings.model_copy(update={"check_balance_before_subscription": True})
        )
        acc = await container.create_account.execute(make_account(balance="10"))
        due = datetime.now(timezone.utc) - timedelta(days=1)
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="50", next_billing=due)
        )
        txs = await container.process_due_subscriptions.execute()
        assert txs == []
        account = await container.account_repository.get_by_id(acc.id)
        assert account is not None
        assert account.balance == Decimal("10.00")
        refreshed = await container.subscription_repository.get_by_id(sub.id)
        assert refreshed is not None
        assert refreshed.next_billing_date == due
        assert refreshed.last_skip_date is not None

    run_async(_run())


def test_pause_skips_billing_resume_advances(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=5)
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="20", next_billing=due)
        )
        paused = await container.pause_subscription.execute(sub.id)
        assert paused.status == SubscriptionStatus.PAUSED
        txs = await container.process_due_subscriptions.execute()
        assert txs == []
        resumed = await container.resume_subscription.execute(sub.id)
        assert resumed.status == SubscriptionStatus.ACTIVE
        assert resumed.next_billing_date > datetime.now(timezone.utc) - timedelta(
            minutes=1
        )

    run_async(_run())


def test_max_payments_expires_subscription(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=1)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="10",
                next_billing=due,
                max_payments=1,
            )
        )
        # Already at limit before charging.
        await container.update_subscription.execute(
            sub.model_copy(update={"payments_made": 1})
        )
        txs = await container.process_due_subscriptions.execute()
        assert txs == []
        refreshed = await container.subscription_repository.get_by_id(sub.id)
        assert refreshed is not None
        assert refreshed.status == SubscriptionStatus.EXPIRED

    run_async(_run())


def test_custom_periodicity_and_charge_now(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="200"))
        due = datetime.now(timezone.utc)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="15",
                next_billing=due,
                periodicity=Periodicity.CUSTOM,
                custom_interval_days=10,
            )
        )
        tx = await container.charge_subscription_now.execute(
            sub.id, check_balance=False
        )
        assert tx.subscription_id == sub.id
        refreshed = await container.subscription_repository.get_by_id(sub.id)
        assert refreshed is not None
        assert refreshed.next_billing_date >= due + timedelta(days=10)
        history = await container.list_transactions.execute(subscription_id=sub.id)
        assert len(history) == 1
        assert await container.delete_subscription_charge.execute(
            history[0].id, subscription_id=sub.id
        )

    run_async(_run())


def test_skip_duplicate_cancel_and_resume_guard(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=5)
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="20", next_billing=due)
        )
        skipped = await container.skip_subscription_period.execute(sub.id)
        assert skipped.next_billing_date > due
        copy = await container.duplicate_subscription.execute(sub.id)
        assert copy.id != sub.id
        assert copy.name.endswith("(copy)")
        assert copy.payments_made == 0
        assert copy.status == SubscriptionStatus.ACTIVE
        cancelled = await container.cancel_subscription.execute(sub.id)
        assert cancelled.status == SubscriptionStatus.CANCELLED
        with pytest.raises(ValueError, match="cannot be resumed"):
            await container.resume_subscription.execute(sub.id)

    run_async(_run())


def test_delete_charge_rolls_back_billing_date(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="200"))
        due = datetime.now(timezone.utc)
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="15", next_billing=due)
        )
        await container.charge_subscription_now.execute(sub.id, check_balance=False)
        after = await container.subscription_repository.get_by_id(sub.id)
        assert after is not None
        next_after = after.next_billing_date
        history = await container.list_transactions.execute(subscription_id=sub.id)
        assert len(history) == 1
        await container.delete_subscription_charge.execute(
            history[0].id, subscription_id=sub.id
        )
        restored = await container.subscription_repository.get_by_id(sub.id)
        assert restored is not None
        assert restored.payments_made == 0
        assert restored.next_billing_date < next_after


def test_update_cannot_cancel_without_cancel_use_case(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=1)
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="20", next_billing=due)
        )
        with pytest.raises(ValueError, match="detail screen"):
            await container.update_subscription.execute(
                sub.model_copy(update={"status": SubscriptionStatus.CANCELLED})
            )
        loaded = await container.get_subscription.execute(sub.id)
        assert loaded.status == SubscriptionStatus.ACTIVE
        paused = await container.update_subscription.execute(
            sub.model_copy(update={"status": SubscriptionStatus.PAUSED})
        )
        assert paused.status == SubscriptionStatus.PAUSED
        cancelled = await container.cancel_subscription.execute(sub.id)
        assert cancelled.status == SubscriptionStatus.CANCELLED
        with pytest.raises(ValueError, match="cannot be resumed"):
            await container.update_subscription.execute(
                cancelled.model_copy(update={"status": SubscriptionStatus.ACTIVE})
            )

    run_async(_run())

    run_async(_run())


def test_charge_now_blocks_expired(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="200"))
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="15")
        )
        await container.update_subscription.execute(
            sub.model_copy(update={"status": SubscriptionStatus.EXPIRED})
        )
        with pytest.raises(ValueError, match="ended"):
            await container.charge_subscription_now.execute(
                sub.id, check_balance=False
            )

    run_async(_run())


def test_catchup_one_period(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        due = datetime.now(timezone.utc) - timedelta(days=95)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="100",
                next_billing=due,
                periodicity=Periodicity.MONTHLY,
            )
        )
        await container.update_subscription.execute(
            sub.model_copy(update={"auto_charge": False})
        )
        txs = await container.process_due_subscriptions.execute(
            subscription_id=sub.id,
            max_charges=1,
            ignore_auto_charge=True,
        )
        assert len(txs) == 1
        refreshed = await container.subscription_repository.get_by_id(sub.id)
        assert refreshed is not None
        assert refreshed.payments_made == 1
        assert refreshed.next_billing_date < datetime.now(timezone.utc)


def test_catchup_all_missed_periods(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        due = datetime.now(timezone.utc) - timedelta(days=95)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="100",
                next_billing=due,
                periodicity=Periodicity.MONTHLY,
            )
        )
        await container.update_subscription.execute(
            sub.model_copy(update={"auto_charge": False})
        )
        txs = await container.process_due_subscriptions.execute(
            subscription_id=sub.id,
            max_charges=0,
            ignore_auto_charge=True,
        )
        assert len(txs) >= 3
        account = await container.account_repository.get_by_id(acc.id)
        assert account is not None
        assert account.balance == Decimal("1000.00") - (Decimal("100.00") * len(txs))

    run_async(_run())


def test_subscription_analytics(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=1)
        await container.create_subscription.execute(
            make_subscription(acc.id, amount="40", next_billing=due)
        )
        await container.process_due_subscriptions.execute()
        stats = await container.get_subscription_analytics.execute(
            base_currency="RUB"
        )
        assert stats.total_active >= 1
        assert stats.total_spent >= Decimal("40.00")
        assert stats.total_monthly_cost >= Decimal("40.00")
        assert stats.total_yearly_cost >= Decimal("480.00")
        assert stats.top_subscriptions
        assert stats.top_subscriptions[0]["icon"]

    run_async(_run())


def test_auto_charge_off_skips_process_due(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=1)
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="40", next_billing=due)
        )
        await container.update_subscription.execute(
            sub.model_copy(update={"auto_charge": False})
        )
        txs = await container.process_due_subscriptions.execute()
        assert txs == []
        account = await container.account_repository.get_by_id(acc.id)
        assert account is not None
        assert account.balance == Decimal("500.00")

    run_async(_run())


def test_end_date_expires_without_charge(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc) - timedelta(days=1)
        sub = await container.create_subscription.execute(
            make_subscription(acc.id, amount="25", next_billing=due)
        )
        # End date clearly before the due billing day (UTC).
        await container.update_subscription.execute(
            sub.model_copy(update={"end_date": (due - timedelta(days=3)).date()})
        )
        txs = await container.process_due_subscriptions.execute()
        assert txs == []
        refreshed = await container.subscription_repository.get_by_id(sub.id)
        assert refreshed is not None
        assert refreshed.status == SubscriptionStatus.EXPIRED

    run_async(_run())


def test_subscription_charge_updates_budget(container) -> None:
    async def _run() -> None:
        now = datetime.now(timezone.utc)
        acc = await container.create_account.execute(make_account(balance="500"))
        # Budget spent is keyed by transaction.date month — keep due in that month
        # (on the 1st, ``now - 1 day`` falls in the previous month).
        due = now - timedelta(days=1)
        if due.month != now.month or due.year != now.year:
            due = now.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="40",
                next_billing=due,
            )
        )
        await container.set_budget.execute(
            sub.name, now.month, now.year, Decimal("200")
        )
        txs = await container.process_due_subscriptions.execute()
        assert len(txs) >= 1
        progress = await container.get_budgets_for_month.execute(now.month, now.year)
        assert progress[0].spent == Decimal("40.00")

    run_async(_run())


def test_subscription_charge_converts_currency(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.currency import ExchangeRate

        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="USD",
                quote="RUB",
                rate=Decimal("100"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        acc = await container.create_account.execute(
            make_account(currency="RUB", balance="1000")
        )
        due = datetime.now(timezone.utc) - timedelta(days=1)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="5",
                currency="USD",
                next_billing=due,
            )
        )
        txs = await container.process_due_subscriptions.execute()
        assert len(txs) >= 1
        assert txs[0].amount == Decimal("500.00")
        assert txs[0].currency == "RUB"
        account = await container.account_repository.get_by_id(acc.id)
        assert account.balance == Decimal("500.00")
        refreshed = await container.subscription_repository.get_by_id(sub.id)
        assert refreshed.payments_made == 1

    run_async(_run())


def test_delete_charge_restores_paused_not_active(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="25",
                next_billing=due,
                max_payments=1,
            )
        )
        await container.pause_subscription.execute(sub.id)
        if container.append_subscription_audit is not None:
            await container.append_subscription_audit.execute(sub.id, "pause")
        tx = await container.charge_subscription_now.execute(
            sub.id, check_balance=False
        )
        expired = await container.subscription_repository.get_by_id(sub.id)
        assert expired is not None
        assert expired.status == SubscriptionStatus.EXPIRED
        if container.append_subscription_audit is not None:
            await container.append_subscription_audit.execute(sub.id, "charge")

        assert await container.delete_subscription_charge.execute(
            tx.id, subscription_id=sub.id
        )
        restored = await container.subscription_repository.get_by_id(sub.id)
        assert restored is not None
        assert restored.status == SubscriptionStatus.PAUSED
        assert restored.is_active is False
        assert restored.payments_made == 0

    run_async(_run())


def test_delete_charge_restores_pause_via_editor_update(container) -> None:
    """ACTIVE→PAUSED through update_subscription must audit as pause."""

    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="500"))
        due = datetime.now(timezone.utc)
        sub = await container.create_subscription.execute(
            make_subscription(
                acc.id,
                amount="25",
                next_billing=due,
                max_payments=1,
            )
        )
        paused = await container.update_subscription.execute(
            sub.model_copy(update={"status": SubscriptionStatus.PAUSED})
        )
        assert paused.status == SubscriptionStatus.PAUSED
        tx = await container.charge_subscription_now.execute(
            sub.id, check_balance=False
        )
        expired = await container.subscription_repository.get_by_id(sub.id)
        assert expired is not None
        assert expired.status == SubscriptionStatus.EXPIRED

        assert await container.delete_subscription_charge.execute(
            tx.id, subscription_id=sub.id
        )
        restored = await container.subscription_repository.get_by_id(sub.id)
        assert restored is not None
        assert restored.status == SubscriptionStatus.PAUSED
        assert restored.is_active is False

    run_async(_run())
