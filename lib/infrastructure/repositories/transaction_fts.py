"""Helpers for transactions_fts (SQLite FTS5)."""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import text

logger = logging.getLogger("finanse.infrastructure.transaction_fts")

_FTS_SPECIAL = re.compile(r'["\'\*:\^\(\)\{\}\[\]\-\\]')

FTS_COLUMNS = ("id", "category", "comment", "tags", "payee", "amount")


def tags_blob(tags: Sequence[str] | None) -> str:
    """Serialize tags for the FTS document (space-separated + JSON)."""
    items = [str(t).strip() for t in (tags or []) if str(t).strip()]
    if not items:
        return ""
    return " ".join(items) + " " + json.dumps(items, ensure_ascii=False)


def payee_blob(items: Sequence[Any] | None) -> str:
    """Concatenate receipt line names for FTS (stand-in for payee)."""
    names: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(getattr(item, "name", "") or "").strip()
        if name:
            names.append(name)
    return " ".join(names)


def amount_blob(amount: object) -> str:
    """Index numeric amount as several searchable tokens."""
    try:
        value = Decimal(str(amount))
    except Exception:  # noqa: BLE001
        text_value = str(amount or "").strip()
        return text_value
    raw = format(value, "f")
    tokens = {raw, raw.replace(".", ","), str(int(value))}
    if "." in raw:
        tokens.add(raw.split(".", 1)[0])
        tokens.add(raw.replace(".", ""))
    return " ".join(sorted(tokens))


def build_fts_match(query: str) -> str | None:
    """Turn a user query into a safe FTS5 MATCH expression (AND of prefixes)."""
    cleaned = _FTS_SPECIAL.sub(" ", (query or "").strip())
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return None
    parts = [f'"{tok}"*' for tok in tokens[:12]]
    return " AND ".join(parts)


def fts_upsert(
    session: Any,
    *,
    tx_id: str,
    category: str,
    comment: str,
    tags: Sequence[str] | None,
    amount: object = None,
    payee: str = "",
    items: Sequence[Any] | None = None,
) -> None:
    """Insert or replace one FTS row (no-op if virtual table missing)."""
    try:
        session.execute(
            text("DELETE FROM transactions_fts WHERE id = :id"),
            {"id": tx_id},
        )
        session.execute(
            text(
                "INSERT INTO transactions_fts"
                "(id, category, comment, tags, payee, amount) "
                "VALUES (:id, :category, :comment, :tags, :payee, :amount)"
            ),
            {
                "id": tx_id,
                "category": category or "",
                "comment": comment or "",
                "tags": tags_blob(tags),
                "payee": (payee or "").strip() or payee_blob(items),
                "amount": amount_blob(amount),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("FTS upsert skipped: %s", exc)


def fts_delete(session: Any, tx_id: str) -> None:
    """Remove one FTS row."""
    try:
        session.execute(
            text("DELETE FROM transactions_fts WHERE id = :id"),
            {"id": tx_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("FTS delete skipped: %s", exc)
