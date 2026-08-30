"""Import exchange balances and trades into a FinWise account."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from lib.core.config import AppConfig
from lib.domain.entities.account import Account
from lib.domain.entities.exchange_connection import ExchangeConnection
from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.exchanges import get_exchange
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.exchange_connection_repository import (
    ExchangeConnectionRepository,
)
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.infrastructure.api.ccxt_exchange_client import (
    ExchangeClientError,
    Snapshot,
    fetch_snapshot,
    test_credentials,
)
from lib.infrastructure.services.secret_box import decrypt_secret, encrypt_secret

logger = logging.getLogger("finanse.domain.use_cases.exchange_sync")

_CAT = {
    "trade": "Торговля",
    "fee": "Комиссия",
    "deposit": "Депозит",
    "withdrawal": "Вывод",
}


@dataclass
class SyncResult:
    """Outcome of an exchange pull."""

    account: Account
    imported: int = 0
    holdings: int = 0
    error: str = ""


def ext_tag(provider: str, kind: str, external_id: str) -> str:
    """Stable idempotency tag for a venue event."""
    return f"ext:{provider}:{kind}:{external_id}"


class ConnectExchangeAccountUseCase:
    """Create or update an account bound to exchange API keys."""

    def __init__(
        self,
        accounts: AccountRepository,
        connections: ExchangeConnectionRepository,
        *,
        config: Optional[AppConfig] = None,
    ) -> None:
        self._accounts = accounts
        self._connections = connections
        self._config = config

    async def execute(
        self,
        *,
        account: Account,
        provider: str,
        api_key: str,
        secret: str,
        passphrase: str = "",
        existing: Optional[Account] = None,
        verify: bool = True,
    ) -> Account:
        spec = get_exchange(provider)
        if spec is None:
            raise ValueError(f"Unknown exchange: {provider}")
        if not (api_key or "").strip() or not (secret or "").strip():
            raise ValueError("API key and secret are required")
        if existing is None:
            account.name = spec.title
        if verify:
            await asyncio.to_thread(
                test_credentials,
                provider=provider,
                api_key=api_key,
                secret=secret,
                passphrase=passphrase,
            )
        if existing is None:
            saved = await self._accounts.create(account)
        else:
            saved = await self._accounts.update(account)
        blob = encrypt_secret(
            {
                "api_key": api_key.strip(),
                "secret": secret.strip(),
                "passphrase": (passphrase or "").strip(),
            },
            config=self._config,
        )
        previous = await self._connections.get_by_account_id(saved.id)
        link = ExchangeConnection(
            id=previous.id if previous else str(uuid4()),
            account_id=saved.id,
            provider=spec.id,
            credentials_encrypted=blob,
            last_sync_at=previous.last_sync_at if previous else None,
            last_error="",
            holdings_json=previous.holdings_json if previous else [],
            created_at=previous.created_at if previous else saved.created_at,
        )
        await self._connections.upsert(link)
        return saved


class SyncExchangeAccountUseCase:
    """Pull balances and trades, then rewrite the account ledger snapshot."""

    def __init__(
        self,
        accounts: AccountRepository,
        transactions: TransactionRepository,
        connections: ExchangeConnectionRepository,
        *,
        config: Optional[AppConfig] = None,
        add_transaction: Any = None,
    ) -> None:
        self._accounts = accounts
        self._transactions = transactions
        self._connections = connections
        self._config = config
        self._add = add_transaction

    async def _create_tx(self, tx: Transaction) -> Transaction:
        if self._add is not None:
            return await self._add.execute(tx)
        return await self._transactions.create(tx)

    async def execute(self, account_id: str) -> SyncResult:
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        link = await self._connections.get_by_account_id(account_id)
        if link is None:
            raise ValueError("This account is not linked to an exchange")
        try:
            creds = decrypt_secret(link.credentials_encrypted, config=self._config)
        except Exception as exc:  # noqa: BLE001
            await self._fail(link, str(exc))
            raise ExchangeClientError("Could not read stored API keys") from exc
        is_first = link.last_sync_at is None
        quote = "AUTO" if is_first else (account.currency or "AUTO")
        try:
            snapshot: Snapshot = await asyncio.to_thread(
                fetch_snapshot,
                provider=link.provider,
                api_key=str(creds.get("api_key") or ""),
                secret=str(creds.get("secret") or ""),
                passphrase=str(creds.get("passphrase") or ""),
                quote=quote,
            )
        except ExchangeClientError as exc:
            await self._fail(link, str(exc))
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Exchange sync failed for %s", account_id)
            await self._fail(link, str(exc))
            raise ExchangeClientError(str(exc)) from exc

        if is_first or not (account.currency or "").strip():
            account.currency = snapshot.currency

        existing = await self._transactions.list_by_account(account_id)
        known = {tag for tx in existing for tag in (tx.tags or []) if tag.startswith("ext:")}
        imported = 0
        for trade in snapshot.trades:
            tag = ext_tag(link.provider, trade.kind, trade.external_id)
            if tag in known:
                continue
            if trade.amount <= 0:
                continue
            tx_type = (
                TransactionType.INCOME
                if trade.side == "sell" or trade.kind == "deposit"
                else TransactionType.EXPENSE
            )
            if trade.kind == "withdrawal":
                tx_type = TransactionType.EXPENSE
            category = _CAT.get(trade.kind, _CAT["trade"])
            await self._create_tx(
                Transaction(
                    account_id=account_id,
                    amount=trade.amount,
                    category=category,
                    tags=[tag],
                    date=trade.date,
                    comment=trade.comment,
                    type=tx_type,
                    currency=account.currency,
                )
            )
            known.add(tag)
            imported += 1
            if trade.fee > 0 and trade.fee_currency in {"", account.currency.upper()}:
                fee_tag = ext_tag(link.provider, "fee", trade.external_id)
                if fee_tag not in known:
                    await self._create_tx(
                        Transaction(
                            account_id=account_id,
                            amount=trade.fee if trade.fee > 0 else Decimal("0.01"),
                            category=_CAT["fee"],
                            tags=[fee_tag],
                            date=trade.date,
                            comment=f"fee {trade.symbol}".strip(),
                            type=TransactionType.EXPENSE,
                            currency=account.currency,
                        )
                    )
                    known.add(fee_tag)
                    imported += 1

        txs = await self._transactions.list_by_account(account_id)
        net = Decimal("0")
        for tx in txs:
            if tx.type == TransactionType.INCOME:
                net += tx.amount
            else:
                net -= tx.amount
        total = quantize_money(snapshot.total)
        account.initial_balance = quantize_money(total - net)
        account.balance = total
        saved = await self._accounts.update(account)

        holdings_payload: list[dict[str, Any]] = [
            {
                "asset": item.asset,
                "amount": str(item.amount),
                "value": str(item.value),
            }
            for item in snapshot.holdings
        ]
        link.last_sync_at = datetime.now(timezone.utc)
        link.last_error = ""
        link.holdings_json = holdings_payload
        await self._connections.upsert(link)
        return SyncResult(account=saved, imported=imported, holdings=len(holdings_payload))

    async def _fail(self, link: ExchangeConnection, message: str) -> None:
        link.last_error = (message or "sync failed")[:500]
        try:
            await self._connections.upsert(link)
        except Exception:  # noqa: BLE001
            logger.exception("Could not store exchange sync error")
