"""Transaction-related use cases."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Callable, Optional, Sequence

from pydantic import BaseModel, Field

from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.budget_repository import BudgetRepository
from lib.domain.repositories.currency_repository import CurrencyRepository
from lib.domain.repositories.debt_repository import DebtRepository
from lib.domain.repositories.goal_repository import GoalRepository
from lib.domain.repositories.settings_repository import SettingsRepository
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.domain.use_cases.debts import (
    apply_debt_payment_credit,
    assert_debt_accepts_ledger,
    debt_credit_amount,
    is_debt_principal_tx,
    reverse_debt_payment_credit,
)
from lib.domain.use_cases.goals import (
    allocate_goal_contribution_credit,
    apply_goal_contribution_credit,
    assert_goal_accepts_ledger,
    encode_goal_allocation_tags,
    goal_credit_amount,
    has_goal_allocation_tag_markers,
    parse_goal_allocation_tags,
    reverse_goal_contribution_credit,
    strip_goal_allocation_tags,
)
from lib.domain.unit_of_work import in_unit_of_work, unit_of_work

FEE_CATEGORY = "Комиссия"
TRANSFER_FEE_TAG_PREFIX = "xfer_fee:"


def transfer_fee_tag(transfer_id: str) -> str:
    """Stable tag linking a fee expense to its transfer."""
    return f"{TRANSFER_FEE_TAG_PREFIX}{transfer_id}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _balance_delta(tx_type: TransactionType, amount: Decimal) -> Decimal:
    """Return signed balance change for an account (income +, expense −)."""
    amount = quantize_money(amount)
    if tx_type == TransactionType.INCOME:
        return amount
    return -amount


def _is_goal_contribution(transaction: Transaction) -> bool:
    return transaction.type == TransactionType.EXPENSE and bool(transaction.goal_id)


def _is_goal_withdrawal(transaction: Transaction) -> bool:
    return transaction.type == TransactionType.INCOME and bool(transaction.goal_id)


async def _credit_goal_from_transaction(
    *,
    goals: GoalRepository,
    transactions: TransactionRepository,
    transaction: Transaction,
) -> Transaction:
    """Apply contribution and persist allocation tags atomically (same UoW).

    Goal progress and ``goal_alloc:`` tags are written in one unit of work so a
    failed tag write rolls back the goal credit (no partial state).
    """
    if not _is_goal_contribution(transaction):
        return transaction
    goal = await goals.get_by_id(transaction.goal_id or "")
    if goal is None:
        return transaction
    credit = goal_credit_amount(transaction)
    updated, allocations = allocate_goal_contribution_credit(
        goal,
        credit,
        item_id=transaction.goal_item_id,
    )
    if goal.items and not allocations:
        raise ValueError("Goal allocation tags are required")
    clean = strip_goal_allocation_tags(transaction.tags)
    if allocations:
        tagged = transaction.model_copy(
            update={"tags": clean + encode_goal_allocation_tags(allocations)}
        )
    else:
        tagged = (
            transaction.model_copy(update={"tags": clean})
            if clean != list(transaction.tags or [])
            else transaction
        )

    # Persist goal + tagged row together; callers wrap in unit_of_work.
    await goals.update(updated)
    if tagged is transaction and not allocations:
        return transaction
    return await transactions.update(tagged)


async def _debit_goal_from_transaction(
    *,
    goals: GoalRepository,
    transaction: Transaction,
) -> None:
    """Reverse contribution using stored allocations when present."""
    if not _is_goal_contribution(transaction):
        return
    goal = await goals.get_by_id(transaction.goal_id or "")
    if goal is None:
        return
    credit = goal_credit_amount(transaction)
    markers = has_goal_allocation_tag_markers(transaction.tags)
    parsed = parse_goal_allocation_tags(transaction.tags)
    if markers and parsed is None:
        mode = "primary_only"
        allocations = None
    elif parsed is not None:
        mode = "exact"
        allocations = parsed
    else:
        mode = "lifo"
        allocations = None
    updated = reverse_goal_contribution_credit(
        goal,
        credit,
        item_id=transaction.goal_item_id,
        allocations=allocations,
        allocation_mode=mode,
    )
    await goals.update(updated)


async def _with_goal_credit(
    transaction: Transaction,
    *,
    goals: GoalRepository,
    currencies: Optional[CurrencyRepository],
    accounts: AccountRepository,
) -> Transaction:
    """Ensure ``goal_credit_amount`` is set in the goal's currency when linked."""
    if not (_is_goal_contribution(transaction) or _is_goal_withdrawal(transaction)):
        return transaction.model_copy(
            update={"goal_id": None, "goal_credit_amount": None}
        )
    if transaction.goal_credit_amount is not None:
        return transaction
    goal = await goals.get_by_id(transaction.goal_id or "")
    if goal is None:
        raise ValueError(f"Goal not found: {transaction.goal_id}")
    account = await accounts.get_by_id(transaction.account_id)
    src = (transaction.currency or (account.currency if account else "") or "RUB")
    dst = goal.currency or "RUB"
    if src.upper() == dst.upper():
        return transaction.model_copy(
            update={"goal_credit_amount": quantize_money(transaction.amount)}
        )
    if currencies is None:
        raise ValueError(f"No exchange rate for {src}/{dst}")
    from lib.domain.services.rate_cache import get_cached_rate_book

    book = await get_cached_rate_book(currencies)
    credit = book.convert(transaction.amount, src, dst)
    if credit is None:
        raise ValueError(f"No exchange rate for {src}/{dst}")
    return transaction.model_copy(
        update={"goal_credit_amount": quantize_money(credit)}
    )


async def _with_debt_credit(
    transaction: Transaction,
    *,
    debts: DebtRepository,
    currencies: Optional[CurrencyRepository],
    accounts: AccountRepository,
) -> Transaction:
    """Ensure ``debt_credit_amount`` is set in the debt's currency when linked."""
    if is_debt_principal_tx(transaction):
        return transaction
    if not _is_debt_payment(transaction):
        return transaction.model_copy(
            update={"debt_id": None, "debt_credit_amount": None}
        )
    if transaction.debt_credit_amount is not None:
        return transaction
    debt = await debts.get_by_id(transaction.debt_id or "")
    if debt is None:
        raise ValueError(f"Debt not found: {transaction.debt_id}")
    account = await accounts.get_by_id(transaction.account_id)
    src = (transaction.currency or (account.currency if account else "") or "RUB")
    dst = debt.currency or "RUB"
    if src.upper() == dst.upper():
        return transaction.model_copy(
            update={"debt_credit_amount": quantize_money(transaction.amount)}
        )
    if currencies is None:
        raise ValueError(f"No exchange rate for {src}/{dst}")
    from lib.domain.services.rate_cache import get_cached_rate_book

    book = await get_cached_rate_book(currencies)
    credit = book.convert(transaction.amount, src, dst)
    if credit is None:
        raise ValueError(f"No exchange rate for {src}/{dst}")
    return transaction.model_copy(
        update={"debt_credit_amount": quantize_money(credit)}
    )


async def _validate_goal_link(
    transaction: Transaction,
    *,
    goals: GoalRepository,
    existing: Transaction | None = None,
) -> None:
    if not transaction.goal_id:
        return
    if not (
        _is_goal_contribution(transaction) or _is_goal_withdrawal(transaction)
    ):
        return
    if existing is not None and existing.goal_id == transaction.goal_id:
        return
    goal = await goals.get_by_id(transaction.goal_id)
    if goal is None:
        raise ValueError(f"Goal not found: {transaction.goal_id}")
    assert_goal_accepts_ledger(goal)


def _debt_payment_unchanged(
    existing: Transaction,
    transaction: Transaction,
) -> bool:
    return (
        existing.debt_id == transaction.debt_id
        and existing.amount == transaction.amount
        and existing.debt_credit_amount == transaction.debt_credit_amount
        and existing.type == transaction.type
        and (existing.tags or []) == (transaction.tags or [])
    )


async def _validate_debt_link(
    transaction: Transaction,
    *,
    debts: DebtRepository,
    existing: Transaction | None = None,
) -> None:
    if not transaction.debt_id:
        return
    if not _is_debt_payment(transaction):
        return
    if existing is not None and _debt_payment_unchanged(existing, transaction):
        return
    debt = await debts.get_by_id(transaction.debt_id)
    if debt is None:
        raise ValueError(f"Debt not found: {transaction.debt_id}")
    assert_debt_accepts_ledger(debt)


def _is_debt_payment(transaction: Transaction) -> bool:
    """True for repayments that reduce remaining — not principal openers."""
    if not transaction.debt_id:
        return False
    from lib.domain.use_cases.debts import is_debt_principal_tx

    if is_debt_principal_tx(transaction):
        return False
    return True


async def _sync_budget_expense(
    budgets: Optional[BudgetRepository],
    transaction: Transaction,
    *,
    sign: int,
    settings_repo: Optional[SettingsRepository] = None,
    notifications: object = None,
    currencies: Optional[CurrencyRepository] = None,
    accounts: Optional[object] = None,
) -> None:
    """Apply or reverse an expense against the matching monthly budget(s).

    Multi-line transactions sync each line's category separately so a
    supermarket basket can hit Food + Tobacco budgets in one receipt.
    Corporate account expenses only touch corporate-scoped budgets.
    """
    if budgets is None or transaction.type != TransactionType.EXPENSE:
        return
    if transaction.transfer_id:
        return
    if any(
        str(tag).startswith(TRANSFER_FEE_TAG_PREFIX)
        for tag in (transaction.tags or [])
    ):
        return
    if transaction.goal_id or transaction.goal_credit_amount is not None:
        return
    from lib.domain.use_cases.budgets import apply_expense_delta

    settings = None
    language = "ru"
    currency = "RUB"
    rate_book = None
    if settings_repo is not None:
        try:
            settings = await settings_repo.get()
            language = settings.language
            currency = settings.default_currency
        except Exception:  # noqa: BLE001
            settings = None
    if currencies is not None:
        try:
            from lib.domain.services.rate_cache import get_cached_rate_book

            rate_book = await get_cached_rate_book(currencies)
        except Exception:  # noqa: BLE001
            rate_book = None

    budget_account_id: Optional[str] = None
    get_account = getattr(accounts, "get_by_id", None) if accounts is not None else None
    if callable(get_account):
        try:
            account = await get_account(transaction.account_id)
            if account is not None and getattr(account, "is_corporate", False):
                budget_account_id = account.id
        except Exception:  # noqa: BLE001
            budget_account_id = None

    slices: list[tuple[str, Decimal]]
    if transaction.items:
        slices = [
            (item.category or transaction.category, item.amount)
            for item in transaction.items
        ]
    else:
        slices = [(transaction.category, transaction.amount)]

    for category, amount in slices:
        if not category:
            continue
        await apply_expense_delta(
            budgets,
            category=category,
            when=transaction.date,
            amount=amount,
            sign=sign,
            settings=settings,
            notifications=notifications,  # type: ignore[arg-type]
            currency=currency,
            language=language,
            amount_currency=transaction.currency,
            rate_book=rate_book,
            account_id=budget_account_id,
        )


class AddTransactionUseCase:
    """Create a transaction and adjust account (and optional goal / debt) balances."""

    def __init__(
        self,
        transactions: TransactionRepository,
        accounts: AccountRepository,
        goals: GoalRepository,
        debts: Optional[DebtRepository] = None,
        budgets: Optional[BudgetRepository] = None,
        settings: Optional[SettingsRepository] = None,
        notifications: object = None,
        currencies: Optional[CurrencyRepository] = None,
        session_factory: object = None,
    ) -> None:
        self._transactions = transactions
        self._accounts = accounts
        self._goals = goals
        self._debts = debts
        self._budgets = budgets
        self._settings = settings
        self._notifications = notifications
        self._currencies = currencies
        self._session_factory = session_factory

    async def execute(self, transaction: Transaction) -> Transaction:
        """Persist ``transaction``, update account balance, sync goal/debt if linked."""
        account = await self._accounts.get_by_id(transaction.account_id)
        if account is None:
            raise ValueError(f"Account not found: {transaction.account_id}")

        now = _utc_now()
        transaction = transaction.model_copy(
            update={
                "amount": quantize_money(transaction.amount),
                "currency": transaction.currency or account.currency,
                "created_at": now,
                "updated_at": now,
            }
        )
        transaction = await _with_goal_credit(
            transaction,
            goals=self._goals,
            currencies=self._currencies,
            accounts=self._accounts,
        )
        if self._debts is not None:
            transaction = await _with_debt_credit(
                transaction,
                debts=self._debts,
                currencies=self._currencies,
                accounts=self._accounts,
            )
        await _validate_goal_link(transaction, goals=self._goals)
        if self._debts is not None:
            await _validate_debt_link(transaction, debts=self._debts)

        async def _persist() -> Transaction:
            created = await self._transactions.create(transaction)

            account.balance = quantize_money(
                account.balance + _balance_delta(created.type, created.amount)
            )
            await self._accounts.update(account)

            created = await self._apply_goal_contribution(created)
            await self._apply_goal_withdrawal(created)
            await self._apply_debt_payment(created)
            await _sync_budget_expense(
                self._budgets,
                created,
                sign=1,
                settings_repo=self._settings,
                notifications=self._notifications,
                currencies=self._currencies,
                accounts=self._accounts,
            )
            return created

        if self._session_factory is not None:
            # TransferAccountsUseCase already owns an outer UoW — reuse it.
            if in_unit_of_work():
                return await _persist()
            with unit_of_work(self._session_factory):  # type: ignore[arg-type]
                return await _persist()
        return await _persist()

    async def _apply_goal_contribution(self, transaction: Transaction) -> Transaction:
        return await _credit_goal_from_transaction(
            goals=self._goals,
            transactions=self._transactions,
            transaction=transaction,
        )

    async def _apply_goal_withdrawal(self, transaction: Transaction) -> None:
        if not _is_goal_withdrawal(transaction):
            return
        goal = await self._goals.get_by_id(transaction.goal_id or "")
        if goal is None:
            return
        credit = goal_credit_amount(transaction)
        updated = reverse_goal_contribution_credit(
            goal,
            credit,
            item_id=transaction.goal_item_id,
        )
        await self._goals.update(updated)

    async def _apply_debt_payment(self, transaction: Transaction) -> None:
        if self._debts is None or not _is_debt_payment(transaction):
            return
        debt = await self._debts.get_by_id(transaction.debt_id or "")
        if debt is None:
            return
        credit = debt_credit_amount(transaction)
        updated = apply_debt_payment_credit(
            debt, credit, transaction=transaction, roll_schedule=True
        )
        await self._debts.update(updated)


class UpdateTransactionUseCase:
    """Update a transaction and reconcile account / goal / debt balances."""

    def __init__(
        self,
        transactions: TransactionRepository,
        accounts: AccountRepository,
        goals: GoalRepository,
        debts: Optional[DebtRepository] = None,
        budgets: Optional[BudgetRepository] = None,
        settings: Optional[SettingsRepository] = None,
        notifications: object = None,
        currencies: Optional[CurrencyRepository] = None,
        session_factory: object = None,
    ) -> None:
        self._transactions = transactions
        self._accounts = accounts
        self._goals = goals
        self._debts = debts
        self._budgets = budgets
        self._settings = settings
        self._notifications = notifications
        self._currencies = currencies
        self._session_factory = session_factory

    async def execute(self, transaction: Transaction) -> Transaction:
        """Replace an existing transaction and fix derived balances."""
        existing = await self._transactions.get_by_id(transaction.id)
        if existing is None:
            raise ValueError(f"Transaction not found: {transaction.id}")
        if existing.transfer_id:
            if (
                transaction.amount != existing.amount
                or transaction.account_id != existing.account_id
                or transaction.type != existing.type
                or transaction.currency != existing.currency
                or transaction.category != existing.category
            ):
                raise ValueError("Transfer legs cannot be edited independently")
            transaction = transaction.model_copy(
                update={
                    "transfer_id": existing.transfer_id,
                    "transfer_peer_account_id": existing.transfer_peer_account_id,
                    "goal_id": None,
                    "debt_id": None,
                    "subscription_id": None,
                }
            )

        updated = transaction.model_copy(
            update={
                "amount": quantize_money(transaction.amount),
                "updated_at": _utc_now(),
                "created_at": existing.created_at,
            }
        )
        updated = await _with_goal_credit(
            updated,
            goals=self._goals,
            currencies=self._currencies,
            accounts=self._accounts,
        )
        if self._debts is not None:
            updated = await _with_debt_credit(
                updated,
                debts=self._debts,
                currencies=self._currencies,
                accounts=self._accounts,
            )
        # Validate before reversing balances / persisting so a bad goal or
        # debt link cannot leave half-applied ledger side effects.
        await _validate_goal_link(updated, goals=self._goals, existing=existing)
        if self._debts is not None:
            await _validate_debt_link(updated, debts=self._debts, existing=existing)

        async def _persist() -> Transaction:
            await self._apply_account_delta(
                existing.account_id,
                -_balance_delta(existing.type, existing.amount),
            )
            await self._reverse_goal_ledger(existing)
            await self._reverse_debt_payment(existing)

            # Drop stale alloc markers from the editor payload; apply rewrites them.
            cleaned = updated.model_copy(
                update={"tags": strip_goal_allocation_tags(updated.tags)}
            )
            saved = await self._transactions.update(cleaned)

            await self._apply_account_delta(
                saved.account_id,
                _balance_delta(saved.type, saved.amount),
            )
            saved = await self._apply_goal_ledger(saved)
            await self._apply_debt_payment(saved)
            await _sync_budget_expense(
                self._budgets,
                existing,
                sign=-1,
                settings_repo=self._settings,
                notifications=self._notifications,
                currencies=self._currencies,
                accounts=self._accounts,
            )
            await _sync_budget_expense(
                self._budgets,
                saved,
                sign=1,
                settings_repo=self._settings,
                notifications=self._notifications,
                currencies=self._currencies,
                accounts=self._accounts,
            )
            return saved

        if self._session_factory is not None:
            if in_unit_of_work():
                return await _persist()
            with unit_of_work(self._session_factory):  # type: ignore[arg-type]
                return await _persist()
        return await _persist()

    async def _apply_account_delta(self, account_id: str, delta: Decimal) -> None:
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        account.balance = quantize_money(account.balance + delta)
        await self._accounts.update(account)

    async def _apply_goal_ledger(self, transaction: Transaction) -> Transaction:
        if _is_goal_contribution(transaction):
            return await _credit_goal_from_transaction(
                goals=self._goals,
                transactions=self._transactions,
                transaction=transaction,
            )
        if _is_goal_withdrawal(transaction):
            goal = await self._goals.get_by_id(transaction.goal_id or "")
            if goal is None:
                return transaction
            credit = goal_credit_amount(transaction)
            updated = reverse_goal_contribution_credit(
                goal,
                credit,
                item_id=transaction.goal_item_id,
            )
            await self._goals.update(updated)
        return transaction

    async def _reverse_goal_ledger(self, transaction: Transaction) -> None:
        if _is_goal_contribution(transaction):
            await _debit_goal_from_transaction(
                goals=self._goals,
                transaction=transaction,
            )
        elif _is_goal_withdrawal(transaction):
            goal = await self._goals.get_by_id(transaction.goal_id or "")
            if goal is None:
                return
            credit = goal_credit_amount(transaction)
            updated = apply_goal_contribution_credit(
                goal,
                credit,
                item_id=transaction.goal_item_id,
            )
            await self._goals.update(updated)

    async def _apply_debt_payment(self, transaction: Transaction) -> None:
        if self._debts is None or not _is_debt_payment(transaction):
            return
        debt = await self._debts.get_by_id(transaction.debt_id or "")
        if debt is None:
            return
        credit = debt_credit_amount(transaction)
        updated = apply_debt_payment_credit(
            debt, credit, transaction=transaction, roll_schedule=True
        )
        await self._debts.update(updated)

    async def _reverse_debt_payment(self, transaction: Transaction) -> None:
        if self._debts is None or not _is_debt_payment(transaction):
            return
        debt = await self._debts.get_by_id(transaction.debt_id or "")
        if debt is None:
            return
        credit = debt_credit_amount(transaction)
        updated = reverse_debt_payment_credit(
            debt, credit, transaction=transaction, roll_schedule=True
        )
        await self._debts.update(updated)


class DeleteTransactionUseCase:
    """Delete a transaction and reverse its balance effects."""

    def __init__(
        self,
        transactions: TransactionRepository,
        accounts: AccountRepository,
        goals: GoalRepository,
        debts: Optional[DebtRepository] = None,
        budgets: Optional[BudgetRepository] = None,
        settings: Optional[SettingsRepository] = None,
        notifications: object = None,
        currencies: Optional[CurrencyRepository] = None,
        session_factory: object = None,
        media_cleanup: Optional[Callable[[str, Sequence[str]], None]] = None,
    ) -> None:
        self._transactions = transactions
        self._accounts = accounts
        self._goals = goals
        self._debts = debts
        self._budgets = budgets
        self._settings = settings
        self._notifications = notifications
        self._currencies = currencies
        self._session_factory = session_factory
        self._media_cleanup = media_cleanup

    async def execute(self, transaction_id: str) -> bool:
        """Remove a transaction and undo account / goal / debt side effects."""

        async def _run() -> bool:
            existing = await self._transactions.get_by_id(transaction_id)
            if existing is None:
                return False
            peer_ids: list[str] = []
            fee_ids: list[str] = []
            if existing.transfer_id:
                peers = await self._transactions.list(transfer_id=existing.transfer_id)
                peer_ids = [p.id for p in peers if p.id != existing.id]
                fee_tag = transfer_fee_tag(existing.transfer_id)
                source = next(
                    (p for p in peers if p.type == TransactionType.EXPENSE),
                    existing if existing.type == TransactionType.EXPENSE else None,
                )
                if source is not None:
                    fees = await self._transactions.list(
                        account_id=source.account_id,
                        category=FEE_CATEGORY,
                        tags=[fee_tag],
                    )
                    fee_ids = [
                        f.id
                        for f in fees
                        if f.id != existing.id and f.id not in peer_ids
                    ]
            ok = await self._delete_one(existing)
            for peer_id in peer_ids:
                peer = await self._transactions.get_by_id(peer_id)
                if peer is not None:
                    await self._delete_one(peer)
            for fee_id in fee_ids:
                fee = await self._transactions.get_by_id(fee_id)
                if fee is not None:
                    await self._delete_one(fee)
            return ok

        if self._session_factory is not None:
            if in_unit_of_work():
                return await _run()
            with unit_of_work(self._session_factory):  # type: ignore[arg-type]
                return await _run()
        return await _run()

    async def _delete_one(self, existing: Transaction) -> bool:
        """Reverse one row without looking up its transfer peer."""
        account = await self._accounts.get_by_id(existing.account_id)
        if account is not None:
            account.balance = quantize_money(
                account.balance - _balance_delta(existing.type, existing.amount)
            )
            await self._accounts.update(account)

        if _is_goal_contribution(existing):
            await _debit_goal_from_transaction(
                goals=self._goals,
                transaction=existing,
            )
        elif _is_goal_withdrawal(existing):
            goal = await self._goals.get_by_id(existing.goal_id or "")
            if goal is not None:
                credit = goal_credit_amount(existing)
                updated = apply_goal_contribution_credit(
                    goal,
                    credit,
                    item_id=existing.goal_item_id,
                )
                await self._goals.update(updated)

        if self._debts is not None and _is_debt_payment(existing):
            debt = await self._debts.get_by_id(existing.debt_id or "")
            if debt is not None:
                credit = debt_credit_amount(existing)
                updated = reverse_debt_payment_credit(
                    debt, credit, transaction=existing, roll_schedule=True
                )
                await self._debts.update(updated)

        await _sync_budget_expense(
            self._budgets,
            existing,
            sign=-1,
            settings_repo=self._settings,
            notifications=self._notifications,
            currencies=self._currencies,
            accounts=self._accounts,
        )
        try:
            if self._media_cleanup is not None:
                self._media_cleanup(
                    existing.id, list(existing.attachments or [])
                )
        except Exception:  # noqa: BLE001
            pass
        return await self._transactions.delete(existing.id)


class ListTransactionsUseCase:
    """List / filter transactions."""

    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    async def execute(
        self,
        *,
        account_id: Optional[str] = None,
        category: Optional[str] = None,
        transaction_type: Optional[TransactionType] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        tags: Optional[Sequence[str]] = None,
        goal_id: Optional[str] = None,
        debt_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        has_subscription: Optional[bool] = None,
        has_debt: Optional[bool] = None,
        transfer_id: Optional[str] = None,
        has_transfer: Optional[bool] = None,
        query: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[Transaction]:
        """Return transactions matching the given filters."""
        return await self._transactions.list(
            account_id=account_id,
            category=category,
            transaction_type=transaction_type,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            goal_id=goal_id,
            debt_id=debt_id,
            subscription_id=subscription_id,
            has_subscription=has_subscription,
            has_debt=has_debt,
            transfer_id=transfer_id,
            has_transfer=has_transfer,
            query=query,
            limit=limit,
            offset=offset,
        )


class StatsPeriod(str, Enum):
    """Aggregation bucket for transaction statistics."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class CategorySlice(BaseModel):
    """Pie-chart slice for a category."""

    category: str
    amount: Decimal
    share: Decimal = Field(description="Fraction of total (0–1)")


class TimeSeriesPoint(BaseModel):
    """Single point on a time-series (line) chart."""

    period: str
    income: Decimal
    expense: Decimal
    net: Decimal


class TransactionStats(BaseModel):
    """Aggregated transaction statistics for charts."""

    total_income: Decimal
    total_expense: Decimal
    net: Decimal
    by_period: list[TimeSeriesPoint]
    by_category: list[CategorySlice]
    fx_ok: bool = True


class GetTransactionStatsUseCase:
    """Compute income/expense stats for charts (time series + category pie)."""

    def __init__(
        self,
        transactions: TransactionRepository,
        currencies: Optional[CurrencyRepository] = None,
        settings: Optional[SettingsRepository] = None,
    ) -> None:
        self._transactions = transactions
        self._currencies = currencies
        self._settings = settings

    async def execute(
        self,
        *,
        account_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        group_by: StatsPeriod = StatsPeriod.MONTH,
    ) -> TransactionStats:
        """Aggregate transactions into period and category summaries."""
        from lib.domain.entities.currency_codes import normalize_currency_code
        from lib.domain.transaction_paging import list_transactions_paged

        items = await list_transactions_paged(
            self._transactions.list,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )

        base = "RUB"
        book = None
        if self._settings is not None:
            try:
                cfg = await self._settings.get()
                base = normalize_currency_code(cfg.default_currency)
            except Exception:  # noqa: BLE001
                pass
        if self._currencies is not None:
            try:
                from lib.domain.services.rate_cache import get_cached_rate_book

                book = await get_cached_rate_book(self._currencies)
            except Exception:  # noqa: BLE001
                book = None

        total_income = Decimal("0.00")
        total_expense = Decimal("0.00")
        period_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        period_expense: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        fx_ok = True

        for tx in items:
            if tx.transfer_id:
                continue
            src = normalize_currency_code(tx.currency or base)
            amount = tx.amount
            if src != base:
                if book is None:
                    fx_ok = False
                    continue
                converted = book.convert(amount, src, base)
                if converted is None:
                    fx_ok = False
                    continue
                amount = converted
            amount = quantize_money(amount)
            key = self._period_key(tx.date, group_by)
            if tx.type == TransactionType.INCOME:
                total_income += amount
                period_income[key] += amount
            else:
                total_expense += amount
                period_expense[key] += amount
                if tx.items:
                    for line in tx.items:
                        line_amt = line.amount
                        if src != base and book is not None:
                            converted_line = book.convert(line_amt, src, base)
                            if converted_line is None:
                                fx_ok = False
                                continue
                            line_amt = converted_line
                        category_totals[line.category or tx.category] += quantize_money(
                            line_amt
                        )
                else:
                    category_totals[tx.category] += amount

        total_income = quantize_money(total_income)
        total_expense = quantize_money(total_expense)
        keys = sorted(set(period_income) | set(period_expense))
        by_period = [
            TimeSeriesPoint(
                period=key,
                income=quantize_money(period_income[key]),
                expense=quantize_money(period_expense[key]),
                net=quantize_money(period_income[key] - period_expense[key]),
            )
            for key in keys
        ]

        expense_total = total_expense if total_expense > 0 else Decimal("1")
        by_category = [
            CategorySlice(
                category=cat,
                amount=quantize_money(amount),
                share=quantize_money(amount / expense_total),
            )
            for cat, amount in sorted(
                category_totals.items(), key=lambda kv: kv[1], reverse=True
            )
        ]

        return TransactionStats(
            total_income=total_income,
            total_expense=total_expense,
            net=quantize_money(total_income - total_expense),
            by_period=by_period,
            by_category=by_category,
            fx_ok=fx_ok,
        )

    @staticmethod
    def _period_key(dt: datetime, group_by: StatsPeriod) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if group_by == StatsPeriod.DAY:
            return dt.strftime("%Y-%m-%d")
        if group_by == StatsPeriod.WEEK:
            iso = dt.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"
        return dt.strftime("%Y-%m")


TRANSFER_CATEGORY = "Перевод"


def make_fee_expense(
    *,
    account_id: str,
    currency: str,
    amount: Decimal,
    date: Optional[datetime] = None,
    comment: str = "",
    extra_tags: Optional[Sequence[str]] = None,
) -> Transaction:
    """Ordinary expense used for a bank/exchange fee."""
    extra = (comment or "").strip()
    tags = ["fee"]
    if extra_tags:
        tags.extend(extra_tags)
    return Transaction(
        account_id=account_id,
        amount=quantize_money(amount),
        category=FEE_CATEGORY,
        tags=tags,
        date=date or _utc_now(),
        comment=extra or FEE_CATEGORY,
        type=TransactionType.EXPENSE,
        currency=currency,
    )


class TransferAccountsUseCase:
    """Move money between two accounts as a linked expense + income pair."""

    def __init__(
        self,
        add_transaction: AddTransactionUseCase,
        delete_transaction: DeleteTransactionUseCase,
        accounts: AccountRepository,
        currencies: object,
        find_or_create_category: object = None,
        session_factory: object = None,
    ) -> None:
        self._add = add_transaction
        self._delete = delete_transaction
        self._accounts = accounts
        self._currencies = currencies
        self._find_or_create_category = find_or_create_category
        self._session_factory = session_factory

    async def execute(
        self,
        *,
        from_account_id: str,
        to_account_id: str,
        amount: Decimal,
        comment: str = "",
        date: Optional[datetime] = None,
        fee: Decimal = Decimal("0"),
        fee_account_id: Optional[str] = None,
    ) -> tuple[Transaction, Transaction]:
        """Create both transfer legs and return ``(outgoing, incoming)``.

        ``fee`` is a separate expense. By default it is charged on the source
        account; pass ``fee_account_id`` to debit another account (e.g. dest).
        The fee amount is in the **fee account** currency.
        """
        from uuid import uuid4

        from lib.domain.entities.category import CategoryKind

        if from_account_id == to_account_id:
            raise ValueError("Cannot transfer to the same account")
        amount = quantize_money(amount)
        fee = quantize_money(fee)
        if amount <= 0:
            raise ValueError("Transfer amount must be positive")
        if fee < 0:
            raise ValueError("Fee cannot be negative")

        source = await self._accounts.get_by_id(from_account_id)
        dest = await self._accounts.get_by_id(to_account_id)
        if source is None:
            raise ValueError(f"Account not found: {from_account_id}")
        if dest is None:
            raise ValueError(f"Account not found: {to_account_id}")

        fee_account = source
        if fee > 0 and fee_account_id:
            resolved = await self._accounts.get_by_id(fee_account_id)
            if resolved is None:
                raise ValueError(f"Account not found: {fee_account_id}")
            fee_account = resolved

        if source.balance < amount:
            raise ValueError("Insufficient funds")
        if fee > 0 and fee_account.id == source.id and source.balance < amount + fee:
            raise ValueError("Insufficient funds")
        if (
            fee > 0
            and fee_account.id != source.id
            and fee_account.id != dest.id
            and fee_account.balance < fee
        ):
            raise ValueError("Insufficient funds")

        dest_amount = amount
        if source.currency.upper() != dest.currency.upper():
            from lib.domain.services.rate_cache import get_cached_rate_book

            converted = (
                await get_cached_rate_book(self._currencies)
            ).convert(amount, source.currency, dest.currency)
            if converted is None:
                raise ValueError("No exchange rate for this currency pair")
            dest_amount = converted
            if dest_amount <= 0:
                raise ValueError("No exchange rate for this currency pair")

        if fee > 0 and fee_account.id == dest.id and dest.balance + dest_amount < fee:
            raise ValueError("Insufficient funds")

        if self._find_or_create_category is not None:
            await self._find_or_create_category.execute(
                TRANSFER_CATEGORY,
                kind=CategoryKind.BOTH,
                icon="sync_alt",
            )
            if fee > 0:
                await self._find_or_create_category.execute(
                    FEE_CATEGORY,
                    kind=CategoryKind.EXPENSE,
                    icon="receipt_long",
                )

        when = date or _utc_now()
        extra = (comment or "").strip()
        out_comment = f"→ {dest.name}"
        in_comment = f"← {source.name}"
        if extra:
            out_comment = f"{out_comment} · {extra}"
            in_comment = f"{in_comment} · {extra}"

        transfer_id = str(uuid4())
        outgoing = Transaction(
            account_id=source.id,
            amount=amount,
            category=TRANSFER_CATEGORY,
            date=when,
            comment=out_comment,
            type=TransactionType.EXPENSE,
            currency=source.currency,
            transfer_id=transfer_id,
            transfer_peer_account_id=dest.id,
        )
        incoming = Transaction(
            account_id=dest.id,
            amount=dest_amount,
            category=TRANSFER_CATEGORY,
            date=when,
            comment=in_comment,
            type=TransactionType.INCOME,
            currency=dest.currency,
            transfer_id=transfer_id,
            transfer_peer_account_id=source.id,
        )

        async def _add_fee() -> None:
            if fee <= 0:
                return
            fee_comment = f"{FEE_CATEGORY} · → {dest.name}"
            if fee_account.id != source.id:
                fee_comment = f"{fee_comment} · {fee_account.name}"
            if extra:
                fee_comment = f"{fee_comment} · {extra}"
            await self._add.execute(
                make_fee_expense(
                    account_id=fee_account.id,
                    currency=fee_account.currency,
                    amount=fee,
                    date=when,
                    comment=fee_comment,
                    extra_tags=[transfer_fee_tag(transfer_id)],
                )
            )

        async def _persist() -> tuple[Transaction, Transaction]:
            created_out = await self._add.execute(outgoing)
            created_in = await self._add.execute(incoming)
            await _add_fee()
            return created_out, created_in

        if self._session_factory is not None:
            with unit_of_work(self._session_factory):  # type: ignore[arg-type]
                return await _persist()

        created_out = await self._add.execute(outgoing)
        try:
            created_in = await self._add.execute(incoming)
            await _add_fee()
        except Exception:
            await self._delete.execute(created_out.id)
            raise
        return created_out, created_in
