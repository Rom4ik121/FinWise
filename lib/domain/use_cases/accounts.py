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
from lib.domain.repositories.settings_repository import SettingsRepository
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.domain.services.rate_book import RateBook


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CreateAccountUseCase:
    """Create a new account with an initial balance."""

    def __init__(
        self,
        accounts: AccountRepository,
        settings: SettingsRepository,
    ) -> None:
        self._accounts = accounts
        self._settings = settings

    async def execute(self, account: Account) -> Account:
        """Persist a new account; balance starts at ``initial_balance``.

        Corporate accounts are excluded from home totals by default.

        The first account's currency becomes ``settings.default_currency`` once;
        later accounts do not change the display currency (Settings only).
        """
        prior = await self._accounts.list(active_only=False)
        is_first = len(prior) == 0
        initial = quantize_money(account.initial_balance)
        currency = normalize_currency_code(account.currency)
        patch: dict = {
            "initial_balance": initial,
            "balance": initial,
            "currency": currency,
            "created_at": account.created_at or _utc_now(),
        }
        if account.is_corporate:
            patch["include_in_total"] = False
            patch["is_corporate"] = True
        created = await self._accounts.create(account.model_copy(update=patch))
        if is_first:
            current = await self._settings.get()
            if normalize_currency_code(current.default_currency) != currency:
                await self._settings.update(
                    current.model_copy(
                        update={
                            "default_currency": currency,
                            "updated_at": _utc_now(),
                        }
                    )
                )
        return created


class UpdateAccountUseCase:
    """Update account metadata (name, icon, color, currency, active / total flags)."""

    def __init__(
        self,
        accounts: AccountRepository,
        currencies: CurrencyRepository,
        transactions: TransactionRepository,
        session_factory: object = None,
    ) -> None:
        self._accounts = accounts
        self._currencies = currencies
        self._transactions = transactions
        self._session_factory = session_factory

    async def execute(self, account: Account) -> Account:
        """Update metadata; never overwrite ledger ``balance`` from the client.

        Balance changes only via transactions or
        :class:`RecalculateAccountBalanceUseCase`. ``initial_balance`` may be
        edited and is stored as provided (caller should recalculate after).

        Changing ``currency`` converts ``initial_balance`` and every transaction
        amount (including line items) via :class:`RateBook`, then recalculates
        balance. ``goal_credit_amount`` / ``debt_credit_amount`` stay untouched —
        they are denominated in the goal/debt currency, not the account's.
        Raises ``ValueError`` when any rate is missing.
        """

        async def _run() -> Account:
            existing = await self._accounts.get_by_id(account.id)
            if existing is None:
                raise ValueError(f"Account not found: {account.id}")

            old_ccy = normalize_currency_code(existing.currency)
            new_ccy = normalize_currency_code(account.currency or existing.currency)

            def _with_corporate_rules(entity: Account) -> Account:
                if entity.is_corporate:
                    return entity.model_copy(
                        update={"include_in_total": False, "is_corporate": True}
                    )
                return entity

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
                return await self._accounts.update(_with_corporate_rules(updated))

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
                                raise ValueError(
                                    f"No exchange rate for {src}/{new_ccy}"
                                )
                            item_amt = quantize_money(item_conv, currency=new_ccy)
                        new_items.append(item.model_copy(update={"amount": item_amt}))
                    patch["items"] = new_items
                # Do NOT convert goal_credit_amount / debt_credit_amount: those
                # amounts are already in goal/debt currency for apply/reverse.
                await self._transactions.update(tx.model_copy(update=patch))

            patched = account.model_copy(
                update={
                    "currency": new_ccy,
                    "initial_balance": quantize_money(new_initial, currency=new_ccy),
                    "balance": quantize_money(existing.balance, currency=new_ccy),
                }
            )
            await self._accounts.update(_with_corporate_rules(patched))
            return await RecalculateAccountBalanceUseCase(
                self._accounts, self._transactions
            ).execute(account.id)

        if self._session_factory is not None:
            from lib.domain.unit_of_work import in_unit_of_work, unit_of_work

            if in_unit_of_work():
                return await _run()
            with unit_of_work(self._session_factory):  # type: ignore[arg-type]
                return await _run()
        return await _run()


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

    async def execute(
        self,
        *,
        active_only: bool = False,
        corporate: bool | None = None,
    ) -> list[Account]:
        """Return accounts; see :meth:`AccountRepository.list` for filters."""
        return await self._accounts.list(
            active_only=active_only, corporate=corporate
        )


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
