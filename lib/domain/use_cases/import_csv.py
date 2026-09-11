"""CSV statement import use cases."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from lib.domain.entities.account import Account
from lib.domain.entities.transaction import Transaction
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.services.csv_statement import (
    CsvDetectResult,
    CsvMappedRow,
    detect_csv,
    iter_valid,
    map_rows,
)
from lib.domain.use_cases.transactions import AddTransactionUseCase


class PreviewCsvImportUseCase:
    """Detect CSV shape and dry-run map rows (no writes)."""

    async def execute(
        self,
        payload: bytes,
        mapping: Optional[dict[str, str]] = None,
        *,
        default_currency: str = "RUB",
    ) -> tuple[CsvDetectResult, list[CsvMappedRow]]:
        info = detect_csv(payload)
        cols = mapping or info.mapping
        rows = map_rows(
            payload,
            cols,
            default_currency=default_currency,
            detect=info,
        )
        return info, rows


class CommitCsvImportUseCase:
    """Create ledger transactions from validated CSV rows."""

    def __init__(
        self,
        add_transaction: AddTransactionUseCase,
        accounts: AccountRepository,
    ) -> None:
        self._add = add_transaction
        self._accounts = accounts

    async def execute(
        self,
        rows: Sequence[CsvMappedRow],
        *,
        account_id: str,
        default_category: str = "Прочее",
        default_currency: str = "RUB",
        accounts: Optional[Sequence[Account]] = None,
    ) -> list[Transaction]:
        account_list = list(accounts) if accounts is not None else await self._accounts.list(
            active_only=False
        )
        by_id = {a.id: a for a in account_list}
        by_name = {a.name.strip().lower(): a for a in account_list}
        fallback = by_id.get(account_id)
        if fallback is None:
            raise ValueError("Account not found")
        created: list[Transaction] = []
        for row in iter_valid(rows):
            target = fallback
            hint = (row.account_hint or "").strip()
            if hint:
                if hint in by_id:
                    target = by_id[hint]
                else:
                    named = by_name.get(hint.lower())
                    if named is not None:
                        target = named
            amount = row.amount or Decimal("0")
            saved = await self._add.execute(
                Transaction(
                    account_id=target.id,
                    amount=amount,
                    category=default_category,
                    date=row.date,
                    comment=row.description,
                    type=row.tx_type,
                    currency=row.currency or target.currency or default_currency,
                    tags=["csv-import"],
                )
            )
            created.append(saved)
        return created
