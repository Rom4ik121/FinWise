"""Goal-related use cases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from pydantic import BaseModel

from lib.core.config import DEFAULT_SAVINGS_CATEGORY, normalize_savings_category
from lib.domain.entities.goal import Goal, GoalItem, GoalItemStatus, GoalStatus
from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.repositories.account_repository import AccountRepository
from lib.domain.repositories.currency_repository import CurrencyRepository
from lib.domain.repositories.goal_repository import GoalRepository
from lib.domain.repositories.transaction_repository import TransactionRepository
from lib.domain.services.rate_book import RateBook

if TYPE_CHECKING:
    from lib.domain.use_cases.transactions import (
        AddTransactionUseCase,
        DeleteTransactionUseCase,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _savings_category(goal: Goal) -> str:
    """Ledger category for contributions — the goal name."""
    name = (goal.name or "").strip()
    if name:
        return name
    return normalize_savings_category(goal.category_link)


def _months_between(start: datetime, end: datetime) -> float:
    """Approximate fractional months between two UTC datetimes."""
    from lib.domain.use_cases.goal_insights import fractional_months_between

    return fractional_months_between(start, end)


def assert_goal_accepts_ledger(goal: Goal) -> None:
    """Raise when the goal cannot receive contributions or withdrawals."""
    status = (
        goal.status
        if isinstance(goal.status, GoalStatus)
        else GoalStatus(str(goal.status))
    )
    if status == GoalStatus.ARCHIVED:
        raise ValueError("Goal is archived")
    if status != GoalStatus.ACTIVE:
        raise ValueError("Goal is already completed")


def _add_months(dt: datetime, months: float) -> datetime:
    """Add fractional months to ``dt`` (day-based approximation)."""
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


def goal_credit_amount(transaction: Transaction) -> Decimal:
    """Amount credited to the goal currency for a contribution transaction."""
    if transaction.goal_credit_amount is not None:
        return quantize_money(transaction.goal_credit_amount)
    return quantize_money(transaction.amount)


GOAL_ALLOC_TAG_PREFIX = "goal_alloc:"


def encode_goal_allocation_tags(allocations: dict[str, Decimal]) -> list[str]:
    """Serialize per-item contribution splits into transaction tags."""
    tags: list[str] = []
    for item_id, amount in sorted(allocations.items()):
        amt = quantize_money(amount)
        if amt <= 0:
            continue
        tags.append(f"{GOAL_ALLOC_TAG_PREFIX}{item_id}:{amt}")
    return tags


def has_goal_allocation_tag_markers(tags: list[str] | None) -> bool:
    """True when any ``goal_alloc:`` marker is present (even if corrupt)."""
    return any(
        str(tag).strip().startswith(GOAL_ALLOC_TAG_PREFIX) for tag in (tags or [])
    )


def parse_goal_allocation_tags(tags: list[str] | None) -> dict[str, Decimal] | None:
    """Parse per-item splits from tags; ``None`` when no valid allocation tags exist."""
    found: dict[str, Decimal] = {}
    for tag in tags or []:
        text = (tag or "").strip()
        if not text.startswith(GOAL_ALLOC_TAG_PREFIX):
            continue
        payload = text[len(GOAL_ALLOC_TAG_PREFIX) :]
        if ":" not in payload:
            continue
        item_id, raw_amt = payload.split(":", 1)
        item_id = item_id.strip()
        if not item_id:
            continue
        try:
            amt = quantize_money(raw_amt)
        except Exception:  # noqa: BLE001
            continue
        if amt <= 0:
            continue
        found[item_id] = quantize_money(found.get(item_id, Decimal("0")) + amt)
    return found or None


def strip_goal_allocation_tags(tags: list[str] | None) -> list[str]:
    """Remove allocation markers while keeping user tags."""
    return [
        t
        for t in (tags or [])
        if not str(t).strip().startswith(GOAL_ALLOC_TAG_PREFIX)
    ]


def apply_goal_contribution_credit(
    goal: Goal,
    credit: Decimal,
    *,
    item_id: str | None = None,
) -> Goal:
    """Increase goal (and optional item) progress after a contribution."""
    updated, _allocations = allocate_goal_contribution_credit(
        goal, credit, item_id=item_id
    )
    return updated


def allocate_goal_contribution_credit(
    goal: Goal,
    credit: Decimal,
    *,
    item_id: str | None = None,
) -> tuple[Goal, dict[str, Decimal]]:
    """Apply credit and return ``(goal, per-item allocations)`` for exact reverse."""
    credit = quantize_money(credit)
    if goal.items:
        if not item_id:
            raise ValueError("Goal item is required")
        by_id = {item.id: item for item in goal.items}
        if item_id not in by_id:
            raise ValueError("Goal item not found")
        if by_id[item_id].is_closed:
            raise ValueError("Goal item is already closed")

        credit_left = credit
        updated: dict[str, GoalItem] = dict(by_id)
        allocations: dict[str, Decimal] = {}

        def _credit_item(iid: str, amount: Decimal) -> Decimal:
            item = updated[iid]
            if item.is_closed or amount <= 0:
                return amount
            room = quantize_money(
                max(Decimal("0"), item.target_amount - item.current_amount)
            )
            # When already at/over target, leave amount for sibling spillover
            # (or the final overflow dump onto primary).
            if room <= 0:
                return amount
            add = min(amount, room)
            updated[iid] = item.model_copy(
                update={
                    "current_amount": quantize_money(item.current_amount + add)
                }
            )
            allocations[iid] = quantize_money(
                allocations.get(iid, Decimal("0")) + add
            )
            return quantize_money(amount - add)

        credit_left = _credit_item(item_id, credit_left)
        if credit_left > 0:
            # Spill to the next open items in sort order (wrap around), so
            # excess on position N fills N+1, N+2… before dumping leftover.
            ordered = sorted(
                goal.items, key=lambda i: (int(i.sort_order), i.id)
            )
            start = next(
                (idx for idx, it in enumerate(ordered) if it.id == item_id),
                0,
            )
            for offset in range(1, len(ordered)):
                if credit_left <= 0:
                    break
                sibling = ordered[(start + offset) % len(ordered)]
                if sibling.id == item_id or sibling.is_closed:
                    continue
                credit_left = _credit_item(sibling.id, credit_left)
        if credit_left > 0:
            primary = updated[item_id]
            updated[item_id] = primary.model_copy(
                update={
                    "current_amount": quantize_money(
                        primary.current_amount + credit_left
                    )
                }
            )
            allocations[item_id] = quantize_money(
                allocations.get(item_id, Decimal("0")) + credit_left
            )
        ordered = [updated[item.id] for item in goal.items]
        payload = goal.model_copy(update={"items": ordered})
        return Goal.model_validate(payload.model_dump()), allocations
    payload = goal.model_copy(
        update={"current_amount": quantize_money(goal.current_amount + credit)}
    )
    return Goal.model_validate(payload.model_dump()), {}


def reverse_goal_contribution_credit(
    goal: Goal,
    credit: Decimal,
    *,
    item_id: str | None = None,
    allocations: dict[str, Decimal] | None = None,
    allocation_mode: str | None = None,
) -> Goal:
    """Undo goal (and optional item) progress when a contribution is removed.

    ``allocation_mode``:
    - ``exact`` — use ``allocations`` then debit leftover from primary only
      (no sibling LIFO; prevents wiping unrelated item credits).
    - ``primary_only`` — corrupt/partial markers; debit primary only.
    - ``lifo`` / ``None`` — legacy spillover reverse when no tags were stored.
    """
    credit = quantize_money(credit)
    if goal.items:
        if not item_id:
            raise ValueError("Goal item is required")
        by_id = {item.id: item for item in goal.items}
        if item_id not in by_id:
            raise ValueError("Goal item not found")

        updated: dict[str, GoalItem] = dict(by_id)

        def _debit_item(iid: str, amount: Decimal) -> Decimal:
            """Remove up to ``amount`` from item; return how much was taken."""
            if iid not in updated:
                return Decimal("0.00")
            item = updated[iid]
            if amount <= 0:
                return Decimal("0.00")
            take = min(amount, quantize_money(max(Decimal("0"), item.current_amount)))
            updated[iid] = item.model_copy(
                update={
                    "current_amount": quantize_money(item.current_amount - take)
                }
            )
            return quantize_money(take)

        mode = (allocation_mode or "").strip().lower()
        if not mode:
            mode = "exact" if allocations else "lifo"

        debit_left = credit
        if mode == "exact" and allocations:
            for iid, amount in allocations.items():
                taken = _debit_item(iid, quantize_money(amount))
                debit_left = quantize_money(debit_left - taken)
            # Leftover stays on primary — never LIFO into siblings when tags
            # were authoritative (avoids full wipe on partial tags).
            if debit_left > 0:
                _debit_item(item_id, debit_left)
        elif mode == "primary_only":
            _debit_item(item_id, debit_left)
        else:
            # Legacy LIFO: overflow → siblings → primary.
            excess = quantize_money(
                max(
                    Decimal("0"),
                    updated[item_id].current_amount - updated[item_id].target_amount,
                )
            )
            if excess > 0 and debit_left > 0:
                taken = _debit_item(item_id, min(excess, debit_left))
                debit_left = quantize_money(debit_left - taken)
            for item in sorted(goal.items, key=lambda i: i.sort_order, reverse=True):
                if item.id == item_id or debit_left <= 0:
                    continue
                taken = _debit_item(item.id, debit_left)
                debit_left = quantize_money(debit_left - taken)
            if debit_left > 0:
                _debit_item(item_id, debit_left)

        ordered = [updated[item.id] for item in goal.items]
        payload = goal.model_copy(update={"items": ordered})
        return Goal.model_validate(payload.model_dump())
    payload = goal.model_copy(
        update={
            "current_amount": quantize_money(
                max(Decimal("0"), goal.current_amount - credit)
            )
        }
    )
    return Goal.model_validate(payload.model_dump())


def _normalize_goal_items(items: list[GoalItem]) -> list[GoalItem]:
    normalized: list[GoalItem] = []
    for idx, item in enumerate(items):
        name = (item.name or "").strip()
        if not name:
            continue
        normalized.append(
            item.model_copy(
                update={
                    "name": name,
                    "target_amount": quantize_money(item.target_amount),
                    "current_amount": quantize_money(item.current_amount),
                    "sort_order": idx,
                }
            )
        )
    return normalized


class GoalProjection(BaseModel):
    """Projection / on-track metrics for a savings goal."""

    goal_id: str
    required_monthly_contribution: Optional[Decimal] = None
    projected_completion_date: Optional[datetime] = None
    is_on_track: Optional[bool] = None
    average_monthly_contribution: Decimal = Decimal("0.00")
    remaining_amount: Decimal = Decimal("0.00")
    lookback_months: int = 6


class CreateGoalUseCase:
    """Create a savings goal (progress starts at zero — fund via account)."""

    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    async def execute(self, goal: Goal) -> Goal:
        """Persist a new goal; ``current_amount`` always starts at zero."""
        items = _normalize_goal_items(list(goal.items or []))
        target = (
            quantize_money(sum(i.target_amount for i in items))
            if items
            else quantize_money(goal.target_amount)
        )
        created = goal.model_copy(
            update={
                "target_amount": target,
                "current_amount": Decimal("0.00"),
                "items": [
                    i.model_copy(update={"current_amount": Decimal("0.00")})
                    for i in items
                ],
                "created_at": goal.created_at or _utc_now(),
                "status": GoalStatus.ACTIVE,
                "is_completed": False,
                "closed_early": False,
                "cached_projection": None,
            }
        )
        return await self._goals.create(Goal.model_validate(created.model_dump()))


class UpdateGoalUseCase:
    """Update goal metadata (progress only changes via contributions)."""

    def __init__(
        self,
        goals: GoalRepository,
        currencies: Optional[CurrencyRepository] = None,
    ) -> None:
        self._goals = goals
        self._currencies = currencies

    async def execute(self, goal: Goal) -> Goal:
        """Update name/target/deadline/priority/currency; keep ledger progress.

        Changing currency converts ``current_amount`` via RateBook, or refuses
        when the rate is missing.
        """
        existing = await self._goals.get_by_id(goal.id)
        if existing is None:
            raise ValueError(f"Goal not found: {goal.id}")

        status = goal.status if isinstance(goal.status, GoalStatus) else GoalStatus(goal.status)
        incoming_items = _normalize_goal_items(list(goal.items or []))
        if incoming_items:
            by_id = {i.id: i for i in existing.items}
            merged: list[GoalItem] = []
            for idx, item in enumerate(incoming_items):
                prev = by_id.get(item.id)
                merged.append(
                    item.model_copy(
                        update={
                            "current_amount": (
                                prev.current_amount if prev is not None else Decimal("0.00")
                            ),
                            "status": (
                                prev.status if prev is not None else GoalItemStatus.OPEN
                            ),
                            "closed_at": prev.closed_at if prev is not None else None,
                            "sort_order": idx,
                        }
                    )
                )
            target = quantize_money(sum(i.target_amount for i in merged))
            current = quantize_money(sum(i.current_amount for i in merged))
            if not existing.items and existing.current_amount > 0 and merged:
                merged[0] = merged[0].model_copy(
                    update={"current_amount": quantize_money(existing.current_amount)}
                )
                current = quantize_money(sum(i.current_amount for i in merged))
        else:
            merged = []
            target = quantize_money(goal.target_amount)
            current = quantize_money(existing.current_amount)

        new_ccy = (goal.currency or existing.currency or "RUB").upper()
        old_ccy = (existing.currency or "RUB").upper()
        if new_ccy != old_ccy and current != 0:
            if self._currencies is None:
                raise ValueError(f"No exchange rate for {old_ccy}/{new_ccy}")
            rates = await self._currencies.list_rates()
            converted = RateBook(rates).convert(current, old_ccy, new_ccy)
            if converted is None:
                raise ValueError(f"No exchange rate for {old_ccy}/{new_ccy}")
            current = quantize_money(converted)
            if merged:
                ratio = (
                    converted / existing.current_amount
                    if existing.current_amount > 0
                    else Decimal("1")
                )
                merged = [
                    item.model_copy(
                        update={
                            "current_amount": quantize_money(item.current_amount * ratio)
                        }
                    )
                    for item in merged
                ]
                current = quantize_money(sum(i.current_amount for i in merged))

        if status == GoalStatus.ARCHIVED:
            pass
        elif merged:
            if all(i.is_closed for i in merged):
                status = GoalStatus.COMPLETED
            elif status == GoalStatus.COMPLETED:
                status = GoalStatus.ACTIVE
        elif current >= target:
            status = GoalStatus.COMPLETED
        elif status == GoalStatus.COMPLETED and current < target:
            status = GoalStatus.ACTIVE

        updated = goal.model_copy(
            update={
                "currency": new_ccy,
                "current_amount": current,
                "target_amount": target,
                "items": merged,
                "status": status,
                "is_completed": status == GoalStatus.COMPLETED
                or (status == GoalStatus.ARCHIVED and current >= target),
                "cached_projection": existing.cached_projection,
                "closed_early": existing.closed_early,
            }
        )
        return await self._goals.update(Goal.model_validate(updated.model_dump()))


class DeleteGoalUseCase:
    """Delete a goal and unlink contribution transactions (cash stays on accounts)."""

    def __init__(
        self,
        goals: GoalRepository,
        transactions: Optional[TransactionRepository] = None,
        session_factory: object = None,
    ) -> None:
        self._goals = goals
        self._transactions = transactions
        self._session_factory = session_factory

    async def execute(self, goal_id: str) -> bool:
        """Remove a goal; unlink txs without reversing cash.

        Clears ``goal_id`` but keeps ``goal_credit_amount`` so budget
        recalculate never treats former contributions as category spend.
        """

        async def _run() -> bool:
            if self._transactions is not None:
                await self._transactions.clear_goal_links(goal_id)
            return await self._goals.delete(goal_id)

        if self._session_factory is not None:
            from lib.domain.unit_of_work import in_unit_of_work, unit_of_work

            if in_unit_of_work():
                return await _run()
            with unit_of_work(self._session_factory):  # type: ignore[arg-type]
                return await _run()
        return await _run()


class ListGoalsUseCase:
    """List savings goals."""

    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    async def execute(
        self,
        *,
        status: GoalStatus | str | None = None,
        include_completed: bool = True,
        currency: str | None = None,
        min_priority: int | None = None,
        sort_by: str = "priority",
    ) -> list[Goal]:
        """Return goals with optional filters and sorting."""
        return await self._goals.list(
            status=status,
            include_completed=include_completed,
            currency=currency,
            min_priority=min_priority,
            sort_by=sort_by,
        )


class ArchiveGoalUseCase:
    """Move a goal to archived status."""

    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    async def execute(self, goal_id: str) -> Goal:
        goal = await self._goals.get_by_id(goal_id)
        if goal is None:
            raise ValueError(f"Goal not found: {goal_id}")
        if goal.status == GoalStatus.ARCHIVED:
            return goal
        updated = goal.model_copy(update={"status": GoalStatus.ARCHIVED})
        return await self._goals.update(updated)


class DuplicateGoalUseCase:
    """Create a similar goal with zero progress."""

    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    async def execute(self, goal_id: str, *, name_suffix: str = " (копия)") -> Goal:
        source = await self._goals.get_by_id(goal_id)
        if source is None:
            raise ValueError(f"Goal not found: {goal_id}")
        new_name = f"{source.name}{name_suffix}"
        copy = source.model_copy(
            update={
                "id": str(uuid4()),
                "name": new_name,
                "category_link": new_name,
                "current_amount": Decimal("0.00"),
                "status": GoalStatus.ACTIVE,
                "is_completed": False,
                "closed_early": False,
                "cached_projection": None,
                "created_at": _utc_now(),
                "items": [
                    item.model_copy(
                        update={
                            "id": str(uuid4()),
                            "current_amount": Decimal("0.00"),
                            "status": GoalItemStatus.OPEN,
                            "closed_at": None,
                        }
                    )
                    for item in source.items
                ],
            }
        )
        return await self._goals.create(Goal.model_validate(copy.model_dump()))


class ContributeToGoalUseCase:
    """Move money from an account into a goal (creates an expense transaction)."""

    def __init__(
        self,
        goals: GoalRepository,
        accounts: AccountRepository,
        add_transaction: "AddTransactionUseCase",
        currencies: CurrencyRepository,
        transactions: TransactionRepository | None = None,
    ) -> None:
        self._goals = goals
        self._accounts = accounts
        self._add_transaction = add_transaction
        self._currencies = currencies
        self._transactions = transactions

    async def execute(
        self,
        goal_id: str,
        amount: Decimal,
        *,
        account_id: str,
        item_id: str | None = None,
    ) -> Goal:
        """Debit ``account_id`` and increase the goal's ``current_amount``.

        ``amount`` is in the account currency. It is converted into the goal
        currency via :class:`RateBook` and stored as ``goal_credit_amount``.
        """
        amount = quantize_money(amount)
        if amount <= 0:
            raise ValueError("Contribution amount must be positive")
        if not (account_id or "").strip():
            raise ValueError("Account is required to fund a goal")

        goal = await self._goals.get_by_id(goal_id)
        if goal is None:
            raise ValueError(f"Goal not found: {goal_id}")
        if goal.status == GoalStatus.ARCHIVED:
            raise ValueError("Goal is archived")
        if goal.status != GoalStatus.ACTIVE:
            raise ValueError("Goal is already completed")
        if goal.items and not item_id:
            raise ValueError("Goal item is required")

        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")

        rates = await self._currencies.list_rates()
        book = RateBook(rates)
        credit = book.convert(amount, account.currency, goal.currency)
        if credit is None:
            raise ValueError(
                f"No exchange rate for {account.currency}/{goal.currency}"
            )
        credit = quantize_money(credit)
        if credit <= 0:
            raise ValueError("Converted contribution amount must be positive")

        await self._add_transaction.execute(
            Transaction(
                account_id=account.id,
                amount=amount,
                category=_savings_category(goal),
                date=_utc_now(),
                comment=goal.name,
                type=TransactionType.EXPENSE,
                currency=account.currency,
                goal_id=goal.id,
                goal_item_id=item_id,
                goal_credit_amount=credit,
            )
        )
        updated = await self._goals.get_by_id(goal_id)
        if updated is None:
            raise ValueError(f"Goal not found after contribution: {goal_id}")

        if self._transactions is not None:
            try:
                await GetGoalProjectionUseCase(
                    self._goals, self._transactions
                ).execute(goal_id)
                refreshed = await self._goals.get_by_id(goal_id)
                if refreshed is not None:
                    return refreshed
            except Exception:  # noqa: BLE001
                pass
        return updated


class GetGoalProjectionUseCase:
    """Compute savings pace, required monthly amount, and on-track status."""

    def __init__(
        self,
        goals: GoalRepository,
        transactions: TransactionRepository,
        *,
        lookback_months: int = 6,
    ) -> None:
        self._goals = goals
        self._transactions = transactions
        self._lookback_months = max(1, int(lookback_months))

    async def execute(self, goal_id: str) -> GoalProjection:
        goal = await self._goals.get_by_id(goal_id)
        if goal is None:
            raise ValueError(f"Goal not found: {goal_id}")

        now = _utc_now()
        remaining = goal.remaining_amount
        projection = GoalProjection(
            goal_id=goal.id,
            remaining_amount=remaining,
            lookback_months=self._lookback_months,
        )

        if remaining <= 0:
            projection.required_monthly_contribution = Decimal("0.00")
            projection.projected_completion_date = now
            projection.is_on_track = True
            await self._cache(goal, projection)
            return projection

        if goal.deadline is not None:
            from lib.domain.use_cases.goal_insights import required_monthly_for_goal

            projection.required_monthly_contribution = required_monthly_for_goal(
                remaining,
                goal.deadline,
                now=now,
            )

        from lib.domain.use_cases.goal_insights import days_between, net_goal_credit_flow

        days_left = (
            days_between(now, goal.deadline) if goal.deadline is not None else None
        )
        # Short horizons: use recent daily pace instead of a 6-month average.
        short_horizon = days_left is not None and 0 < days_left <= 45
        if short_horizon:
            lookback_days = max(7.0, min(float(days_left) * 2.0, 30.0))
            lookback_start = now - timedelta(days=lookback_days)
            txs = await self._transactions.list(
                goal_id=goal.id, date_from=lookback_start
            )
            net_flow = net_goal_credit_flow(txs)
            created = goal.created_at
            if created is not None:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_days = max(days_between(created, now), 1.0 / 24.0)
                lookback_days = min(lookback_days, age_days)
            avg_daily = (
                quantize_money(net_flow / Decimal(str(lookback_days)))
                if net_flow > 0
                else Decimal("0.00")
            )
            projection.average_monthly_contribution = quantize_money(
                avg_daily * Decimal("30.4375")
            )
            if avg_daily > 0:
                days_needed = float(remaining / avg_daily)
                projection.projected_completion_date = now + timedelta(
                    days=max(days_needed, 0.0)
                )
            else:
                projection.projected_completion_date = None
        else:
            lookback_start = now - timedelta(days=self._lookback_months * 30.4375)
            txs = await self._transactions.list(
                goal_id=goal.id, date_from=lookback_start
            )
            net_flow = net_goal_credit_flow(txs)
            divisor = _pace_divisor_months(
                now, self._lookback_months, goal.created_at
            )
            avg = (
                quantize_money(net_flow / divisor)
                if net_flow > 0
                else Decimal("0.00")
            )
            projection.average_monthly_contribution = avg

            if avg > 0:
                months_needed = float(remaining / avg)
                projection.projected_completion_date = _add_months(now, months_needed)
            else:
                projection.projected_completion_date = None

        if goal.deadline is None:
            projection.is_on_track = None
        elif days_left is not None and days_left <= 0:
            projection.is_on_track = False
        elif projection.projected_completion_date is None:
            projection.is_on_track = False
        else:
            projection.is_on_track = (
                projection.projected_completion_date <= goal.deadline
            )

        await self._cache(goal, projection)
        return projection

    async def _cache(self, goal: Goal, projection: GoalProjection) -> None:
        payload: dict[str, Any] = {
            "required_monthly_contribution": (
                str(projection.required_monthly_contribution)
                if projection.required_monthly_contribution is not None
                else None
            ),
            "projected_completion_date": (
                projection.projected_completion_date.isoformat()
                if projection.projected_completion_date
                else None
            ),
            "is_on_track": projection.is_on_track,
            "average_monthly_contribution": str(
                projection.average_monthly_contribution
            ),
            "remaining_amount": str(projection.remaining_amount),
            "lookback_months": projection.lookback_months,
            "computed_at": _utc_now().isoformat(),
        }
        updated = goal.model_copy(update={"cached_projection": payload})
        try:
            await self._goals.update(updated)
        except Exception:  # noqa: BLE001
            # Cache is best-effort; projection is still returned.
            pass


class DeleteGoalContributionUseCase:
    """Delete a goal contribution transaction and reverse goal progress."""

    def __init__(
        self,
        transactions: TransactionRepository,
        delete_transaction: "DeleteTransactionUseCase",
    ) -> None:
        self._transactions = transactions
        self._delete_transaction = delete_transaction

    async def execute(self, transaction_id: str, *, goal_id: str) -> bool:
        tx = await self._transactions.get_by_id(transaction_id)
        if tx is None:
            return False
        if tx.goal_id != goal_id:
            raise ValueError("Transaction is not linked to this goal")
        return await self._delete_transaction.execute(transaction_id)


class CloseGoalItemUseCase:
    """Mark one open sub-position as closed (with or without full funding)."""

    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    async def execute(self, goal_id: str, item_id: str) -> Goal:
        goal = await self._goals.get_by_id(goal_id)
        if goal is None:
            raise ValueError(f"Goal not found: {goal_id}")
        if goal.status != GoalStatus.ACTIVE:
            raise ValueError("Goal is not active")
        if not goal.items:
            raise ValueError("Goal has no items to withdraw from")
        now = _utc_now()
        updated_items: list[GoalItem] = []
        found = False
        for item in goal.items:
            if item.id != item_id:
                updated_items.append(item)
                continue
            found = True
            if item.is_closed:
                return goal
            updated_items.append(
                item.model_copy(
                    update={"status": GoalItemStatus.CLOSED, "closed_at": now}
                )
            )
        if not found:
            raise ValueError("Goal item not found")
        payload = goal.model_copy(update={"items": updated_items})
        saved = Goal.model_validate(payload.model_dump())
        return await self._goals.update(saved)


class CloseGoalEarlyUseCase:
    """Archive an active goal before the target is fully reached."""

    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    async def execute(self, goal_id: str) -> Goal:
        goal = await self._goals.get_by_id(goal_id)
        if goal is None:
            raise ValueError(f"Goal not found: {goal_id}")
        if goal.status == GoalStatus.ARCHIVED:
            return goal
        if goal.status != GoalStatus.ACTIVE:
            raise ValueError("Goal is already completed")
        updated = goal.model_copy(
            update={"status": GoalStatus.ARCHIVED, "closed_early": True}
        )
        return await self._goals.update(Goal.model_validate(updated.model_dump()))


class WithdrawFromGoalUseCase:
    """Return savings from a goal back to an account (partial withdrawal)."""

    def __init__(
        self,
        goals: GoalRepository,
        accounts: AccountRepository,
        add_transaction: "AddTransactionUseCase",
        currencies: CurrencyRepository,
    ) -> None:
        self._goals = goals
        self._accounts = accounts
        self._add_transaction = add_transaction
        self._currencies = currencies

    async def execute(
        self,
        goal_id: str,
        amount: Decimal,
        *,
        account_id: str,
        item_id: str | None = None,
    ) -> Goal:
        from lib.domain.entities.transaction import Transaction, TransactionType

        amount = quantize_money(amount)
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        goal = await self._goals.get_by_id(goal_id)
        if goal is None:
            raise ValueError(f"Goal not found: {goal_id}")
        if goal.status != GoalStatus.ACTIVE:
            raise ValueError("Goal is not active")
        if goal.items:
            if not item_id:
                raise ValueError("Goal item is required")
            item = next((i for i in goal.items if i.id == item_id), None)
            if item is None:
                raise ValueError("Goal item not found")
            if item.is_closed:
                raise ValueError("Goal item is already closed")
            if amount > item.current_amount:
                raise ValueError("Withdrawal exceeds item balance")
        elif amount > goal.current_amount:
            raise ValueError("Withdrawal exceeds goal balance")
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")

        rates = await self._currencies.list_rates()
        book = RateBook(rates)
        credit = book.convert(amount, goal.currency, account.currency)
        if credit is None:
            raise ValueError(
                f"No exchange rate for {goal.currency}/{account.currency}"
            )
        credit = quantize_money(credit)

        await self._add_transaction.execute(
            Transaction(
                account_id=account.id,
                amount=credit,
                category=_savings_category(goal),
                date=_utc_now(),
                comment=goal.name,
                type=TransactionType.INCOME,
                currency=account.currency,
                goal_id=goal.id,
                goal_item_id=item_id,
                goal_credit_amount=amount,
            )
        )
        updated = await self._goals.get_by_id(goal_id)
        if updated is None:
            raise ValueError(f"Goal not found after withdrawal: {goal_id}")
        return updated


class AppendGoalAuditUseCase:
    """Record a goal audit log entry."""

    def __init__(self, audit_repository) -> None:
        self._audit = audit_repository

    async def execute(
        self,
        goal_id: str,
        action: str,
        *,
        details: dict | None = None,
    ) -> None:
        from lib.domain.entities.goal_audit import GoalAuditEntry

        await self._audit.append(
            GoalAuditEntry(goal_id=goal_id, action=action, details=details)
        )


class ListGoalAuditUseCase:
    """List audit entries for one goal."""

    def __init__(self, audit_repository) -> None:
        self._audit = audit_repository

    async def execute(self, goal_id: str, *, limit: int = 30) -> list:
        return await self._audit.list_for_goal(goal_id, limit=limit)
