"""SQLAlchemy transaction repository."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import or_, select, update as sa_update, text, cast, String

from lib.domain.entities.transaction import Transaction, TransactionItem, TransactionType
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.infrastructure.db_models import AccountModel, TransactionModel
from lib.infrastructure.repositories._base import (
    SessionFactory,
    ensure_utc,
    in_unit_of_work,
    session_scope,
)
from lib.infrastructure.repositories.transaction_fts import (
    build_fts_match,
    fts_delete,
    fts_upsert,
)

logger = logging.getLogger("finanse.infrastructure.repositories.transaction")


def _items_from_model(raw: object) -> list[TransactionItem]:
    if not raw:
        return []
    rows = raw if isinstance(raw, list) else []
    out: list[TransactionItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            out.append(
                TransactionItem(
                    name=str(row.get("name") or ""),
                    amount=Decimal(str(row.get("amount") or "0")),
                    category=str(row.get("category") or ""),
                )
            )
        except (ValueError, TypeError, ArithmeticError):
            continue
    return out


def _items_to_json(items: list[TransactionItem]) -> list[dict]:
    return [
        {
            "name": item.name,
            "amount": str(item.amount),
            "category": item.category,
        }
        for item in items
    ]


def _rewrite_item_categories(
    raw: object, old_name: str, new_name: str
) -> list | None:
    """Return rewritten JSON items when a line category matches, else None."""
    from lib.domain.entities.category import category_names_equal

    if not isinstance(raw, list) or not raw:
        return None
    target = (new_name or "").strip()
    source = (old_name or "").strip()
    if not target or not source:
        return None
    changed = False
    out: list = []
    for row in raw:
        if not isinstance(row, dict):
            out.append(row)
            continue
        cat = str(row.get("category") or "")
        hit = category_names_equal(cat, source) or (
            not category_names_equal(source, target)
            and category_names_equal(cat, target)
        )
        if hit and cat != target:
            out.append({**row, "category": target})
            changed = True
        else:
            out.append(row)
    return out if changed else None


def _to_entity(model: TransactionModel) -> Transaction:
    tags = list(model.tags or [])
    return Transaction(
        id=model.id,
        account_id=model.account_id,
        amount=Decimal(str(model.amount)),
        category=model.category,
        tags=tags,
        date=ensure_utc(model.date) or datetime.now(timezone.utc),
        comment=model.comment or "",
        type=TransactionType(model.type),
        currency=model.currency,
        goal_id=model.goal_id,
        goal_item_id=getattr(model, "goal_item_id", None),
        debt_id=getattr(model, "debt_id", None),
        subscription_id=getattr(model, "subscription_id", None),
        goal_credit_amount=(
            Decimal(str(model.goal_credit_amount))
            if getattr(model, "goal_credit_amount", None) is not None
            else None
        ),
        debt_credit_amount=(
            Decimal(str(model.debt_credit_amount))
            if getattr(model, "debt_credit_amount", None) is not None
            else None
        ),
        transfer_id=getattr(model, "transfer_id", None),
        transfer_peer_account_id=getattr(model, "transfer_peer_account_id", None),
        items=_items_from_model(getattr(model, "items", None)),
        attachments=[
            str(p).strip()
            for p in (getattr(model, "attachments", None) or [])
            if str(p).strip()
        ],
        created_at=ensure_utc(model.created_at) or datetime.now(timezone.utc),
        updated_at=ensure_utc(model.updated_at) or datetime.now(timezone.utc),
    )


def _apply_entity(model: TransactionModel, entity: Transaction) -> None:
    model.id = entity.id
    model.account_id = entity.account_id
    model.amount = entity.amount
    model.category = entity.category
    model.tags = list(entity.tags or [])
    model.date = ensure_utc(entity.date) or datetime.now(timezone.utc)
    model.comment = entity.comment or ""
    model.type = entity.type.value if isinstance(entity.type, TransactionType) else str(entity.type)
    model.currency = entity.currency
    model.goal_id = entity.goal_id
    model.goal_item_id = entity.goal_item_id
    model.debt_id = entity.debt_id
    model.subscription_id = entity.subscription_id
    model.goal_credit_amount = entity.goal_credit_amount
    model.debt_credit_amount = entity.debt_credit_amount
    model.transfer_id = entity.transfer_id
    model.transfer_peer_account_id = entity.transfer_peer_account_id
    model.items = _items_to_json(list(entity.items or []))
    model.attachments = [
        str(p).strip() for p in (entity.attachments or []) if str(p).strip()
    ]
    model.created_at = ensure_utc(entity.created_at) or datetime.now(timezone.utc)
    model.updated_at = ensure_utc(entity.updated_at) or datetime.now(timezone.utc)


class SqlAlchemyTransactionRepository(TransactionRepository):
    """Transaction persistence via SQLAlchemy sync session + ``asyncio.to_thread``."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def create(self, transaction: Transaction) -> Transaction:
        if in_unit_of_work():
            return self._create_sync(transaction)
        return await asyncio.to_thread(self._create_sync, transaction)

    async def update(self, transaction: Transaction) -> Transaction:
        if in_unit_of_work():
            return self._update_sync(transaction)
        return await asyncio.to_thread(self._update_sync, transaction)

    async def delete(self, transaction_id: str) -> bool:
        if in_unit_of_work():
            return self._delete_sync(transaction_id)
        return await asyncio.to_thread(self._delete_sync, transaction_id)

    async def clear_goal_links(self, goal_id: str) -> int:
        """Bulk-clear ``goal_id`` on linked txs (keeps ``goal_credit_amount``)."""
        if in_unit_of_work():
            return self._clear_goal_links_sync(goal_id)
        return await asyncio.to_thread(self._clear_goal_links_sync, goal_id)

    async def get_by_id(self, transaction_id: str) -> Optional[Transaction]:
        if in_unit_of_work():
            return self._get_by_id_sync(transaction_id)
        return await asyncio.to_thread(self._get_by_id_sync, transaction_id)

    async def list(
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
        amount_min: Optional[Decimal] = None,
        amount_max: Optional[Decimal] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[Transaction]:
        args = (
            account_id,
            category,
            transaction_type,
            date_from,
            date_to,
            list(tags) if tags is not None else None,
            goal_id,
            debt_id,
            subscription_id,
            has_subscription,
            has_debt,
            transfer_id,
            has_transfer,
            (query or "").strip() or None,
            amount_min,
            amount_max,
            limit,
            offset,
        )
        if in_unit_of_work():
            return self._list_sync(*args)
        return await asyncio.to_thread(self._list_sync, *args)

    async def reassign_category(
        self,
        old_name: str,
        new_name: str,
        *,
        account_id: Optional[str] = None,
    ) -> int:
        if in_unit_of_work():
            return self._reassign_category_sync(old_name, new_name, account_id)
        return await asyncio.to_thread(
            self._reassign_category_sync, old_name, new_name, account_id
        )

    def _create_sync(self, entity: Transaction) -> Transaction:
        with session_scope(self._session_factory) as session:
            model = TransactionModel()
            _apply_entity(model, entity)
            session.add(model)
            session.flush()
            fts_upsert(
                session,
                tx_id=model.id,
                category=model.category,
                comment=model.comment or "",
                tags=list(model.tags or []),
                amount=model.amount,
                items=getattr(model, "items", None),
            )
            logger.debug("Created transaction %s", model.id)
            return _to_entity(model)

    def _update_sync(self, entity: Transaction) -> Transaction:
        with session_scope(self._session_factory) as session:
            model = session.get(TransactionModel, entity.id)
            if model is None:
                raise KeyError(f"Transaction not found: {entity.id}")
            _apply_entity(model, entity)
            model.updated_at = datetime.now(timezone.utc)
            session.flush()
            fts_upsert(
                session,
                tx_id=model.id,
                category=model.category,
                comment=model.comment or "",
                tags=list(model.tags or []),
                amount=model.amount,
                items=getattr(model, "items", None),
            )
            logger.debug("Updated transaction %s", model.id)
            return _to_entity(model)

    def _delete_sync(self, transaction_id: str) -> bool:
        with session_scope(self._session_factory) as session:
            model = session.get(TransactionModel, transaction_id)
            if model is None:
                logger.warning("Delete skipped; transaction not found: %s", transaction_id)
                return False
            fts_delete(session, transaction_id)
            session.delete(model)
            logger.debug("Deleted transaction %s", transaction_id)
            return True

    def _clear_goal_links_sync(self, goal_id: str) -> int:
        with session_scope(self._session_factory) as session:
            now = datetime.now(timezone.utc)
            result = session.execute(
                sa_update(TransactionModel)
                .where(TransactionModel.goal_id == goal_id)
                .values(goal_id=None, updated_at=now)
            )
            count = int(result.rowcount or 0)
            logger.debug("Cleared goal_id on %s transactions for goal %s", count, goal_id)
            return count

    def _reassign_category_sync(
        self,
        old_name: str,
        new_name: str,
        account_id: Optional[str],
    ) -> int:
        from lib.domain.entities.category import category_names_equal

        target = (new_name or "").strip()
        source = (old_name or "").strip()
        if not target or not source:
            return 0
        now = datetime.now(timezone.utc)
        scope = (account_id or "").strip()
        count = 0
        with session_scope(self._session_factory) as session:
            stmt = select(TransactionModel)
            if scope:
                stmt = stmt.where(TransactionModel.account_id == scope)
            else:
                stmt = stmt.join(
                    AccountModel,
                    TransactionModel.account_id == AccountModel.id,
                ).where(AccountModel.is_corporate.is_(False))
            rows = session.scalars(stmt).all()
            for model in rows:
                header_hit = category_names_equal(model.category, source) or (
                    not category_names_equal(source, target)
                    and category_names_equal(model.category, target)
                )
                new_items = _rewrite_item_categories(model.items, source, target)
                if not header_hit and new_items is None:
                    continue
                if header_hit and model.category != target:
                    model.category = target
                if new_items is not None:
                    model.items = new_items
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(model, "items")
                model.updated_at = now
                fts_upsert(
                    session,
                    tx_id=model.id,
                    category=model.category,
                    comment=model.comment or "",
                    tags=list(model.tags or []),
                    amount=model.amount,
                    items=getattr(model, "items", None),
                )
                count += 1
            logger.debug(
                "Reassigned category %r → %r on %s transactions (scope=%r)",
                source,
                target,
                count,
                scope,
            )
            return count

    def _get_by_id_sync(self, transaction_id: str) -> Optional[Transaction]:
        with session_scope(self._session_factory) as session:
            model = session.get(TransactionModel, transaction_id)
            return _to_entity(model) if model else None

    def _list_sync(
        self,
        account_id: Optional[str],
        category: Optional[str],
        transaction_type: Optional[TransactionType],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        tags: Optional[list[str]],
        goal_id: Optional[str],
        debt_id: Optional[str],
        subscription_id: Optional[str],
        has_subscription: Optional[bool],
        has_debt: Optional[bool],
        transfer_id: Optional[str],
        has_transfer: Optional[bool],
        query: Optional[str],
        amount_min: Optional[Decimal],
        amount_max: Optional[Decimal],
        limit: Optional[int],
        offset: int,
    ) -> list[Transaction]:
        with session_scope(self._session_factory) as session:
            stmt = select(TransactionModel)
            if account_id is not None:
                stmt = stmt.where(TransactionModel.account_id == account_id)
            if category is not None:
                stmt = stmt.where(TransactionModel.category == category)
            if transaction_type is not None:
                value = (
                    transaction_type.value
                    if isinstance(transaction_type, TransactionType)
                    else str(transaction_type)
                )
                stmt = stmt.where(TransactionModel.type == value)
            if date_from is not None:
                stmt = stmt.where(TransactionModel.date >= ensure_utc(date_from))
            if date_to is not None:
                stmt = stmt.where(TransactionModel.date <= ensure_utc(date_to))
            if goal_id is not None:
                stmt = stmt.where(TransactionModel.goal_id == goal_id)
            if debt_id is not None:
                stmt = stmt.where(TransactionModel.debt_id == debt_id)
            if subscription_id is not None:
                stmt = stmt.where(TransactionModel.subscription_id == subscription_id)
            if has_subscription is True:
                stmt = stmt.where(TransactionModel.subscription_id.is_not(None))
            elif has_subscription is False:
                stmt = stmt.where(TransactionModel.subscription_id.is_(None))
            if has_debt is True:
                stmt = stmt.where(TransactionModel.debt_id.is_not(None))
            elif has_debt is False:
                stmt = stmt.where(TransactionModel.debt_id.is_(None))
            if transfer_id is not None:
                stmt = stmt.where(TransactionModel.transfer_id == transfer_id)
            if has_transfer is True:
                stmt = stmt.where(TransactionModel.transfer_id.is_not(None))
            elif has_transfer is False:
                stmt = stmt.where(TransactionModel.transfer_id.is_(None))
            if amount_min is not None:
                stmt = stmt.where(TransactionModel.amount >= amount_min)
            if amount_max is not None:
                stmt = stmt.where(TransactionModel.amount <= amount_max)

            q = (query or "").strip()
            if q:
                match = build_fts_match(q)
                fts_ids: list[str] | None = None
                if match:
                    try:
                        rows = session.execute(
                            text(
                                "SELECT id FROM transactions_fts "
                                "WHERE transactions_fts MATCH :q"
                            ),
                            {"q": match},
                        ).fetchall()
                        fts_ids = [str(r[0]) for r in rows]
                    except Exception:  # noqa: BLE001
                        fts_ids = None
                if fts_ids is not None:
                    if not fts_ids:
                        return []
                    stmt = stmt.where(TransactionModel.id.in_(fts_ids))
                else:
                    # LIKE fallback when FTS table is missing.
                    pattern = f"%{q}%"
                    stmt = stmt.where(
                        or_(
                            TransactionModel.category.ilike(pattern),
                            TransactionModel.comment.ilike(pattern),
                            cast(TransactionModel.tags, String).ilike(pattern),
                            cast(TransactionModel.amount, String).ilike(pattern),
                            cast(TransactionModel.items, String).ilike(pattern),
                        )
                    )

            stmt = stmt.order_by(TransactionModel.date.desc())
            # Tags live in JSON — filter in Python *before* limit/offset so
            # pagination matches the filtered set (AUDIT #63).
            if tags:
                rows = session.scalars(stmt).all()
                required = set(tags)
                entities = [
                    e
                    for e in (_to_entity(r) for r in rows)
                    if required.issubset(set(e.tags))
                ]
                if offset:
                    entities = entities[offset:]
                if limit is not None:
                    entities = entities[:limit]
                return entities
            if offset:
                stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.scalars(stmt).all()
            return [_to_entity(r) for r in rows]
