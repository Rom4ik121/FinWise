"""Account-related use cases."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from lib.domain.entities.account import Account
from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import TransactionType
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.currency_repository import CurrencyRepository
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.domain.services.rate_book import RateBook


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CreateAccountUseCase:
    """Create a new account with an initial balance."""

    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, account: Account) -> Account:
        """Persist a new account; balance starts at ``initial_balance``."""
        initial = quantize_money(account.initial_balance)
        created = account.model_copy(
            update={
                "initial_balance": initial,
                "balance": initial,
                "created_at": account.created_at or _utc_now(),
            }
        )
        return await self._accounts.create(created)


class UpdateAccountUseCase:
    """Update account metadata (name, icon, color, currency, active / total flags)."""

    def __init__(
        self,
        accounts: AccountRepository,
        currencies: CurrencyRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._accounts = accounts
        self._currencies = currencies
        self._transactions = transactions

    async def execute(self, account: Account) -> Account:
        """Update metadata; never overwrite ledger ``balance`` from the client.

        Balance changes only via transactions or
        :class:`RecalculateAccountBalanceUseCase`. ``initial_balance`` may be
        edited and is stored as provided (caller should recalculate after).

        Changing ``currency`` converts ``initial_balance`` and every transaction
        amount (including line items) via :class:`RateBook`, then recalculates
        balance. Raises ``ValueError`` when any rate is missing.
        """
        existing = await self._accounts.get_by_id(account.id)
        if existing is None:
            raise ValueError(f"Account not found: {account.id}")

        old_ccy = normalize_currency_code(existing.currency)
        new_ccy = normalize_currency_code(account.currency or existing.currency)

        if old_ccy == new_ccy:
            updated = account.model_copy(
                update={
                    "balance": quantize_money(existing.balance, currency=new_ccy),
                    "initial_balance": quantize_money(
                        account.initial_balance, currency=new_ccy
                    ),
                    "currency": new_ccy,
                }
            )
            return await self._accounts.update(updated)

        rates = await self._currencies.list_rates()
        book = RateBook(rates)
        new_initial = book.convert(existing.initial_balance, old_ccy, new_ccy)
        if new_initial is None:
            raise ValueError(f"No exchange rate for {old_ccy}/{new_ccy}")

        txs = await self._transactions.list_by_account(account.id)
        for tx in txs:
            src = normalize_currency_code(tx.currency or old_ccy)
            patch: dict = {"currency": new_ccy}
            if src != new_ccy:
                converted = book.convert(tx.amount, src, new_ccy)
                if converted is None:
                    raise ValueError(f"No exchange rate for {src}/{new_ccy}")
                patch["amount"] = quantize_money(converted, currency=new_ccy)
            if tx.items:
                new_items = []
                for item in tx.items:
                    item_amt = item.amount
                    if src != new_ccy:
                        item_conv = book.convert(item.amount, src, new_ccy)
                        if item_conv is None:
                            raise ValueError(f"No exchange rate for {src}/{new_ccy}")
                        item_amt = quantize_money(item_conv, currency=new_ccy)
                    new_items.append(item.model_copy(update={"amount": item_amt}))
                patch["items"] = new_items
            if tx.goal_credit_amount is not None and src != new_ccy:
                gconv = book.convert(tx.goal_credit_amount, src, new_ccy)
                if gconv is None:
                    raise ValueError(f"No exchange rate for {src}/{new_ccy}")
                patch["goal_credit_amount"] = quantize_money(gconv, currency=new_ccy)
            if tx.debt_credit_amount is not None and src != new_ccy:
                dconv = book.convert(tx.debt_credit_amount, src, new_ccy)
                if dconv is None:
                    raise ValueError(f"No exchange rate for {src}/{new_ccy}")
                patch["debt_credit_amount"] = quantize_money(dconv, currency=new_ccy)
            await self._transactions.update(tx.model_copy(update=patch))

        patched = account.model_copy(
            update={
                "currency": new_ccy,
                "initial_balance": quantize_money(new_initial, currency=new_ccy),
                "balance": quantize_money(existing.balance, currency=new_ccy),
            }
        )
        await self._accounts.update(patched)
        return await RecalculateAccountBalanceUseCase(
            self._accounts, self._transactions
        ).execute(account.id)


class DeleteAccountUseCase:
    """Delete an account."""

    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, account_id: str) -> bool:
        """Remove an account by id."""
        return await self._accounts.delete(account_id)


class ListAccountsUseCase:
    """List accounts."""

    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, *, active_only: bool = False) -> list[Account]:
        """Return accounts, optionally active-only."""
        return await self._accounts.list(active_only=active_only)


class RecalculateAccountBalanceUseCase:
    """Recompute an account balance from initial balance + transactions."""

    def __init__(
        self,
        accounts: AccountRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._accounts = accounts
        self._transactions = transactions

    async def execute(self, account_id: str) -> Account:
        """Set balance = initial_balance + incomes − expenses."""
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")

        txs = await self._transactions.list_by_account(account_id)
        balance = quantize_money(account.initial_balance)
        for tx in txs:
            if tx.type == TransactionType.INCOME:
                balance += tx.amount
            else:
                balance -= tx.amount

        account.balance = quantize_money(balance)
        return await self._accounts.update(account)
