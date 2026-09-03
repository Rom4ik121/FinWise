"""Subscription-related use cases."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from lib.domain.entities.category import Category, CategoryKind
from lib.domain.entities.money import quantize_money
from lib.domain.entities.subscription import (
    Periodicity,
    Subscription,
    SubscriptionStatus,
)
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.category_repository import CategoryRepository
from lib.domain.repositories.currency_repository import CurrencyRepository
from lib.domain.repositories.subscription_repository import SubscriptionRepository
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.domain.services.rate_book import RateBook

if TYPE_CHECKING:
    from lib.domain.repositories.settings_repository import SettingsRepository
    from lib.domain.use_cases.transactions import (
        AddTransactionUseCase,
        DeleteTransactionUseCase,
    )

_DEFAULT_SUB_ICON = "autorenew"
_DEFAULT_SUB_COLOR = "#A78BFA"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _add_months(dt: datetime, months: int) -> datetime:
    """Add calendar months, clamping the day to the target month's length."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def advance_billing_date(
    current: datetime,
    periodicity: Periodicity,
    *,
    custom_interval_days: Optional[int] = None,
) -> datetime:
    """Move billing date forward by one period."""
    current = _as_utc(current)
    if periodicity == Periodicity.DAILY:
        return current + timedelta(days=1)
    if periodicity == Periodicity.WEEKLY:
        return current + timedelta(days=7)
    if periodicity == Periodicity.BIWEEKLY:
        return current + timedelta(days=14)
    if periodicity == Periodicity.MONTHLY:
        return _add_months(current, 1)
    if periodicity == Periodicity.QUARTERLY:
        return _add_months(current, 3)
    if periodicity == Periodicity.SEMI_ANNUAL:
        return _add_months(current, 6)
    if periodicity == Periodicity.YEARLY:
        return _add_months(current, 12)
    if periodicity == Periodicity.CUSTOM:
        days = custom_interval_days or 1
        return current + timedelta(days=days)
    return _add_months(current, 1)


def retreat_billing_date(
    current: datetime,
    periodicity: Periodicity,
    *,
    custom_interval_days: Optional[int] = None,
) -> datetime:
    """Move billing date backward by one period."""
    current = _as_utc(current)
    if periodicity == Periodicity.DAILY:
        return current - timedelta(days=1)
    if periodicity == Periodicity.WEEKLY:
        return current - timedelta(days=7)
    if periodicity == Periodicity.BIWEEKLY:
        return current - timedelta(days=14)
    if periodicity == Periodicity.MONTHLY:
        return _add_months(current, -1)
    if periodicity == Periodicity.QUARTERLY:
        return _add_months(current, -3)
    if periodicity == Periodicity.SEMI_ANNUAL:
        return _add_months(current, -6)
    if periodicity == Periodicity.YEARLY:
        return _add_months(current, -12)
    if periodicity == Periodicity.CUSTOM:
        days = custom_interval_days or 1
        return current - timedelta(days=days)
    return _add_months(current, -1)


def count_missed_periods(
    subscription: Subscription,
    *,
    as_of: Optional[datetime] = None,
) -> int:
    """How many billing periods are overdue (capped at 500)."""
    moment = _as_utc(as_of or _utc_now())
    next_date = _as_utc(subscription.next_billing_date)
    payments = int(subscription.payments_made or 0)
    n = 0
    while next_date <= moment and n < 500:
        billing_day = next_date.date()
        if subscription.end_date is not None and billing_day > subscription.end_date:
            break
        if subscription.max_payments is not None and payments + n >= subscription.max_payments:
            break
        n += 1
        next_date = advance_billing_date(
            next_date,
            subscription.periodicity,
            custom_interval_days=subscription.custom_interval_days,
        )
    return n


def skip_missed_to_future(
    subscription: Subscription,
    *,
    as_of: Optional[datetime] = None,
) -> datetime:
    """Advance ``next_billing_date`` past ``as_of`` without charging."""
    moment = _as_utc(as_of or _utc_now())
    next_date = _as_utc(subscription.next_billing_date)
    safety = 0
    while next_date <= moment and safety < 500:
        next_date = advance_billing_date(
            next_date,
            subscription.periodicity,
            custom_interval_days=subscription.custom_interval_days,
        )
        safety += 1
    return next_date


def assert_subscription_chargeable(subscription: Subscription) -> None:
    """Raise when the subscription cannot receive a charge."""
    status = (
        subscription.status
        if isinstance(subscription.status, SubscriptionStatus)
        else SubscriptionStatus(str(subscription.status))
    )
    if status == SubscriptionStatus.EXPIRED:
        raise ValueError("Subscription has ended")
    if status == SubscriptionStatus.CANCELLED:
        raise ValueError("Subscription is cancelled")
    if status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED):
        raise ValueError("Subscription cannot be charged")
    if (
        subscription.max_payments is not None
        and int(subscription.payments_made or 0) >= subscription.max_payments
    ):
        raise ValueError("Subscription payment limit reached")


# Backward-compatible alias used by unit tests.
_advance_billing_date = advance_billing_date


def monthly_equivalent(
    amount: Decimal,
    periodicity: Periodicity,
    *,
    custom_interval_days: Optional[int] = None,
) -> Decimal:
    """Convert a subscription amount into an approximate monthly cost."""
    amount = quantize_money(amount)
    if periodicity == Periodicity.DAILY:
        return quantize_money(amount * Decimal("30.4375"))
    if periodicity == Periodicity.WEEKLY:
        return quantize_money(amount * Decimal("52") / Decimal("12"))
    if periodicity == Periodicity.BIWEEKLY:
        return quantize_money(amount * Decimal("26") / Decimal("12"))
    if periodicity == Periodicity.MONTHLY:
        return amount
    if periodicity == Periodicity.QUARTERLY:
        return quantize_money(amount / Decimal("3"))
    if periodicity == Periodicity.SEMI_ANNUAL:
        return quantize_money(amount / Decimal("6"))
    if periodicity == Periodicity.YEARLY:
        return quantize_money(amount / Decimal("12"))
    if periodicity == Periodicity.CUSTOM:
        days = max(1, int(custom_interval_days or 1))
        return quantize_money(amount * Decimal("30.4375") / Decimal(days))
    return amount


def _sync_active(status: SubscriptionStatus) -> bool:
    return status == SubscriptionStatus.ACTIVE


def subscription_charge_category(subscription: Subscription) -> str:
    """Ledger category for a charge: the subscription name."""
    return (subscription.name or subscription.category or "").strip() or "Subscription"


async def sync_subscription_category(
    categories: Optional[CategoryRepository],
    subscription: Subscription,
) -> str:
    """Create or refresh an expense category with the subscription name and icon."""
    name = subscription_charge_category(subscription)
    if categories is None:
        return name
    icon = getattr(subscription, "icon", None) or _DEFAULT_SUB_ICON
    color = getattr(subscription, "color", None) or _DEFAULT_SUB_COLOR
    existing = await categories.get_by_name(name)
    if existing is None:
        await categories.create(
            Category(
                name=name,
                icon=icon,
                color=color,
                kind=CategoryKind.EXPENSE,
            )
        )
        return name
    if existing.is_system:
        return name
    updates: dict[str, object] = {}
    if existing.icon != icon:
        updates["icon"] = icon
    if existing.color != color:
        updates["color"] = color
    if not existing.is_active:
        updates["is_active"] = True
    if updates:
        updates["updated_at"] = _utc_now()
        await categories.update(existing.model_copy(update=updates))
    return name


class CreateSubscriptionUseCase:
    """Create a recurring subscription."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        categories: Optional[CategoryRepository] = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._categories = categories

    async def execute(self, subscription: Subscription) -> Subscription:
        """Persist a new subscription."""
        status = subscription.status or SubscriptionStatus.ACTIVE
        name = (subscription.name or "").strip() or "Subscription"
        created = subscription.model_copy(
            update={
                "name": name,
                "category": name,
                "amount": quantize_money(subscription.amount),
                "status": status,
                "is_active": _sync_active(status),
                "payments_made": int(subscription.payments_made or 0),
                "created_at": subscription.created_at or _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        saved = await self._subscriptions.create(created)
        await sync_subscription_category(self._categories, saved)
        return saved


class UpdateSubscriptionUseCase:
    """Update an existing subscription."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        categories: Optional[CategoryRepository] = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._categories = categories

    async def execute(self, subscription: Subscription) -> Subscription:
        """Update subscription fields."""
        existing = await self._subscriptions.get_by_id(subscription.id)
        if existing is None:
            raise ValueError(f"Subscription not found: {subscription.id}")
        status = subscription.status or existing.status
        if (
            existing.status == SubscriptionStatus.CANCELLED
            and status != SubscriptionStatus.CANCELLED
        ):
            raise ValueError("Cancelled subscription cannot be resumed")
        if (
            existing.status == SubscriptionStatus.EXPIRED
            and status != SubscriptionStatus.EXPIRED
        ):
            raise ValueError("Subscription has ended")
        if (
            status == SubscriptionStatus.CANCELLED
            and existing.status != SubscriptionStatus.CANCELLED
        ):
            raise ValueError("Cancel a subscription from the detail screen")
        name = (subscription.name or existing.name or "").strip() or "Subscription"
        updated = subscription.model_copy(
            update={
                "name": name,
                "category": name,
                "amount": quantize_money(subscription.amount),
                "status": status,
                "is_active": _sync_active(status),
                "updated_at": _utc_now(),
                "created_at": existing.created_at,
                "payments_made": subscription.payments_made,
            }
        )
        saved = await self._subscriptions.update(updated)
        await sync_subscription_category(self._categories, saved)
        return saved


class DeleteSubscriptionUseCase:
    """Delete a subscription."""

    def __init__(self, subscriptions: SubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def execute(self, subscription_id: str) -> bool:
        """Remove a subscription by id."""
        return await self._subscriptions.delete(subscription_id)


class ListSubscriptionsUseCase:
    """List subscriptions."""

    def __init__(self, subscriptions: SubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def execute(
        self,
        *,
        active_only: bool = False,
        account_id: Optional[str] = None,
        status: Optional[SubscriptionStatus] = None,
    ) -> list[Subscription]:
        """Return subscriptions with optional filters."""
        return await self._subscriptions.list(
            active_only=active_only,
            account_id=account_id,
            status=status,
        )


class GetSubscriptionUseCase:
    """Fetch one subscription by id."""

    def __init__(self, subscriptions: SubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def execute(self, subscription_id: str) -> Subscription:
        sub = await self._subscriptions.get_by_id(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        return sub


class PauseSubscriptionUseCase:
    """Pause an active subscription (billing stops, next date kept)."""

    def __init__(self, subscriptions: SubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def execute(self, subscription_id: str) -> Subscription:
        sub = await self._subscriptions.get_by_id(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        if sub.status != SubscriptionStatus.ACTIVE:
            return sub
        updated = sub.model_copy(
            update={
                "status": SubscriptionStatus.PAUSED,
                "is_active": False,
                "updated_at": _utc_now(),
            }
        )
        return await self._subscriptions.update(updated)


class ResumeSubscriptionUseCase:
    """Resume a paused subscription and skip missed periods without charging."""

    def __init__(self, subscriptions: SubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def execute(
        self,
        subscription_id: str,
        *,
        as_of: Optional[datetime] = None,
    ) -> Subscription:
        sub = await self._subscriptions.get_by_id(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        if sub.status != SubscriptionStatus.PAUSED:
            if sub.status == SubscriptionStatus.CANCELLED:
                raise ValueError("Cancelled subscription cannot be resumed")
            return sub

        moment = _as_utc(as_of or _utc_now())
        next_date = skip_missed_to_future(sub, as_of=moment)

        updated = sub.model_copy(
            update={
                "status": SubscriptionStatus.ACTIVE,
                "is_active": True,
                "next_billing_date": next_date,
                "updated_at": _utc_now(),
            }
        )
        return await self._subscriptions.update(updated)


class ChargeSubscriptionNowUseCase:
    """Force a single charge for a subscription (optional balance check)."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        accounts: AccountRepository,
        add_transaction: "AddTransactionUseCase",
        currencies: CurrencyRepository,
        settings: Optional["SettingsRepository"] = None,
        categories: Optional[CategoryRepository] = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._accounts = accounts
        self._add = add_transaction
        self._currencies = currencies
        self._settings = settings
        self._categories = categories

    async def execute(
        self,
        subscription_id: str,
        *,
        check_balance: Optional[bool] = None,
        language: str = "ru",
        notifier: Any = None,
    ) -> Transaction:
        sub = await self._subscriptions.get_by_id(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        assert_subscription_chargeable(sub)
        if sub.end_date is not None and _utc_now().date() > sub.end_date:
            raise ValueError("Subscription has ended")

        account = await self._accounts.get_by_id(sub.account_id)
        if account is None:
            raise ValueError(f"Account not found: {sub.account_id}")

        if check_balance is None and self._settings is not None:
            settings = await self._settings.get()
            check_balance = bool(
                getattr(settings, "check_balance_before_subscription", True)
            )
        if check_balance is None:
            check_balance = True

        amount = quantize_money(sub.amount)
        sub_currency = sub.currency or account.currency
        cash_amount = await _subscription_cash_amount(
            self._currencies,
            amount=amount,
            from_currency=sub_currency,
            to_currency=account.currency,
        )
        if check_balance and account.balance < cash_amount:
            raise ValueError("insufficient_funds")

        now = _utc_now()
        category = await sync_subscription_category(self._categories, sub)
        saved = await self._add.execute(
            Transaction(
                account_id=sub.account_id,
                amount=cash_amount,
                category=category,
                tags=["subscription"],
                date=now,
                comment=sub.comment or f"Subscription: {sub.name}",
                type=TransactionType.EXPENSE,
                currency=account.currency,
                subscription_id=sub.id,
                created_at=now,
                updated_at=now,
            )
        )

        next_date = advance_billing_date(
            _as_utc(sub.next_billing_date),
            sub.periodicity,
            custom_interval_days=sub.custom_interval_days,
        )
        payments_made = int(sub.payments_made or 0) + 1
        status = sub.status
        expired = False
        if sub.end_date is not None and next_date.date() > sub.end_date:
            expired = True
        if sub.max_payments is not None and payments_made >= sub.max_payments:
            expired = True
        if expired:
            status = SubscriptionStatus.EXPIRED
        updated = sub.model_copy(
            update={
                "last_charged_at": now,
                "next_billing_date": next_date,
                "payments_made": payments_made,
                "status": status,
                "is_active": _sync_active(status),
                "updated_at": now,
            }
        )
        await self._subscriptions.update(updated)
        return saved


async def _subscription_cash_amount(
    currencies: CurrencyRepository,
    *,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
) -> Decimal:
    """Convert subscription amount into account currency."""
    if from_currency.upper() == to_currency.upper():
        return quantize_money(amount)
    rates = await currencies.list_rates()
    converted = RateBook(rates).convert(amount, from_currency, to_currency)
    if converted is None:
        raise ValueError(f"No exchange rate for {from_currency}/{to_currency}")
    return quantize_money(converted)


class DeleteSubscriptionChargeUseCase:
    """Delete a subscription charge transaction (no next_billing_date recalculation)."""

    def __init__(
        self,
        transactions: TransactionRepository,
        subscriptions: SubscriptionRepository,
        delete_transaction: "DeleteTransactionUseCase",
    ) -> None:
        self._transactions = transactions
        self._subscriptions = subscriptions
        self._delete_transaction = delete_transaction

    async def execute(self, transaction_id: str, *, subscription_id: str) -> bool:
        tx = await self._transactions.get_by_id(transaction_id)
        if tx is None:
            return False
        if tx.subscription_id != subscription_id:
            raise ValueError("Transaction is not linked to this subscription")

        deleted = await self._delete_transaction.execute(transaction_id)
        if not deleted:
            return False

        sub = await self._subscriptions.get_by_id(subscription_id)
        if sub is None:
            return True

        remaining = await self._transactions.list(
            subscription_id=subscription_id,
            limit=1,
            offset=0,
        )
        last_charged = remaining[0].date if remaining else None
        payments = max(0, int(sub.payments_made or 0) - 1)
        next_date = retreat_billing_date(
            _as_utc(sub.next_billing_date),
            sub.periodicity,
            custom_interval_days=sub.custom_interval_days,
        )
        status = sub.status
        if status == SubscriptionStatus.EXPIRED:
            under_max = (
                sub.max_payments is None or payments < sub.max_payments
            )
            before_end = (
                sub.end_date is None or next_date.date() <= sub.end_date
            )
            if under_max and before_end:
                status = SubscriptionStatus.ACTIVE
        updated = sub.model_copy(
            update={
                "last_charged_at": last_charged,
                "payments_made": payments,
                "next_billing_date": next_date,
                "status": status,
                "is_active": _sync_active(status),
                "updated_at": _utc_now(),
            }
        )
        await self._subscriptions.update(updated)
        return True


class ProcessDueSubscriptionsUseCase:
    """Charge due subscriptions as expense transactions and advance billing dates."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        accounts: AccountRepository,
        settings: Optional["SettingsRepository"] = None,
        add_transaction: Optional["AddTransactionUseCase"] = None,
        currencies: Optional[CurrencyRepository] = None,
        categories: Optional[CategoryRepository] = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._accounts = accounts
        self._settings = settings
        self._add = add_transaction
        self._currencies = currencies
        self._categories = categories

    async def execute(
        self,
        *,
        as_of: Optional[datetime] = None,
        language: str = "ru",
        notifier: Any = None,
        subscription_id: Optional[str] = None,
        max_charges: Optional[int] = 1,
        ignore_auto_charge: bool = False,
    ) -> list[Transaction]:
        """Process due subscriptions (or one subscription for catch-up).

        ``max_charges`` limits overdue periods billed in one run.
        Default ``1`` so a background catch-up cannot drain the account;
        pass ``0`` (or a negative value) to charge every missed period.
        """
        if self._add is None or self._currencies is None:
            raise RuntimeError("Subscription charging is not configured")
        as_of = _as_utc(as_of or _utc_now())
        check_balance = True
        if self._settings is not None:
            settings = await self._settings.get()
            check_balance = bool(
                getattr(settings, "check_balance_before_subscription", True)
            )

        if subscription_id:
            one = await self._subscriptions.get_by_id(subscription_id)
            due = [one] if one is not None else []
        else:
            due = await self._subscriptions.list_due(as_of)
        created_txs: list[Transaction] = []

        # Prefetch accounts once to avoid N+1 lookups.
        account_ids = {sub.account_id for sub in due if sub is not None}
        accounts_by_id: dict[str, Any] = {}
        if account_ids:
            for account in await self._accounts.list(active_only=False):
                if account.id in account_ids:
                    accounts_by_id[account.id] = account

        if max_charges is None:
            charge_cap = 1
        elif max_charges <= 0:
            charge_cap = 10_000
        else:
            charge_cap = int(max_charges)

        for sub in due:
            if sub is None:
                continue
            if sub.status == SubscriptionStatus.CANCELLED:
                continue
            if sub.status == SubscriptionStatus.EXPIRED:
                continue
            if (
                sub.status != SubscriptionStatus.ACTIVE
                and not ignore_auto_charge
            ):
                continue
            if not ignore_auto_charge and not sub.is_active:
                continue
            if not ignore_auto_charge and not bool(getattr(sub, "auto_charge", True)):
                continue

            account = accounts_by_id.get(sub.account_id)
            if account is None:
                continue
            category = await sync_subscription_category(self._categories, sub)

            amount = quantize_money(sub.amount)
            sub_currency = sub.currency or account.currency
            next_date = _as_utc(sub.next_billing_date)
            payments_made = int(sub.payments_made or 0)
            charged_any = False
            expired = False
            charged_count = 0

            while next_date <= as_of and charged_count < charge_cap:
                billing_day = next_date.date()
                if sub.end_date is not None and billing_day > sub.end_date:
                    expired = True
                    break
                if sub.max_payments is not None and payments_made >= sub.max_payments:
                    expired = True
                    break

                try:
                    cash_amount = await _subscription_cash_amount(
                        self._currencies,
                        amount=amount,
                        from_currency=sub_currency,
                        to_currency=account.currency,
                    )
                except ValueError:
                    sub = sub.model_copy(
                        update={
                            "last_skip_date": billing_day,
                            "updated_at": _utc_now(),
                        }
                    )
                    await self._subscriptions.update(sub)
                    break

                if check_balance and account.balance < cash_amount:
                    sub = sub.model_copy(
                        update={
                            "last_skip_date": billing_day,
                            "updated_at": _utc_now(),
                        }
                    )
                    await self._subscriptions.update(sub)
                    self._notify_insufficient(
                        notifier,
                        sub,
                        account_name=getattr(account, "name", ""),
                        language=language,
                    )
                    # Do not advance billing — retry next run for this period.
                    break

                now = _utc_now()
                saved_tx = await self._add.execute(
                    Transaction(
                        account_id=sub.account_id,
                        amount=cash_amount,
                        category=category,
                        tags=["subscription"],
                        date=next_date,
                        comment=sub.comment or f"Subscription: {sub.name}",
                        type=TransactionType.EXPENSE,
                        currency=account.currency,
                        subscription_id=sub.id,
                        created_at=now,
                        updated_at=now,
                    )
                )
                refreshed = await self._accounts.get_by_id(account.id)
                if refreshed is not None:
                    account = refreshed
                    accounts_by_id[account.id] = account
                created_txs.append(saved_tx)
                charged_any = True
                charged_count += 1
                payments_made += 1
                sub.last_charged_at = now
                next_date = advance_billing_date(
                    next_date,
                    sub.periodicity,
                    custom_interval_days=sub.custom_interval_days,
                )

            if expired:
                sub = sub.model_copy(
                    update={
                        "status": SubscriptionStatus.EXPIRED,
                        "is_active": False,
                        "next_billing_date": next_date,
                        "payments_made": payments_made,
                        "updated_at": _utc_now(),
                    }
                )
                await self._subscriptions.update(sub)
                self._notify_expired(notifier, sub, language=language)
                continue

            if charged_any:
                sub = sub.model_copy(
                    update={
                        "next_billing_date": next_date,
                        "payments_made": payments_made,
                        "last_charged_at": sub.last_charged_at,
                        "updated_at": _utc_now(),
                    }
                )
                await self._subscriptions.update(sub)

        return created_txs

    @staticmethod
    def _notify_insufficient(
        notifier: Any,
        sub: Subscription,
        *,
        account_name: str,
        language: str,
    ) -> None:
        if notifier is None:
            return
        notify = getattr(notifier, "notify_subscription_skipped", None)
        if not callable(notify):
            return
        try:
            notify(sub, account_name=account_name, language=language)
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _notify_expired(notifier: Any, sub: Subscription, *, language: str) -> None:
        if notifier is None:
            return
        notify = getattr(notifier, "notify_subscription_expired", None)
        if not callable(notify):
            return
        try:
            notify(sub, language=language)
        except Exception:  # noqa: BLE001
            return


class SubscriptionAnalytics(BaseModel):
    """Aggregated subscription metrics for analytics screens."""

    total_spent: Decimal = Decimal("0")
    monthly_trend: list[dict[str, object]] = Field(default_factory=list)
    top_subscriptions: list[dict[str, object]] = Field(default_factory=list)
    total_active: int = 0
    total_monthly_cost: Decimal = Decimal("0")
    total_yearly_cost: Decimal = Decimal("0")
    currency: str = "RUB"


class GetSubscriptionAnalyticsUseCase:
    """Compute spend / trend / top / monthly cost for subscriptions."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        transactions: TransactionRepository,
        currencies: "CurrencyRepository",
    ) -> None:
        self._subscriptions = subscriptions
        self._transactions = transactions
        self._currencies = currencies

    async def execute(
        self,
        *,
        base_currency: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> SubscriptionAnalytics:
        rates = await self._currencies.list_rates()
        book = RateBook(rates)
        base = (base_currency or "RUB").upper()

        subs = await self._subscriptions.list(active_only=False)
        active = [s for s in subs if s.status == SubscriptionStatus.ACTIVE]
        sub_by_id = {s.id: s for s in subs}
        monthly_cost = Decimal("0")
        monthly_by_id: dict[str, Decimal] = {}
        for sub in active:
            monthly = monthly_equivalent(
                sub.amount,
                sub.periodicity,
                custom_interval_days=sub.custom_interval_days,
            )
            converted = book.convert(monthly, sub.currency, base)
            if converted is None and sub.currency.upper() == base:
                converted = monthly
            if converted is None:
                monthly_by_id[sub.id] = Decimal("0")
                continue
            monthly_by_id[sub.id] = converted
            monthly_cost += converted

        # Prefer FK-linked charges; fall back to legacy tagged expenses.
        charge_txs = await self._transactions.list(
            date_from=date_from,
            date_to=date_to,
            has_subscription=True,
        )
        if not charge_txs:
            charge_txs = await self._transactions.list(
                date_from=date_from,
                date_to=date_to,
                tags=["subscription"],
            )

        total_spent = Decimal("0")
        per_sub: dict[str, Decimal] = {}
        trend_map: dict[str, Decimal] = {}

        for tx in charge_txs:
            if tx.type != TransactionType.EXPENSE:
                continue
            converted = book.convert(tx.amount, tx.currency, base)
            if converted is None and tx.currency.upper() == base:
                converted = tx.amount
            if converted is None:
                continue
            total_spent += converted
            key = tx.subscription_id or tx.comment or tx.id
            per_sub[key] = per_sub.get(key, Decimal("0")) + converted
            month_key = _as_utc(tx.date).strftime("%Y-%m")
            trend_map[month_key] = trend_map.get(month_key, Decimal("0")) + converted

        keys: set[str] = set(per_sub) | {s.id for s in active}
        ranked: list[tuple[str, Decimal, Decimal]] = []
        for sid in keys:
            spent = per_sub.get(sid, Decimal("0"))
            monthly_amt = monthly_by_id.get(sid, Decimal("0"))
            ranked.append((sid, spent, monthly_amt))
        ranked.sort(key=lambda item: (item[1], item[2]), reverse=True)
        top_subscriptions = []
        for sid, spent, monthly_amt in ranked[:12]:
            sub = sub_by_id.get(sid)
            share = (
                float(spent / total_spent) if total_spent > 0 and spent > 0 else 0.0
            )
            icon = "autorenew"
            color = "#A78BFA"
            label = str(sid)
            if sub is not None:
                label = sub.name
                icon = getattr(sub, "icon", None) or icon
                color = getattr(sub, "color", None) or color
            top_subscriptions.append(
                {
                    "id": sid,
                    "name": label,
                    "amount": quantize_money(spent),
                    "monthly": quantize_money(monthly_amt),
                    "icon": icon,
                    "color": color,
                    "share": share,
                }
            )

        # Build last-12-months trend (or span of filtered period).
        end = _as_utc(date_to or _utc_now())
        months: list[dict[str, object]] = []
        cursor = date(end.year, end.month, 1)
        for _ in range(12):
            key = f"{cursor.year:04d}-{cursor.month:02d}"
            months.append(
                {
                    "month": key,
                    "sum": quantize_money(trend_map.get(key, Decimal("0"))),
                }
            )
            if cursor.month == 1:
                cursor = date(cursor.year - 1, 12, 1)
            else:
                cursor = date(cursor.year, cursor.month - 1, 1)
        months.reverse()

        return SubscriptionAnalytics(
            total_spent=quantize_money(total_spent),
            monthly_trend=months,
            top_subscriptions=top_subscriptions,
            total_active=len(active),
            total_monthly_cost=quantize_money(monthly_cost),
            total_yearly_cost=quantize_money(monthly_cost * Decimal("12")),
            currency=base,
        )


class SkipSubscriptionPeriodUseCase:
    """Advance the next billing date without creating a charge."""

    def __init__(self, subscriptions: SubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def execute(
        self,
        subscription_id: str,
        *,
        skip_all_missed: bool = False,
        as_of: Optional[datetime] = None,
    ) -> Subscription:
        sub = await self._subscriptions.get_by_id(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED):
            raise ValueError("Subscription cannot be charged")
        moment = _as_utc(as_of or _utc_now())
        if skip_all_missed:
            next_date = skip_missed_to_future(sub, as_of=moment)
        else:
            next_date = advance_billing_date(
                _as_utc(sub.next_billing_date),
                sub.periodicity,
                custom_interval_days=sub.custom_interval_days,
            )
        status = sub.status
        if sub.end_date is not None and next_date.date() > sub.end_date:
            status = SubscriptionStatus.EXPIRED
        updated = sub.model_copy(
            update={
                "next_billing_date": next_date,
                "last_skip_date": moment.date(),
                "status": status,
                "is_active": _sync_active(status),
                "updated_at": _utc_now(),
            }
        )
        return await self._subscriptions.update(updated)


class DuplicateSubscriptionUseCase:
    """Create a copy with a fresh schedule and zero payment count."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        categories: Optional[CategoryRepository] = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._categories = categories

    async def execute(
        self, subscription_id: str, *, name_suffix: str = " (copy)"
    ) -> Subscription:
        source = await self._subscriptions.get_by_id(subscription_id)
        if source is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        now = _utc_now()
        new_name = f"{source.name}{name_suffix}"
        copy = source.model_copy(
            update={
                "id": str(uuid4()),
                "name": new_name,
                "category": new_name,
                "status": SubscriptionStatus.ACTIVE,
                "is_active": True,
                "payments_made": 0,
                "last_charged_at": None,
                "last_skip_date": None,
                "next_billing_date": now,
                "created_at": now,
                "updated_at": now,
            }
        )
        saved = await self._subscriptions.create(
            Subscription.model_validate(copy.model_dump())
        )
        await sync_subscription_category(self._categories, saved)
        return saved


class CancelSubscriptionUseCase:
    """Mark a subscription cancelled (history kept, billing stops)."""

    def __init__(self, subscriptions: SubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def execute(self, subscription_id: str) -> Subscription:
        sub = await self._subscriptions.get_by_id(subscription_id)
        if sub is None:
            raise ValueError(f"Subscription not found: {subscription_id}")
        if sub.status == SubscriptionStatus.CANCELLED:
            return sub
        updated = sub.model_copy(
            update={
                "status": SubscriptionStatus.CANCELLED,
                "is_active": False,
                "updated_at": _utc_now(),
            }
        )
        return await self._subscriptions.update(updated)


class AppendSubscriptionAuditUseCase:
    """Record a subscription audit log entry."""

    def __init__(self, audit_repository) -> None:
        self._audit = audit_repository

    async def execute(
        self,
        subscription_id: str,
        action: str,
        *,
        details: dict | None = None,
    ) -> None:
        from lib.domain.entities.subscription_audit import SubscriptionAuditEntry

        await self._audit.append(
            SubscriptionAuditEntry(
                subscription_id=subscription_id,
                action=action,
                details=details,
            )
        )


class ListSubscriptionAuditUseCase:
    """List audit entries for one subscription."""

    def __init__(self, audit_repository) -> None:
        self._audit = audit_repository

    async def execute(self, subscription_id: str, *, limit: int = 30) -> list:
        return await self._audit.list_for_subscription(subscription_id, limit=limit)

