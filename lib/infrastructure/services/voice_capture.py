"""Save a spoken expense / income to the default account."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from lib.domain.entities.category import CategoryKind
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.infrastructure.services.voice_parse import VoiceDraft, parse_voice_expense

logger = logging.getLogger("finanse.infrastructure.services.voice_capture")


@dataclass(frozen=True)
class VoiceSaveResult:
    """Outcome of hands-free voice capture."""

    ok: bool
    error: str = ""
    draft: Optional[VoiceDraft] = None
    amount_text: str = ""
    category: str = ""


async def save_spoken_transaction(container: Any, spoken: str) -> VoiceSaveResult:
    """Parse speech and persist a transaction on the first active account."""
    draft = parse_voice_expense(spoken)
    if draft.amount is None or draft.amount <= 0:
        return VoiceSaveResult(ok=False, error="need_amount", draft=draft)
    category = (draft.category or "").strip()
    if not category or category == "Прочее":
        return VoiceSaveResult(ok=False, error="need_category", draft=draft)

    list_accounts = getattr(container, "list_accounts", None)
    add_tx = getattr(container, "add_transaction", None)
    if list_accounts is None or add_tx is None:
        return VoiceSaveResult(ok=False, error="unavailable", draft=draft)

    accounts = await list_accounts.execute(active_only=True)
    if not accounts:
        return VoiceSaveResult(ok=False, error="no_account", draft=draft)
    account = accounts[0]

    finder = getattr(container, "find_or_create_category", None)
    if finder is not None:
        kind = (
            CategoryKind.INCOME
            if draft.tx_type is TransactionType.INCOME
            else CategoryKind.EXPENSE
        )
        try:
            created = await finder.execute(category, kind=kind)
            category = created.name
        except Exception:  # noqa: BLE001
            logger.exception("Could not create spoken category %s", category)

    tx = Transaction(
        account_id=account.id,
        amount=draft.amount,
        category=category,
        date=datetime.now(timezone.utc),
        comment=draft.raw,
        type=draft.tx_type,
        currency=account.currency,
    )
    await add_tx.execute(tx)
    return VoiceSaveResult(
        ok=True,
        draft=draft,
        amount_text=f"{draft.amount} {account.currency}",
        category=category,
    )
