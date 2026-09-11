"""Data export use case (interface-level helper)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.budget_repository import BudgetRepository
from lib.domain.repositories.category_repository import CategoryRepository
from lib.domain.repositories.currency_repository import CurrencyRepository
from lib.domain.repositories.debt_repository import DebtRepository
from lib.domain.repositories.goal_repository import GoalRepository
from lib.domain.repositories.settings_repository import SettingsRepository
from lib.domain.repositories.subscription_repository import SubscriptionRepository
from lib.domain.repositories.transaction_repository import TransactionRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_export_filename(filename: str) -> str:
    """Keep only the final path component so callers cannot escape ``export_dir``."""
    name = Path(str(filename or "").replace("\\", "/")).name
    if not name or name in {".", ".."}:
        raise ValueError("Invalid export filename")
    return name


def _confine_export_path(export_dir: Path, filename: str) -> Path:
    """Resolve ``export_dir / filename`` and reject paths outside ``export_dir``."""
    export_root = export_dir.resolve()
    path = (export_root / filename).resolve()
    if path != export_root and export_root not in path.parents:
        raise ValueError("Export path escapes export directory")
    return path


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


@dataclass(slots=True)
class ExportResult:
    """Result of an export operation."""

    path: Path
    exported_at: datetime
    counts: dict[str, int]


class ExportDataUseCase:
    """Export core domain data to a JSON file for backup / reporting.

    This is an interface-level helper: it aggregates repository reads and
    writes a portable JSON snapshot. Presentation / file-picker UI lives
    outside the domain layer.

    Exchange API credentials are never exported.
    """

    def __init__(
        self,
        accounts: AccountRepository,
        transactions: TransactionRepository,
        goals: GoalRepository,
        debts: DebtRepository,
        subscriptions: SubscriptionRepository,
        currencies: CurrencyRepository,
        settings: SettingsRepository,
        categories: Optional[CategoryRepository] = None,
        budgets: Optional[BudgetRepository] = None,
    ) -> None:
        self._accounts = accounts
        self._transactions = transactions
        self._goals = goals
        self._debts = debts
        self._subscriptions = subscriptions
        self._currencies = currencies
        self._settings = settings
        self._categories = categories
        self._budgets = budgets

    async def execute(
        self,
        export_dir: Path,
        *,
        filename: Optional[str] = None,
        password: Optional[str] = None,
    ) -> ExportResult:
        """Write a JSON dump of domain data into ``export_dir``.

        Args:
            export_dir: Target directory (created if missing).
            filename: Optional file name; defaults to a UTC timestamped name.
            password: When set, write an AES-GCM encrypted ``.fwexport`` blob
                instead of plaintext JSON (PBKDF2-HMAC-SHA256 key derivation).

        Returns:
            :class:`ExportResult` with path and entity counts.
        """
        export_dir.mkdir(parents=True, exist_ok=True)
        exported_at = _utc_now()
        if filename is None:
            stamp = exported_at.strftime("%Y%m%dT%H%M%SZ")
            filename = (
                f"finanse_export_{stamp}.fwexport"
                if password
                else f"finanse_export_{stamp}.json"
            )
        filename = _safe_export_filename(filename)

        from lib.domain.transaction_paging import list_transactions_paged

        accounts = await self._accounts.list(active_only=False)
        transactions = await list_transactions_paged(self._transactions.list)
        goals = await self._goals.list(include_completed=True)
        debts = await self._debts.list()
        subscriptions = await self._subscriptions.list(active_only=False)
        currencies = await self._currencies.list_currencies(include_crypto=True)
        rates = await self._currencies.list_rates()
        settings = await self._settings.get()
        categories = (
            await self._categories.list(active_only=False)
            if self._categories is not None
            else []
        )
        budgets = await self._budgets.list_all() if self._budgets is not None else []

        from lib.domain.use_cases.debts import (
            debt_credit_amount,
            debt_interest_from_tags,
            is_debt_principal_tx,
        )

        debt_payments = []
        for tx in transactions:
            if not tx.debt_id or is_debt_principal_tx(tx):
                continue
            debt_payments.append(
                {
                    **tx.model_dump(mode="json"),
                    "principal_credit": str(debt_credit_amount(tx)),
                    "interest_credit": str(debt_interest_from_tags(tx)),
                }
            )

        payload = {
            "exported_at": exported_at.isoformat(),
            "version": 3,
            "accounts": [a.model_dump(mode="json") for a in accounts],
            "transactions": [t.model_dump(mode="json") for t in transactions],
            "goals": [g.model_dump(mode="json") for g in goals],
            "debts": [d.model_dump(mode="json") for d in debts],
            "debt_payments": debt_payments,
            "subscriptions": [s.model_dump(mode="json") for s in subscriptions],
            "categories": [c.model_dump(mode="json") for c in categories],
            "budgets": [b.model_dump(mode="json") for b in budgets],
            "currencies": [c.model_dump(mode="json") for c in currencies],
            "exchange_rates": [r.model_dump(mode="json") for r in rates],
            "settings": settings.model_dump(mode="json"),
        }

        path = _confine_export_path(export_dir, filename)
        raw = json.dumps(
            payload, ensure_ascii=False, indent=2, default=_json_default
        ).encode("utf-8")
        if password:
            path.write_bytes(_encrypt_export(raw, password))
        else:
            path.write_text(raw.decode("utf-8"), encoding="utf-8")

        return ExportResult(
            path=path,
            exported_at=exported_at,
            counts={
                "accounts": len(accounts),
                "transactions": len(transactions),
                "goals": len(goals),
                "debts": len(debts),
                "debt_payments": len(debt_payments),
                "subscriptions": len(subscriptions),
                "categories": len(categories),
                "budgets": len(budgets),
                "currencies": len(currencies),
                "exchange_rates": len(rates),
            },
        )


def _encrypt_export(raw: bytes, password: str) -> bytes:
    """AES-GCM encrypt export bytes; format ``FWEX`` + salt + nonce + cipher."""
    import hashlib
    import secrets

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000, dklen=32)
    nonce = secrets.token_bytes(12)
    cipher = AESGCM(key).encrypt(nonce, raw, b"FWEX")
    return b"FWEX" + salt + nonce + cipher


def decrypt_export_blob(blob: bytes, password: str) -> bytes:
    """Decrypt a blob from :func:`_encrypt_export`."""
    import hashlib

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(b"FWEX") or len(blob) < 4 + 16 + 12 + 16:
        raise ValueError("Invalid encrypted export")
    salt = blob[4:20]
    nonce = blob[20:32]
    cipher = blob[32:]
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000, dklen=32)
    return AESGCM(key).decrypt(nonce, cipher, b"FWEX")
