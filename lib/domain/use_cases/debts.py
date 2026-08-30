"""Debt-related use cases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from lib.domain.entities.debt import (
    Debt,
    DebtDirection,
    DebtStatus,
    resolve_debt_status,
)
from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.currency_repository import CurrencyRepository
from lib.domain.repositories.debt_repository import DebtRepository
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.domain.services.rate_book import RateBook

if TYPE_CHECKING:
    from lib.domain.use_cases.transactions import (
        AddTransactionUseCase,
        DeleteTransactionUseCase,
    )

DEBT_CATEGORY = "Долг"
DEBT_PRINCIPAL_CATEGORY = "Долг (выдача)"
DEBT_PRINCIPAL_TAG = "debt_principal"
DEBT_INTEREST_TAG_PREFIX = "debt_interest:"


def is_debt_principal_tx(transaction: Transaction) -> bool:
    """Cash movement that opens a debt — must not change ``remaining_amount``."""
    return DEBT_PRINCIPAL_TAG in (transaction.tags or [])


def debt_interest_from_tags(transaction: Transaction) -> Decimal:
    """Parse interest portion recorded on a repayment (debt currency)."""
    for tag in transaction.tags or []:
        if tag.startswith(DEBT_INTEREST_TAG_PREFIX):
            raw = tag[len(DEBT_INTEREST_TAG_PREFIX) :]
            try:
                return quantize_money(Decimal(raw))
            except Exception:  # noqa: BLE001
                return Decimal("0.00")
    return Decimal("0.00")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _months_between(start: datetime, end: datetime) -> float:
    if end <= start:
        return 0.0
    return max((end - start).total_seconds() / 86400.0 / 30.4375, 0.0)


def _add_months(dt: datetime, months: float) -> datetime:
    return dt + timedelta(days=months * 30.4375)


def _pace_divisor_months(
    now: datetime,
    lookback_months: int,
    started_at: Optional[datetime],
) -> Decimal:
    """Months to average over: observed life in the lookback window, at least 1."""
    lookback_start = now - timedelta(days=lookback_months * 30.4375)
    window_start = lookback_start
    if started_at is not None:
        start = started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start > window_start:
            window_start = start
    observed = _months_between(window_start, now)
    capped = min(float(lookback_months), max(observed, 1.0))
    return Decimal(str(capped))


def _monthly_interest(debt: Debt) -> Decimal:
    """Monthly share of annual interest on remaining principal (rate / 12).

    Same annual % as :func:`compute_debt_interest` (display / projection only).
    """
    if debt.interest_rate is None:
        return Decimal("0.00")
    remaining = quantize_money(max(Decimal("0"), debt.remaining_amount))
    return quantize_money(
        remaining
        * Decimal(str(debt.interest_rate))
        / Decimal("100")
        / Decimal("12")
    )


def debt_credit_amount(transaction: Transaction) -> Decimal:
    """Amount applied to debt remaining (debt currency)."""
    if transaction.debt_credit_amount is not None:
        return quantize_money(transaction.debt_credit_amount)
    return quantize_money(transaction.amount)


class DebtProjection(BaseModel):
    """Payoff pace / recommended payment metrics for a debt."""

    debt_id: str
    recommended_monthly_payment: Optional[Decimal] = None
    projected_payoff_date: Optional[datetime] = None
    is_on_track: Optional[bool] = None
    average_monthly_payment: Decimal = Decimal("0.00")
    remaining_amount: Decimal = Decimal("0.00")
    lookback_months: int = 3


class CreateDebtUseCase:
    """Create a debt and optionally move cash on an account."""

    def __init__(
        self,
        debts: DebtRepository,
        accounts: Optional[AccountRepository] = None,
        add_transaction: Optional["AddTransactionUseCase"] = None,
        currencies: Optional[CurrencyRepository] = None,
    ) -> None:
        self._debts = debts
        self._accounts = accounts
        self._add_transaction = add_transaction
        self._currencies = currencies

    async def execute(
        self,
        debt: Debt,
        *,
        account_id: Optional[str] = None,
    ) -> Debt:
        """Persist a debt; if ``account_id`` is set, record principal cash flow."""
        amount = quantize_money(debt.amount)
        created = debt.model_copy(
            update={
                "amount": amount,
                "remaining_amount": amount,
                "status": DebtStatus.ACTIVE,
                "account_id": (debt.account_id or account_id or "").strip() or None,
                "accrued_interest": Decimal("0.00"),
                "created_at": debt.created_at or _utc_now(),
                "updated_at": _utc_now(),
                "started_at": debt.started_at or _utc_now(),
            }
        )
        created = await self._debts.create(created)

        cash_account_id = (account_id or "").strip() or None
        if cash_account_id and self._accounts is not None and self._add_transaction is not None:
            account = await self._accounts.get_by_id(cash_account_id)
            if account is None:
                raise ValueError(f"Account not found: {cash_account_id}")
            cash_amount = amount
            if account.currency.upper() != created.currency.upper():
                if self._currencies is None:
                    raise ValueError(
                        f"No exchange rate for {created.currency}/{account.currency}"
                    )
                rates = await self._currencies.list_rates()
                converted = RateBook(rates).convert(
                    amount, created.currency, account.currency
                )
                if converted is None:
                    raise ValueError(
                        f"No exchange rate for {created.currency}/{account.currency}"
                    )
                cash_amount = quantize_money(converted)
            tx_type = (
                TransactionType.INCOME
                if created.direction == DebtDirection.I_OWE
                else TransactionType.EXPENSE
            )
            await self._add_transaction.execute(
                Transaction(
                    account_id=account.id,
                    amount=cash_amount,
                    category=DEBT_PRINCIPAL_CATEGORY,
                    tags=[DEBT_PRINCIPAL_TAG],
                    date=_utc_now(),
                    comment=created.counterparty,
                    type=tx_type,
                    currency=account.currency,
                    debt_id=created.id,
                    debt_credit_amount=Decimal("0.00"),
                )
            )
        return created


class UpdateDebtUseCase:
    """Update debt metadata; remaining stays ledger-driven except currency FX."""

    def __init__(
        self,
        debts: DebtRepository,
        currencies: Optional[CurrencyRepository] = None,
    ) -> None:
        self._debts = debts
        self._currencies = currencies

    async def execute(self, debt: Debt) -> Debt:
        """Update terms; convert remaining when currency changes (or refuse)."""
        existing = await self._debts.get_by_id(debt.id)
        if existing is None:
            raise ValueError(f"Debt not found: {debt.id}")

        amount = quantize_money(debt.amount)
        remaining = quantize_money(existing.remaining_amount)
        accrued = quantize_money(existing.accrued_interest)
        new_ccy = (debt.currency or existing.currency or "RUB").upper()
        old_ccy = (existing.currency or "RUB").upper()
        if new_ccy != old_ccy and remaining != 0:
            if self._currencies is None:
                raise ValueError(f"No exchange rate for {old_ccy}/{new_ccy}")
            rates = await self._currencies.list_rates()
            book = RateBook(rates)
            converted = book.convert(remaining, old_ccy, new_ccy)
            if converted is None:
                raise ValueError(f"No exchange rate for {old_ccy}/{new_ccy}")
            remaining = quantize_money(converted)
            if accrued != 0:
                accrued_fx = book.convert(accrued, old_ccy, new_ccy)
                if accrued_fx is None:
                    raise ValueError(f"No exchange rate for {old_ccy}/{new_ccy}")
                accrued = quantize_money(accrued_fx)
            amount_fx = book.convert(amount, old_ccy, new_ccy)
            if amount_fx is not None:
                amount = quantize_money(amount_fx)

        if amount < remaining and not debt.accrue_interest:
            # Shrinking principal target should not leave remaining above amount
            # unless interest accrual is enabled (remaining can exceed principal).
            remaining = amount

        next_pay_amt = debt.next_payment_amount
        if next_pay_amt is not None:
            next_pay_amt = quantize_money(next_pay_amt)
            if next_pay_amt <= 0:
                next_pay_amt = None

        requested = debt.status if isinstance(debt.status, DebtStatus) else DebtStatus(debt.status)
        if requested == DebtStatus.ARCHIVED:
            status = DebtStatus.ARCHIVED
        else:
            status = resolve_debt_status(
                remaining_amount=remaining,
                due_date=debt.due_date,
                next_payment_date=debt.next_payment_date,
                current=requested,
            )
        updated = debt.model_copy(
            update={
                "currency": new_ccy,
                "amount": amount,
                "remaining_amount": remaining,
                "accrued_interest": accrued,
                "next_payment_amount": next_pay_amt,
                "account_id": (debt.account_id or "").strip() or None,
                "status": status,
                "updated_at": _utc_now(),
                "created_at": existing.created_at,
                "last_interest_accrued_at": existing.last_interest_accrued_at
                if debt.last_interest_accrued_at is None
                else debt.last_interest_accrued_at,
            }
        )
        return await self._debts.update(updated)


class DeleteDebtUseCase:
    """Delete a debt and reverse linked principal cash movements."""

    def __init__(
        self,
        debts: DebtRepository,
        transactions: Optional[TransactionRepository] = None,
        delete_transaction: Optional["DeleteTransactionUseCase"] = None,
    ) -> None:
        self._debts = debts
        self._transactions = transactions
        self._delete_transaction = delete_transaction

    async def execute(self, debt_id: str) -> bool:
        if self._transactions is not None and self._delete_transaction is not None:
            linked = await self._transactions.list(debt_id=debt_id)
            for tx in linked:
                if is_debt_principal_tx(tx):
                    await self._delete_transaction.execute(tx.id)
        return await self._debts.delete(debt_id)


class ListDebtsUseCase:
    """List debts."""

    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    async def execute(
        self,
        *,
        status: DebtStatus | str | None = None,
        direction: DebtDirection | str | None = None,
        currency: str | None = None,
        sort_by: str = "due_date",
    ) -> list[Debt]:
        return await self._debts.list(
            status=status,
            direction=direction,
            currency=currency,
            sort_by=sort_by,
        )


class ArchiveDebtUseCase:
    """Move a paid (or closed) debt to archived status."""

    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    async def execute(self, debt_id: str) -> Debt:
        debt = await self._debts.get_by_id(debt_id)
        if debt is None:
            raise ValueError(f"Debt not found: {debt_id}")
        if debt.status == DebtStatus.ARCHIVED:
            return debt
        if debt.status != DebtStatus.PAID:
            raise ValueError("Only paid debts can be archived")
        updated = debt.model_copy(
            update={"status": DebtStatus.ARCHIVED, "updated_at": _utc_now()}
        )
        return await self._debts.update(updated)


class MarkOverdueDebtsUseCase:
    """Flip active debts past due_date to overdue status."""

    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    async def execute(self, *, now: Optional[datetime] = None) -> list[Debt]:
        moment = now or _utc_now()
        changed: list[Debt] = []
        for debt in await self._debts.list(status=DebtStatus.ACTIVE):
            status = resolve_debt_status(
                remaining_amount=debt.remaining_amount,
                due_date=debt.due_date,
                next_payment_date=debt.next_payment_date,
                current=debt.status,
                now=moment,
            )
            if status != DebtStatus.OVERDUE:
                continue
            updated = debt.model_copy(
                update={"status": DebtStatus.OVERDUE, "updated_at": moment}
            )
            changed.append(await self._debts.update(updated))
        return changed


class RepayDebtUseCase:
    """Pay or collect against a debt using an account balance (FX-aware)."""

    def __init__(
        self,
        debts: DebtRepository,
        accounts: AccountRepository,
        add_transaction: "AddTransactionUseCase",
        currencies: CurrencyRepository,
    ) -> None:
        self._debts = debts
        self._accounts = accounts
        self._add_transaction = add_transaction
        self._currencies = currencies

    async def execute(
        self,
        debt_id: str,
        amount: Decimal,
        *,
        account_id: str,
        interest_amount: Optional[Decimal] = None,
    ) -> Debt:
        """Move money and reduce ``remaining_amount``.

        ``amount`` is in the **account** currency (total cash movement).
        Optional ``interest_amount`` is in the **debt** currency.

        When ``accrue_interest`` is on, the full converted payment reduces
        ``remaining_amount`` (capitalized interest lives there), and
        ``accrued_interest`` is reduced by ``min(interest, accrued)``.
        When accrual is off, only the principal portion
        (``converted - interest``) reduces remaining; interest is cash-only.
        """
        amount = quantize_money(amount)
        if amount <= 0:
            raise ValueError("Payment amount must be positive")
        if not (account_id or "").strip():
            raise ValueError("Account is required for a debt payment")

        debt = await self._debts.get_by_id(debt_id)
        if debt is None:
            raise ValueError(f"Debt not found: {debt_id}")
        if debt.status in (DebtStatus.PAID, DebtStatus.ARCHIVED) or debt.remaining_amount <= 0:
            raise ValueError("Debt is already paid")

        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")

        rates = await self._currencies.list_rates()
        book = RateBook(rates)
        converted = book.convert(amount, account.currency, debt.currency)
        if converted is None:
            raise ValueError(
                f"No exchange rate for {account.currency}/{debt.currency}"
            )
        converted = quantize_money(converted)

        interest = Decimal("0.00")
        if interest_amount is not None:
            interest = quantize_money(interest_amount)
            if interest < 0:
                raise ValueError("Interest amount cannot be negative")
            if interest > converted:
                raise ValueError("Interest cannot exceed payment amount")

        principal_portion = quantize_money(converted - interest)
        if debt.accrue_interest:
            credit_to_remaining = converted
        else:
            credit_to_remaining = principal_portion

        if credit_to_remaining > debt.remaining_amount:
            credit_to_remaining = quantize_money(debt.remaining_amount)
            if debt.accrue_interest:
                # Scale interest share to the clamped total when needed.
                if converted > 0 and interest > 0:
                    interest = quantize_money(
                        interest * credit_to_remaining / converted
                    )
            debt_total = credit_to_remaining if debt.accrue_interest else quantize_money(
                credit_to_remaining + interest
            )
            account_amount = book.convert(debt_total, debt.currency, account.currency)
            if account_amount is None:
                raise ValueError(
                    f"No exchange rate for {debt.currency}/{account.currency}"
                )
            amount = quantize_money(account_amount)
        elif credit_to_remaining <= 0 and interest <= 0:
            raise ValueError("Payment amount must be positive")

        comment = debt.counterparty
        tags: list[str] = []
        if interest > 0:
            comment = f"{debt.counterparty} · interest {interest} {debt.currency}"
            tags.append(f"{DEBT_INTEREST_TAG_PREFIX}{interest}")

        tx_type = (
            TransactionType.EXPENSE
            if debt.direction == DebtDirection.I_OWE
            else TransactionType.INCOME
        )
        await self._add_transaction.execute(
            Transaction(
                account_id=account.id,
                amount=amount,
                category=DEBT_CATEGORY,
                tags=tags,
                date=_utc_now(),
                comment=comment,
                type=tx_type,
                currency=account.currency,
                debt_id=debt.id,
                debt_credit_amount=credit_to_remaining,
            )
        )
        updated = await self._debts.get_by_id(debt_id)
        if updated is None:
            raise ValueError(f"Debt not found after payment: {debt_id}")

        # Persist preferred repay account + roll installment schedule forward.
        patch: dict = {}
        if interest > 0 and debt.accrue_interest:
            new_accrued = quantize_money(
                max(Decimal("0"), updated.accrued_interest - interest)
            )
            if new_accrued != updated.accrued_interest:
                patch["accrued_interest"] = new_accrued
        if (account_id or "").strip():
            patch["account_id"] = account_id.strip()
        if (
            updated.remaining_amount > 0
            and updated.next_payment_date is not None
            and updated.status
            not in (DebtStatus.PAID, DebtStatus.ARCHIVED)
        ):
            patch["next_payment_date"] = _add_months(updated.next_payment_date, 1.0)
            patch["status"] = resolve_debt_status(
                remaining_amount=updated.remaining_amount,
                due_date=updated.due_date,
                next_payment_date=patch["next_payment_date"],
                current=updated.status,
            )
        if patch:
            patch["updated_at"] = _utc_now()
            updated = await self._debts.update(updated.model_copy(update=patch))
        return updated


class GetDebtProjectionUseCase:
    """Compute payoff pace, recommended monthly payment, and on-track status."""

    def __init__(
        self,
        debts: DebtRepository,
        transactions: TransactionRepository,
        *,
        lookback_months: int = 3,
    ) -> None:
        self._debts = debts
        self._transactions = transactions
        self._lookback_months = max(1, int(lookback_months))

    async def execute(self, debt_id: str) -> DebtProjection:
        debt = await self._debts.get_by_id(debt_id)
        if debt is None:
            raise ValueError(f"Debt not found: {debt_id}")

        now = _utc_now()
        remaining = quantize_money(max(Decimal("0"), debt.remaining_amount))
        projection = DebtProjection(
            debt_id=debt.id,
            remaining_amount=remaining,
            lookback_months=self._lookback_months,
        )
        if remaining <= 0:
            projection.recommended_monthly_payment = Decimal("0.00")
            projection.projected_payoff_date = now
            projection.is_on_track = True
            return projection

        monthly_interest = _monthly_interest(debt)
        if debt.due_date is not None:
            months_left = _months_between(now, debt.due_date)
            if months_left <= 0:
                projection.recommended_monthly_payment = remaining
            else:
                projection.recommended_monthly_payment = quantize_money(
                    remaining / Decimal(str(months_left)) + monthly_interest
                )

        lookback_start = now - timedelta(days=self._lookback_months * 30.4375)
        txs = await self._transactions.list(debt_id=debt.id, date_from=lookback_start)
        total_paid = sum(
            (
                debt_credit_amount(tx)
                for tx in txs
                if not is_debt_principal_tx(tx)
            ),
            Decimal("0"),
        )
        divisor = _pace_divisor_months(
            now,
            self._lookback_months,
            debt.started_at or debt.created_at,
        )
        avg = quantize_money(total_paid / divisor)
        projection.average_monthly_payment = avg

        principal_pace = avg - monthly_interest
        if principal_pace > 0:
            months_needed = float(remaining / principal_pace)
            projection.projected_payoff_date = _add_months(now, months_needed)
        else:
            projection.projected_payoff_date = None

        if debt.due_date is None:
            projection.is_on_track = None
        elif _months_between(now, debt.due_date) <= 0:
            projection.is_on_track = False
        elif projection.projected_payoff_date is None:
            projection.is_on_track = False
        else:
            projection.is_on_track = (
                projection.projected_payoff_date <= debt.due_date
            )

        return projection


class DeleteDebtPaymentUseCase:
    """Delete a debt payment transaction and restore remaining amount."""

    def __init__(
        self,
        transactions: TransactionRepository,
        delete_transaction: "DeleteTransactionUseCase",
    ) -> None:
        self._transactions = transactions
        self._delete_transaction = delete_transaction

    async def execute(self, transaction_id: str, *, debt_id: str) -> bool:
        tx = await self._transactions.get_by_id(transaction_id)
        if tx is None:
            return False
        if tx.debt_id != debt_id:
            raise ValueError("Transaction is not linked to this debt")
        return await self._delete_transaction.execute(transaction_id)


class DebtInterestResult(BaseModel):
    """Simple interest accrual result for a debt."""

    debt_id: str
    principal: Decimal
    interest_rate: Decimal
    days: int
    interest_amount: Decimal
    total_with_interest: Decimal


class CalculateDebtInterestUseCase:
    """Calculate simple annual interest accrued since ``started_at``."""

    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    async def execute(
        self,
        debt_id: str,
        *,
        as_of: Optional[datetime] = None,
        debt: Optional[Debt] = None,
    ) -> DebtInterestResult:
        entity = debt
        if entity is None:
            entity = await self._debts.get_by_id(debt_id)
        if entity is None:
            raise ValueError(f"Debt not found: {debt_id}")
        return compute_debt_interest(entity, as_of=as_of)


def compute_debt_interest(
    debt: Debt,
    *,
    as_of: Optional[datetime] = None,
) -> DebtInterestResult:
    """Display interest: remaining × annual% × days/365 (not accrued into ledger).

    Payoff projections use the same annual rate as monthly = rate/12.
    """
    if debt.interest_rate is None:
        raise ValueError(f"Debt {debt.id} has no interest_rate")

    moment = as_of or _utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    start = debt.started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    days = max(0, (moment - start).days)
    rate = Decimal(str(debt.interest_rate))
    principal = quantize_money(debt.remaining_amount)
    interest = quantize_money(
        principal * rate * Decimal(days) / Decimal("365") / Decimal("100")
    )

    return DebtInterestResult(
        debt_id=debt.id,
        principal=principal,
        interest_rate=rate,
        days=days,
        interest_amount=interest,
        total_with_interest=quantize_money(principal + interest),
    )


class AccrueDebtInterestUseCase:
    """Capitalize monthly interest into ``remaining_amount`` when enabled."""

    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    async def execute(self, *, now: Optional[datetime] = None) -> list[Debt]:
        moment = now or _utc_now()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        changed: list[Debt] = []
        open_statuses = (DebtStatus.ACTIVE, DebtStatus.OVERDUE)
        for status in open_statuses:
            for debt in await self._debts.list(status=status):
                if not debt.accrue_interest or debt.interest_rate is None:
                    continue
                if debt.remaining_amount <= 0:
                    continue
                last = debt.last_interest_accrued_at or debt.started_at or debt.created_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                months = int(_months_between(last, moment))
                if months < 1:
                    continue
                monthly = _monthly_interest(debt)
                if monthly <= 0:
                    continue
                add = quantize_money(monthly * Decimal(months))
                new_remaining = quantize_money(debt.remaining_amount + add)
                new_accrued = quantize_money(debt.accrued_interest + add)
                updated = debt.model_copy(
                    update={
                        "remaining_amount": new_remaining,
                        "accrued_interest": new_accrued,
                        "last_interest_accrued_at": moment,
                        "status": resolve_debt_status(
                            remaining_amount=new_remaining,
                            due_date=debt.due_date,
                            next_payment_date=debt.next_payment_date,
                            current=debt.status,
                            now=moment,
                        ),
                        "updated_at": moment,
                    }
                )
                changed.append(await self._debts.update(updated))
        return changed


class UndoLastDebtPaymentUseCase:
    """Delete the most recent non-principal payment for a debt."""

    def __init__(
        self,
        transactions: TransactionRepository,
        delete_debt_payment: DeleteDebtPaymentUseCase,
    ) -> None:
        self._transactions = transactions
        self._delete_debt_payment = delete_debt_payment

    async def execute(self, debt_id: str) -> bool:
        txs = await self._transactions.list(debt_id=debt_id)
        payments = [
            tx
            for tx in txs
            if not is_debt_principal_tx(tx) and tx.debt_id == debt_id
        ]
        if not payments:
            raise ValueError("No repayments to undo")
        payments.sort(key=lambda t: t.date, reverse=True)
        return await self._delete_debt_payment.execute(
            payments[0].id, debt_id=debt_id
        )


class ListDebtCounterpartiesUseCase:
    """Directory of known counterparty names (from existing debts)."""

    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    async def execute(self) -> list[str]:
        names: set[str] = set()
        for status in (
            DebtStatus.ACTIVE,
            DebtStatus.OVERDUE,
            DebtStatus.PAID,
            DebtStatus.ARCHIVED,
        ):
            for debt in await self._debts.list(status=status):
                name = (debt.counterparty or "").strip()
                if name:
                    names.add(name)
        return sorted(names, key=str.casefold)
