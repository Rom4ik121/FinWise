"""Prefer the most-used account when creating income / expense."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from lib.domain.entities.account import Account
from lib.domain.entities.transaction import Transaction
from lib.presentation.utils import tr

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_SCAN_LIMIT = 150


def frequent_account_id(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
) -> Optional[str]:
    """Return the active account id used most often in ``transactions``.

    Transfers are ignored. Ties break toward the most recently used account.
    Falls back to the first account when there is no history.
    """
    if not accounts:
        return None
    active = {a.id for a in accounts}
    counts: Counter[str] = Counter()
    last_seen: dict[str, datetime] = {}
    for tx in transactions:
        aid = tx.account_id
        if aid not in active:
            continue
        if getattr(tx, "is_transfer", False) or getattr(tx, "transfer_id", None):
            continue
        counts[aid] += 1
        when = tx.date or datetime.min.replace(tzinfo=timezone.utc)
        prev = last_seen.get(aid)
        if prev is None or when > prev:
            last_seen[aid] = when
    if not counts:
        return accounts[0].id
    return max(
        counts.keys(),
        key=lambda aid: (counts[aid], last_seen.get(aid) or datetime.min),
    )


def order_accounts_frequent_first(
    accounts: Sequence[Account],
    preferred_id: Optional[str],
) -> list[Account]:
    """Put ``preferred_id`` first; keep relative order of the rest."""
    rows = list(accounts)
    if not preferred_id or not rows:
        return rows
    preferred = [a for a in rows if a.id == preferred_id]
    rest = [a for a in rows if a.id != preferred_id]
    return preferred + rest


def account_option_label(
    account: Account,
    *,
    frequent_id: Optional[str],
    lang: str,
) -> str:
    """Dropdown text; marks the frequent account."""
    base = f"{account.name} ({account.currency})"
    if frequent_id and account.id == frequent_id:
        return f"{base} · {tr('account.frequent', lang)}"
    return base


async def prepare_tx_account_choices(
    state: "AppState",
    accounts: Sequence[Account],
) -> tuple[list[Account], str]:
    """Reorder accounts and pick default id for a new income/expense form."""
    rows = list(accounts)
    if not rows:
        return [], ""
    preferred: Optional[str] = None
    list_tx = getattr(state.container, "list_transactions", None)
    if list_tx is not None:
        try:
            recent = await list_tx.execute(
                has_transfer=False,
                limit=_SCAN_LIMIT,
            )
            preferred = frequent_account_id(rows, recent)
        except Exception:  # noqa: BLE001
            preferred = None
    if preferred is None or preferred not in {a.id for a in rows}:
        preferred = rows[0].id
    ordered = order_accounts_frequent_first(rows, preferred)
    return ordered, preferred
