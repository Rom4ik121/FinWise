"""Goals CRUD page with progress, projection, and contribution history."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.goal import Goal, GoalItemStatus, GoalStatus
from lib.domain.entities.money import quantize_money
from lib.core.config import ACCOUNT_COLORS, normalize_savings_category
from lib.domain.use_cases.goal_insights import (
    projected_date_from_planned,
    required_monthly_for_goal,
)
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.account_icons import (
    account_icon_control,
    account_icon_groups,
    is_valid_account_icon,
)
from lib.presentation.goals_templates import GOAL_TEMPLATES, GoalTemplate, goal_template_chip
from lib.presentation.notification_badges import (
    GOAL_ALERT_KINDS,
    mark_related_read,
    pending_related_ids,
)
from lib.presentation.styles import (
    ICON_CATALOG_GLYPH,
    card_surface,
    choice_chips,
    form_section,
    form_hint,
    muted_text,
    page_header,
    section_title,
)
from lib.presentation.money_input import (
    attach_grouped_digits,
    format_amount_value,
    make_amount_field,
    parse_amount,
)
from lib.presentation.utils import (
    bind_dropdown_select,
    format_date,
    format_money,
    format_money_compact,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    snack_exception,
    tr,
    try_convert_amount,
)
from lib.presentation.widgets.appearance_picker import open_color_picker, open_icon_picker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.currency_ticker_picker import CurrencyTickerPicker
from lib.presentation.widgets.date_time_field import DateTimeField
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form
from lib.presentation.widgets.goal_items_editor import GoalItemsEditor
from lib.presentation.widgets.goal_progress import GoalProgress, goal_item_progress_card
from lib.presentation.widgets.goal_sparkline import goal_contribution_sparkline
from lib.presentation.widgets.goal_summary_ring import goals_summary_ring
from lib.presentation.widgets.goal_swipe_card import swipe_goal_card
from lib.presentation.layout import h_scroll, make_v_scroll
from lib.presentation.widgets.loading import fill_loading, loading_indicator

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_CONTRIB_PAGE = 40
_SORT_KEYS = ("priority", "deadline", "progress", "created_at")
_STATUS_FILTERS = ("active", "completed", "archived")
_GROUP_MODES = ("none", "category", "priority")
_MILESTONE_PCTS = (25, 50, 75)


class GoalsPage(ft.Column):
    """Manage savings goals."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._list = make_v_scroll(spacing=14)
        self._status_filter = "active"
        self._sort_by = "priority"
        self._group_mode = "none"
        self._search_query = ""
        self._alert_ids: set[str] = set()
        self._token = -1
        self._search_tf = ft.TextField(
            hint_text=tr("goal.search_hint", state.language),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            filled=True,
            expand=True,
            on_change=self._on_search_change,
        )
        super().__init__(
            expand=True,
            spacing=0,
            controls=[
                page_header(
                    tr("nav.goals", state.language),
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _e: state.close_secondary(),
                    ),
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.TUNE,
                            tooltip=tr("action.filters", state.language),
                            on_click=lambda _e: self._open_filters(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            tooltip=tr("action.add", state.language),
                            on_click=lambda _e: self._open_editor(),
                        ),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.only(left=12, right=12, top=8, bottom=8),
                    content=self._search_tf,
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.symmetric(horizontal=12),
                    content=self._list,
                ),
            ],
        )
        state.subscribe(self._on_state)
        run_async(page, self.reload)

    def _on_state(self, state: "AppState") -> None:
        if state.goals_token != self._token:
            run_async(self._page, self.reload)

    def _on_search_change(self, e: ft.ControlEvent) -> None:
        self._search_query = str(getattr(e.control, "value", "") or "")
        run_async(self._page, self.reload)

    def _filter_goals(self, goals: list[Goal]) -> list[Goal]:
        q = self._search_query.strip().lower()
        if not q:
            return goals
        filtered: list[Goal] = []
        for goal in goals:
            if q in goal.name.lower():
                filtered.append(goal)
                continue
            if any(q in item.name.lower() for item in goal.items):
                filtered.append(goal)
        return filtered

    def _open_filters(self) -> None:
        lang = self._state.language
        holder = {
            "status": self._status_filter,
            "sort": self._sort_by,
            "group": self._group_mode,
        }
        status_chips = choice_chips(
            [
                (key, tr(f"goal.status.{key}", lang))
                for key in _STATUS_FILTERS
            ],
            value=holder["status"],
            on_changed=lambda value: holder.__setitem__("status", value),
        )
        sort_chips = choice_chips(
            [
                (key, tr(f"goal.sort.{key}", lang))
                for key in _SORT_KEYS
            ],
            value=holder["sort"],
            on_changed=lambda value: holder.__setitem__("sort", value),
        )
        group_chips = choice_chips(
            [
                (key, tr(label_key, lang))
                for key, label_key in (
                    ("none", "goal.group_none"),
                    ("category", "goal.group_by_category"),
                    ("priority", "goal.group_by_priority"),
                )
            ],
            value=holder["group"] if holder["group"] in _GROUP_MODES else "none",
            on_changed=lambda value: holder.__setitem__("group", value),
        )

        async def _apply() -> None:
            self._status_filter = str(holder["status"] or "active")
            self._sort_by = str(holder["sort"] or "priority")
            group_val = str(holder["group"] or "none")
            self._group_mode = group_val if group_val in _GROUP_MODES else "none"
            close()
            await self.reload()

        close = open_fullscreen_form(
            self._page,
            title=tr("action.filters", lang),
            lang=lang,
            overlay_key="goal_filters",
            body=[
                form_section(
                    tr("goal.filter_status", lang),
                    [status_chips],
                    hint=tr("goal.filter_status_hint", lang),
                    icon=ft.Icons.FILTER_LIST,
                ),
                form_section(
                    tr("goal.filter_sort", lang),
                    [sort_chips],
                    hint=tr("goal.filter_sort_hint", lang),
                    icon=ft.Icons.SORT,
                ),
                form_section(
                    tr("goal.group_mode", lang),
                    [group_chips],
                    hint=tr("goal.filter_group_hint", lang),
                    icon=ft.Icons.WIDGETS_OUTLINED,
                ),
            ],
            on_save=_apply,
            save_label=tr("action.apply", lang, default=tr("action.save", lang)),
            save_icon=ft.Icons.CHECK,
        )

    async def reload(self) -> None:
        """Reload goals list."""
        self._token = self._state.goals_token
        lang = self._state.language
        fill_loading(self._list)
        safe_update(self._list)
        self._alert_ids = pending_related_ids(
            self._state.container,
            self._state.settings,
            GOAL_ALERT_KINDS,
        )
        # Do not auto-mark alerts read here — only when the user opens a goal.
        try:
            goals = await self._state.container.list_goals.execute(
                status=self._status_filter,
                sort_by=self._sort_by,
            )
            goals = self._filter_goals(goals)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            self._list.controls = [EmptyState(tr("error.generic", lang))]
            safe_update(self._list)
            return
        if not goals:
            search_active = bool(self._search_query.strip())
            if search_active:
                empty_key = "empty.goals_search"
                show_add = False
            elif self._status_filter != "active" or self._group_mode != "none":
                empty_key = "empty.goals_filtered"
                show_add = False
            else:
                empty_key = "empty.goals"
                show_add = True
            self._list.controls = [
                EmptyState(
                    tr(empty_key, lang),
                    action_label=tr("action.add", lang) if show_add else None,
                    on_action=lambda _e: self._open_editor() if show_add else None,
                )
            ]
            safe_update(self._list)
            return

        base = self._state.base_currency
        book = await load_rate_book(self._state.container)
        total_target = Decimal("0")
        total_saved = Decimal("0")
        fx_ok = True
        for g in goals:
            target = try_convert_amount(book, g.target_amount, g.currency, base)
            saved = try_convert_amount(book, g.current_amount, g.currency, base)
            if target is None or saved is None:
                fx_ok = False
                continue
            total_target += target
            total_saved += saved
        if not fx_ok:
            snack(self._page, tr("fx.missing_rates", lang), error=True)
        cards: list[ft.Control] = []
        if self._status_filter == "active" and fx_ok and total_target > 0:
            cards.append(
                goals_summary_ring(
                    saved=total_saved,
                    target=total_target,
                    currency=base,
                    language=lang,
                )
            )
            cards.append(ft.Container(height=8))
        if self._group_mode == "category":
            grouped: dict[str, list[Goal]] = defaultdict(list)
            for g in goals:
                key = (g.name or "").strip() or tr("goal.uncategorized", lang)
                grouped[key].append(g)
            for category, items in sorted(grouped.items(), key=lambda kv: kv[0].lower()):
                cards.append(section_title(category))
                cards.extend(self._goal_card(g) for g in items)
        elif self._group_mode == "priority":
            by_priority: dict[int, list[Goal]] = defaultdict(list)
            for g in goals:
                by_priority[int(g.priority or 3)].append(g)
            for priority in range(5, 0, -1):
                items = by_priority.get(priority, [])
                if not items:
                    continue
                cards.append(
                    section_title(tr("goal.priority_block", lang, n=str(priority)))
                )
                cards.extend(self._goal_card(g) for g in items)
        else:
            cards.extend(self._goal_card(g) for g in goals)

        self._list.controls = cards
        safe_update(self._list)

    def _goal_card(self, goal: Goal) -> ft.Control:
        cache = goal.cached_projection or {}
        required_raw = cache.get("required_monthly_contribution")
        required: Decimal | None = None
        if required_raw not in (None, ""):
            try:
                required = Decimal(str(required_raw))
            except Exception:  # noqa: BLE001
                required = None
        on_track = cache.get("is_on_track")
        if on_track is not None and not isinstance(on_track, bool):
            on_track = None
        card = GoalProgress(
            goal,
            currency=goal.currency or self._state.base_currency,
            language=self._state.language,
            alert=goal.id in self._alert_ids,
            required_monthly=required,
            is_on_track=on_track,
            on_click=self._open_detail,
            on_alert=self._open_detail,
            on_contribute=None,
            on_item_contribute=(
                (lambda item, g=goal: self._contribute(g, item_id=item.id))
                if goal.status == GoalStatus.ACTIVE
                else None
            ),
        )
        if goal.status == GoalStatus.ACTIVE:
            return swipe_goal_card(
                card,
                language=self._state.language,
                on_contribute=lambda g=goal: self._contribute(g),
                on_edit=lambda g=goal: self._open_editor(g),
            )
        return swipe_goal_card(
            card,
            language=self._state.language,
            on_edit=lambda g=goal: self._open_editor(g),
        )

    def _crossed_milestones(self, old_ratio: float, new_ratio: float) -> list[int]:
        old_pct = int(max(0.0, min(old_ratio, 1.0)) * 100)
        new_pct = int(max(0.0, min(new_ratio, 1.0)) * 100)
        return [m for m in _MILESTONE_PCTS if old_pct < m <= new_pct]

    def _notify_milestones(
        self,
        goal: Goal,
        updated: Goal,
        *,
        old_ratio: float,
        old_item_ratios: dict[str, float] | None = None,
        item_id: str | None = None,
    ) -> None:
        lang = self._state.language
        if (
            not self._state.settings.notifications_enabled
            or not self._state.settings.goal_milestones
        ):
            return
        notifier = getattr(self._state.container, "notification_service", None)
        from lib.infrastructure.services.notification_service import NotificationKind

        new_ratio = float(updated.progress_ratio)
        for pct in self._crossed_milestones(old_ratio, new_ratio):
            title = tr("notify.goal_milestone_percent", lang, name=updated.name, percent=str(pct))
            if notifier is not None:
                notifier.push(
                    title=title,
                    body=updated.name,
                    kind=NotificationKind.GOAL_MILESTONE,
                    related_id=updated.id,
                )
            else:
                self._state.push_notification(title)

        if item_id and old_item_ratios is not None:
            for item in updated.items:
                if item.id != item_id:
                    continue
                old_ir = old_item_ratios.get(item_id, 0.0)
                new_ir = float(item.progress_ratio)
                for pct in self._crossed_milestones(old_ir, new_ir):
                    title = tr(
                        "notify.goal_item_milestone_percent",
                        lang,
                        item=item.name,
                        percent=str(pct),
                    )
                    if notifier is not None:
                        notifier.push(
                            title=title,
                            body=f"{updated.name} · {item.name}",
                            kind=NotificationKind.GOAL_MILESTONE,
                            related_id=updated.id,
                        )
                    else:
                        self._state.push_notification(title)

    def _contribute(
        self,
        goal: Goal,
        *,
        item_id: str | None = None,
        close_holder: dict | None = None,
    ) -> None:
        lang = self._state.language

        async def _open() -> None:
            try:
                accounts = await self._state.container.list_accounts.execute(
                    active_only=True
                )
                book = await load_rate_book(self._state.container)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            if not accounts:
                snack(self._page, tr("error.no_accounts", lang), error=True)
                return

            amount_tf = make_amount_field(
                lang,
                label=tr("field.amount", lang),
                autofocus=True,
            )
            convert_hint = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
            account_dd = ft.Dropdown(
                label=tr("field.account", lang),
                value=accounts[0].id,
                options=[
                    ft.DropdownOption(
                        key=a.id,
                        text=f"{a.name} · {format_money(a.balance, a.currency)}",
                    )
                    for a in accounts
                ],
            )
            open_items = [
                i for i in goal.items if not i.is_closed
            ]
            item_dd: ft.Dropdown | None = None
            if open_items:
                default_item = item_id if item_id in {i.id for i in open_items} else open_items[0].id
                item_dd = ft.Dropdown(
                    label=tr("goal.select_item", lang),
                    value=default_item,
                    options=[
                        ft.DropdownOption(
                            key=i.id,
                            text=f"{i.name} · {format_money(i.remaining_amount, goal.currency)}",
                        )
                        for i in open_items
                    ],
                )

            def _refresh_conversion(_e: ft.ControlEvent | None = None) -> None:
                account = next(
                    (a for a in accounts if a.id == account_dd.value), accounts[0]
                )
                try:
                    amount = parse_amount(amount_tf.value)
                except (InvalidOperation, ValueError):
                    convert_hint.value = ""
                    safe_update(convert_hint)
                    return
                if amount <= 0:
                    convert_hint.value = ""
                    safe_update(convert_hint)
                    return
                converted = book.convert(amount, account.currency, goal.currency)
                if converted is None:
                    convert_hint.value = tr(
                        "goal.no_rate",
                        lang,
                        pair=f"{account.currency}/{goal.currency}",
                    )
                    convert_hint.color = ft.Colors.ERROR
                else:
                    convert_hint.value = tr(
                        "goal.converted_amount",
                        lang,
                        amount=format_money(converted, goal.currency),
                    )
                    convert_hint.color = ft.Colors.ON_SURFACE_VARIANT
                safe_update(convert_hint)

            attach_grouped_digits(
                amount_tf, lang, extra_on_change=_refresh_conversion
            )
            bind_dropdown_select(account_dd, _refresh_conversion)

            async def _save() -> None:
                try:
                    amount = parse_amount(amount_tf.value)
                    if amount <= 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    snack(self._page, tr("invalid_amount", lang), error=True)
                    return
                account_id = account_dd.value or accounts[0].id
                account = next((a for a in accounts if a.id == account_id), accounts[0])
                if amount > account.balance:
                    snack(self._page, tr("error.insufficient_funds", lang), error=True)
                    return
                converted = book.convert(amount, account.currency, goal.currency)
                if converted is None:
                    snack(
                        self._page,
                        tr(
                            "goal.no_rate",
                            lang,
                            pair=f"{account.currency}/{goal.currency}",
                        ),
                        error=True,
                    )
                    return
                remaining = quantize_money(
                    max(Decimal("0"), goal.target_amount - goal.current_amount)
                )
                if remaining > 0 and converted > remaining:
                    snack(
                        self._page,
                        tr(
                            "goal.overfund_warn",
                            lang,
                            remaining=format_money(remaining, goal.currency),
                        ),
                        error=False,
                    )

                try:
                    old_ratio = float(goal.progress_ratio)
                    old_item_ratios = {i.id: float(i.progress_ratio) for i in goal.items}
                    updated = await self._state.container.contribute_to_goal.execute(
                        goal.id,
                        amount,
                        account_id=account_id,
                        item_id=item_dd.value if item_dd is not None else None,
                    )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                close()
                self._state.bump_refresh("dashboard", "accounts", "transactions", "goals")
                self._notify_milestones(
                    goal,
                    updated,
                    old_ratio=old_ratio,
                    old_item_ratios=old_item_ratios,
                    item_id=item_dd.value if item_dd is not None else None,
                )
                await self.reload()
                if close_holder is not None:
                    closer = close_holder.get("close")
                    if callable(closer):
                        closer()
                    self._open_detail(updated)
                elif (
                    updated.is_completed
                    and self._state.settings.notifications_enabled
                    and self._state.settings.goal_milestones
                ):
                    notifier = getattr(
                        self._state.container, "notification_service", None
                    )
                    if notifier is not None:
                        from lib.infrastructure.services.notification_service import (
                            NotificationKind,
                        )

                        notifier.push(
                            title=tr("notify.goal_reached", lang),
                            body=updated.name,
                            kind=NotificationKind.GOAL_MILESTONE,
                            related_id=updated.id,
                        )
                    else:
                        self._state.push_notification(
                            f"{tr('notify.goal_reached', lang)} {updated.name}"
                        )
                else:
                    snack(self._page, tr("action.saved", lang))

            body_fields: list[ft.Control] = [account_dd]
            if item_dd is not None:
                body_fields.append(item_dd)
            body_fields.extend([amount_tf, convert_hint])

            close = open_fullscreen_form(
                self._page,
                title=f"{tr('goal.contribute', lang)} · {goal.name}",
                lang=lang,
                overlay_key="goal_contribute",
                body=body_fields,
                on_save=_save,
                save_icon=ft.Icons.SAVINGS_OUTLINED,
            )

        run_async(self._page, _open)

    def _open_detail(self, goal: Goal) -> None:
        lang = self._state.language
        if goal.id in self._alert_ids:
            mark_related_read(
                self._state.container, goal.id, GOAL_ALERT_KINDS
            )
            self._alert_ids.discard(goal.id)
            self._state.bump_refresh("dashboard")
        body = ft.Column(spacing=12, scroll=ft.ScrollMode.HIDDEN, expand=True)
        close_holder: dict[str, object] = {}

        def _close_detail() -> None:
            closer = close_holder.get("close")
            if callable(closer):
                closer()

        async def _load() -> None:
            body.controls = [loading_indicator()]
            try:
                safe_update(body)
            except Exception:  # noqa: BLE001
                pass
            try:
                fresh = await self._state.container.goal_repository.get_by_id(goal.id)
                goal_obj = fresh or goal
                projection = await self._state.container.get_goal_projection.execute(
                    goal_obj.id
                )
                accounts = {
                    a.id: a
                    for a in await self._state.container.list_accounts.execute(
                        active_only=False
                    )
                }
                txs = await self._state.container.list_transactions.execute(
                    goal_id=goal_obj.id,
                    limit=_CONTRIB_PAGE + 1,
                    offset=0,
                )
                series = None
                get_series = getattr(
                    self._state.container, "get_goal_contribution_series", None
                )
                if get_series is not None:
                    series = await get_series.execute(goal_obj.id)
                audit_entries: list = []
                list_audit = getattr(self._state.container, "list_goal_audit", None)
                if list_audit is not None:
                    audit_entries = await list_audit.execute(goal_obj.id)
                budget_row: ft.Control | None = None
                get_budget = getattr(self._state.container, "get_budget_progress", None)
                if get_budget is not None and goal_obj.category_link:
                    now = datetime.now(timezone.utc)
                    try:
                        budget = await get_budget.execute(
                            category_id=normalize_savings_category(
                                goal_obj.category_link
                            ),
                            month=now.month,
                            year=now.year,
                        )
                        cat_label = localize_category_name(
                            normalize_savings_category(goal_obj.category_link), lang
                        )
                        budget_row = ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    tr(
                                        "goal.budget_link",
                                        lang,
                                        category=cat_label,
                                        spent=format_money(
                                            budget.spent, self._state.base_currency
                                        ),
                                        limit=format_money(
                                            budget.limit, self._state.base_currency
                                        ),
                                    ),
                                    size=12,
                                    expand=True,
                                ),
                                ft.TextButton(
                                    tr("goal.open_budgets", lang),
                                    on_click=lambda _e: (
                                        _close_detail(),
                                        self._state.open_secondary("budgets"),
                                    ),
                                ),
                            ],
                        )
                    except Exception:  # noqa: BLE001
                        budget_row = None
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                return

            has_more = len(txs) > _CONTRIB_PAGE
            shown = txs[:_CONTRIB_PAGE]
            offset = {"n": len(shown)}

            proj_rows: list[ft.Control] = [
                ft.Text(tr("goal.projection", lang), weight=ft.FontWeight.W_700),
            ]
            if projection.required_monthly_contribution is not None:
                proj_rows.append(
                    ft.Text(
                        f"{tr('goal.required_monthly', lang)}: "
                        f"{format_money(projection.required_monthly_contribution, goal_obj.currency)}"
                    )
                )
            if projection.projected_completion_date is not None:
                proj_rows.append(
                    ft.Text(
                        f"{tr('goal.projected_date', lang)}: "
                        f"{format_date(projection.projected_completion_date)}"
                    )
                )
            if projection.is_on_track is True:
                proj_rows.append(
                    ft.Text(tr("goal.on_track", lang), color=ft.Colors.PRIMARY)
                )
            elif projection.is_on_track is False:
                proj_rows.append(
                    ft.Text(tr("goal.off_track", lang), color=ft.Colors.ERROR)
                )

            insight_col = ft.Column(spacing=8, tight=True)
            if series is not None:
                insight_bits: list[ft.Control] = [
                    ft.Text(
                        tr("goal.contribution_trend", lang),
                        weight=ft.FontWeight.W_700,
                        size=13,
                    ),
                    goal_contribution_sparkline(series.buckets),
                ]
                if series.streak_months > 0:
                    insight_bits.append(
                        ft.Text(
                            tr(
                                "goal.streak",
                                lang,
                                months=str(series.streak_months),
                            ),
                            size=12,
                            color=ft.Colors.PRIMARY,
                        )
                    )
                insight_col.controls = insight_bits

            audit_col: ft.Control | None = None
            if audit_entries:
                audit_rows: list[ft.Control] = [
                    ft.Text(tr("goal.audit_log", lang), weight=ft.FontWeight.W_700),
                ]
                for entry in audit_entries:
                    action_key = f"goal.audit.{entry.action}"
                    label = tr(action_key, lang, default=entry.action)
                    audit_rows.append(
                        muted_text(
                            f"{format_date(entry.created_at)} · {label}"
                        )
                    )
                audit_col = ft.Column(spacing=6, tight=True, controls=audit_rows)

            contrib_col = ft.Column(spacing=8, tight=True)
            contrib_col.controls = [
                ft.Text(tr("goal.contributions", lang), weight=ft.FontWeight.W_700),
            ]
            if not shown:
                contrib_col.controls.append(muted_text("—"))
            else:
                for tx in shown:
                    contrib_col.controls.append(
                        self._contribution_row(goal_obj, tx, accounts, close_holder)
                    )

            async def _more(_e: ft.ControlEvent | None = None) -> None:
                more = await self._state.container.list_transactions.execute(
                    goal_id=goal_obj.id,
                    limit=_CONTRIB_PAGE + 1,
                    offset=offset["n"],
                )
                more_has = len(more) > _CONTRIB_PAGE
                chunk = more[:_CONTRIB_PAGE]
                offset["n"] += len(chunk)
                for tx in chunk:
                    contrib_col.controls.append(
                        self._contribution_row(goal_obj, tx, accounts, close_holder)
                    )
                load_more_btn.visible = more_has
                safe_update(contrib_col)
                safe_update(load_more_btn)

            load_more_btn = ft.TextButton(
                tr("action.load_more", lang, default="Load more"),
                visible=has_more,
                on_click=lambda e: run_async(self._page, _more, e),
            )

            async def _do_duplicate(_e: ft.ControlEvent | None = None) -> None:
                await self._duplicate(goal_obj, close_holder)

            async def _do_archive(_e: ft.ControlEvent | None = None) -> None:
                await self._archive(goal_obj, close_holder)

            async def _do_close_early(_e: ft.ControlEvent | None = None) -> None:
                await self._close_early(goal_obj, close_holder)

            def _edit(_e: ft.ControlEvent | None = None) -> None:
                _close_detail()
                self._open_editor(goal_obj)

            def _contrib(_e: ft.ControlEvent | None = None) -> None:
                _close_detail()
                self._contribute(goal_obj)

            def _withdraw(_e: ft.ControlEvent | None = None) -> None:
                self._open_withdraw(goal_obj, close_holder)

            actions: list[ft.Control] = []
            if goal_obj.status == GoalStatus.ACTIVE:
                actions.append(
                    ft.FilledButton(
                        tr("goal.contribute", lang),
                        icon=ft.Icons.ADD,
                        on_click=_contrib,
                    )
                )
                if goal_obj.current_amount > 0:
                    actions.append(
                        ft.OutlinedButton(
                            tr("goal.withdraw", lang),
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            on_click=_withdraw,
                        )
                    )
            actions.extend(
                [
                    ft.FilledTonalButton(
                        tr("action.edit", lang),
                        icon=ft.Icons.EDIT_OUTLINED,
                        on_click=_edit,
                    ),
                    ft.OutlinedButton(
                        tr("goal.duplicate", lang),
                        icon=ft.Icons.CONTENT_COPY,
                        on_click=lambda e: run_async(self._page, _do_duplicate, e),
                    ),
                ]
            )
            if goal_obj.status == GoalStatus.COMPLETED:
                actions.append(
                    ft.OutlinedButton(
                        tr("goal.archive", lang),
                        icon=ft.Icons.ARCHIVE_OUTLINED,
                        on_click=lambda e: run_async(self._page, _do_archive, e),
                    )
                )
            elif goal_obj.status == GoalStatus.ACTIVE:
                actions.append(
                    ft.OutlinedButton(
                        tr("goal.close_early", lang),
                        icon=ft.Icons.FLAG_OUTLINED,
                        on_click=lambda e: run_async(self._page, _do_close_early, e),
                    )
                )

            items_col: ft.Control | None = None
            if goal_obj.items:
                item_rows: list[ft.Control] = [
                    ft.Text(tr("goal.items_section", lang), weight=ft.FontWeight.W_700),
                ]
                for item in sorted(goal_obj.items, key=lambda i: i.sort_order):
                    close_handler = None
                    contribute_handler = None
                    if goal_obj.status == GoalStatus.ACTIVE and not item.is_closed:
                        close_handler = lambda iid=item.id: self._close_item(
                            goal_obj.id, iid, close_holder
                        )
                        contribute_handler = lambda iid=item.id: self._contribute(
                            goal_obj,
                            item_id=iid,
                            close_holder=close_holder,
                        )
                    item_rows.append(
                        goal_item_progress_card(
                            item,
                            currency=goal_obj.currency,
                            language=lang,
                            on_close=close_handler,
                            on_contribute=contribute_handler,
                        )
                    )
                items_col = ft.Column(spacing=10, tight=True, controls=item_rows)

            detail_controls: list[ft.Control] = [
                GoalProgress(
                    goal_obj,
                    currency=goal_obj.currency,
                    language=lang,
                    show_item_rings=False,
                ),
            ]
            if items_col is not None:
                detail_controls.append(items_col)
            if insight_col.controls:
                detail_controls.append(card_surface(insight_col))
            detail_controls.extend(
                [
                    card_surface(ft.Column(proj_rows, spacing=6, tight=True)),
                ]
            )
            if budget_row is not None:
                detail_controls.append(card_surface(budget_row))
            if audit_col is not None:
                detail_controls.append(card_surface(audit_col))
            detail_controls.extend(
                [
                    ft.Row(wrap=True, spacing=8, controls=actions),
                    contrib_col,
                    load_more_btn,
                ]
            )

            body.controls = detail_controls
            safe_update(body)
            if goal_obj.status == GoalStatus.COMPLETED:
                self._offer_complete_archive(goal_obj, close_holder)

        close = open_fullscreen_form(
            self._page,
            title=goal.name,
            lang=lang,
            overlay_key="goal_detail",
            body=[body],
            on_save=None,
            show_save=False,
        )
        close_holder["close"] = close
        run_async(self._page, _load)

    def _offer_complete_archive(self, goal: Goal, close_holder: dict) -> None:
        lang = self._state.language

        async def _do() -> None:
            await self._archive(goal, close_holder)

        confirm_dialog(
            self._page,
            title=tr("goal.complete_archive_title", lang),
            message=tr("goal.complete_archive_message", lang, name=goal.name),
            confirm_text=tr("goal.archive", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=lambda: run_async(self._page, _do),
        )

    def _open_withdraw(self, goal: Goal, close_holder: dict) -> None:
        lang = self._state.language

        async def _open() -> None:
            try:
                accounts = await self._state.container.list_accounts.execute(
                    active_only=True
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            if not accounts:
                snack(self._page, tr("error.no_accounts", lang), error=True)
                return
            amount_tf = make_amount_field(
                lang,
                label=tr("field.amount", lang),
                autofocus=True,
            )
            account_dd = ft.Dropdown(
                label=tr("field.account", lang),
                value=accounts[0].id,
                options=[
                    ft.DropdownOption(
                        key=a.id,
                        text=f"{a.name} · {format_money(a.balance, a.currency)}",
                    )
                    for a in accounts
                ],
            )

            async def _save() -> None:
                try:
                    amount = parse_amount(amount_tf.value)
                    if amount <= 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    snack(self._page, tr("invalid_amount", lang), error=True)
                    return
                if amount > goal.current_amount:
                    snack(self._page, tr("error.insufficient_funds", lang), error=True)
                    return
                withdraw_uc = getattr(self._state.container, "withdraw_from_goal", None)
                if withdraw_uc is None:
                    snack(self._page, tr("error.generic", lang), error=True)
                    return
                try:
                    await withdraw_uc.execute(
                        goal.id,
                        amount,
                        account_id=account_dd.value or accounts[0].id,
                    )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=lang)
                    return
                close()
                self._state.bump_refresh(
                    "dashboard", "accounts", "transactions", "goals"
                )
                closer = close_holder.get("close")
                if callable(closer):
                    closer()
                await self.reload()
                refreshed = await self._state.container.goal_repository.get_by_id(
                    goal.id
                )
                if refreshed is not None:
                    self._open_detail(refreshed)
                snack(self._page, tr("action.saved", lang))

            close = open_fullscreen_form(
                self._page,
                title=f"{tr('goal.withdraw', lang)} · {goal.name}",
                lang=lang,
                overlay_key="goal_withdraw",
                body=[account_dd, amount_tf],
                on_save=_save,
                save_icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
            )

        run_async(self._page, _open)

    def _contribution_row(
        self,
        goal: Goal,
        tx: object,
        accounts: dict,
        close_holder: dict,
    ) -> ft.Control:
        lang = self._state.language
        from lib.domain.use_cases.goals import goal_credit_amount

        credit = goal_credit_amount(tx)  # type: ignore[arg-type]
        account = accounts.get(getattr(tx, "account_id", ""))
        account_name = account.name if account is not None else "—"
        account_ccy = account.currency if account is not None else getattr(tx, "currency", "")
        debit = quantize_money(getattr(tx, "amount", credit))
        debit_ccy = getattr(tx, "currency", None) or account_ccy or goal.currency
        comment = (getattr(tx, "comment", "") or "").strip()
        date_txt = format_date(getattr(tx, "date", None))
        subtitle = account_name
        if debit_ccy.upper() != (goal.currency or "").upper():
            subtitle = (
                f"{account_name} · −{format_money(debit, debit_ccy)} → "
                f"{format_money(credit, goal.currency)}"
            )
        else:
            subtitle = f"{account_name} · −{format_money(debit, debit_ccy)}"

        def _delete(_e: ft.ControlEvent | None = None) -> None:
            async def _do() -> None:
                try:
                    await self._state.container.delete_goal_contribution.execute(
                        getattr(tx, "id"),
                        goal_id=goal.id,
                    )
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=self._state.language)
                    return
                self._state.bump_refresh(
                    "dashboard", "accounts", "transactions", "goals"
                )
                closer = close_holder.get("close")
                if callable(closer):
                    closer()
                await self.reload()
                refreshed = await self._state.container.goal_repository.get_by_id(
                    goal.id
                )
                if refreshed is not None:
                    self._open_detail(refreshed)
                snack(self._page, tr("action.saved", lang))

            confirm_dialog(
                self._page,
                title=tr("action.confirm_delete", lang),
                message=format_money(credit, goal.currency),
                confirm_text=tr("action.delete", lang),
                cancel_text=tr("action.cancel", lang),
                on_confirm=_do,
            )

        return card_surface(
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                f"{date_txt} · {format_money(credit, goal.currency)}",
                                weight=ft.FontWeight.W_600,
                            ),
                            muted_text(subtitle),
                            muted_text(comment) if comment else ft.Container(height=0),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=ft.Colors.ERROR,
                        on_click=_delete,
                    ),
                ],
            )
        )

    def _close_item(self, goal_id: str, item_id: str, close_holder: dict) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                updated = await self._state.container.close_goal_item.execute(
                    goal_id, item_id
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh("dashboard", "goals")
            closer = close_holder.get("close")
            if callable(closer):
                closer()
            await self.reload()
            self._open_detail(updated)
            snack(self._page, tr("action.saved", lang))

        async def _confirm() -> None:
            goal = await self._state.container.goal_repository.get_by_id(goal_id)
            name = ""
            if goal is not None:
                for item in goal.items:
                    if item.id == item_id:
                        name = item.name
                        break
            confirm_dialog(
                self._page,
                title=tr("goal.close_item", lang),
                message=tr("goal.close_item_confirm", lang, name=name),
                confirm_text=tr("goal.close_item", lang),
                cancel_text=tr("action.cancel", lang),
                on_confirm=_do,
            )

        run_async(self._page, _confirm)

    async def _close_early(self, goal: Goal, close_holder: dict) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.close_goal_early.execute(goal.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            closer = close_holder.get("close")
            if callable(closer):
                closer()
            self._state.bump_refresh("dashboard", "goals")
            await self.reload()
            snack(self._page, tr("action.saved", lang))

        confirm_dialog(
            self._page,
            title=tr("goal.close_early", lang),
            message=tr("goal.close_early_confirm", lang, name=goal.name),
            confirm_text=tr("goal.close_early", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=lambda: run_async(self._page, _do),
        )

    async def _archive(self, goal: Goal, close_holder: dict) -> None:
        try:
            await self._state.container.archive_goal.execute(goal.id)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        closer = close_holder.get("close")
        if callable(closer):
            closer()
        self._state.bump_refresh("dashboard")
        await self.reload()
        snack(self._page, tr("action.saved", self._state.language))

    async def _duplicate(self, goal: Goal, close_holder: dict) -> None:
        lang = self._state.language
        try:
            await self._state.container.duplicate_goal.execute(
                goal.id,
                name_suffix=tr("goal.copy_suffix", lang),
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        closer = close_holder.get("close")
        if callable(closer):
            closer()
        self._state.bump_refresh("dashboard")
        await self.reload()
        snack(self._page, tr("action.saved", lang))

    def _open_editor(self, goal: Optional[Goal] = None) -> None:
        lang = self._state.language
        initial_icon = (goal.icon if goal else "flag") or "flag"
        if not is_valid_account_icon(initial_icon):
            initial_icon = "flag"
        selected_icon = {"value": initial_icon}
        selected_color = {
            "value": (goal.color if goal else ACCOUNT_COLORS[0]) or ACCOUNT_COLORS[0]
        }
        name_tf = ft.TextField(
            label=tr("field.name", lang), value=goal.name if goal else ""
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(name_tf, "name")
        target_tf = make_amount_field(
            lang,
            label=tr("goal.target", lang),
            value=goal.target_amount if goal else "",
        )
        planned_tf = make_amount_field(
            lang,
            label=tr("goal.planned_monthly", lang),
            value=goal.planned_monthly_contribution if goal and goal.planned_monthly_contribution else "",
        )
        monthly_hint = ft.Text(
            "",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        target_wrap = ft.Container(content=target_tf)
        wire_field_chain(self._page, [name_tf, target_tf, planned_tf])
        priority = {"value": str(goal.priority if goal else 3)}
        priority_chips = choice_chips(
            [(str(i), str(i)) for i in range(1, 6)],
            value=priority["value"],
            on_changed=lambda v: priority.__setitem__("value", v),
        )
        priority_block = ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Text(
                    tr("field.priority", lang),
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                priority_chips,
            ],
        )
        deadline_field = DateTimeField(
            self._page,
            lang=lang,
            label=tr("field.date", lang),
            value=goal.deadline if goal and goal.deadline else None,
            allow_clear=True,
            on_changed=lambda _dt: _refresh_monthly_hint(),
        )
        currency_picker = CurrencyTickerPicker(
            self._page,
            lang=lang,
            label=tr("goal.currency", lang),
            value=(goal.currency if goal else self._state.base_currency),
            include_crypto=True,
        )
        icon_preview = ft.Container(
            width=48,
            height=48,
            border_radius=24,
            alignment=ft.Alignment.CENTER,
            bgcolor=selected_color["value"],
            content=account_icon_control(
                selected_icon["value"],
                size=24,
                color=ICON_CATALOG_GLYPH,
            ),
        )
        color_preview = ft.Container(
            width=48,
            height=48,
            border_radius=24,
            bgcolor=selected_color["value"],
            border=ft.Border.all(2, ft.Colors.OUTLINE_VARIANT),
        )

        def _refresh_previews() -> None:
            icon_preview.content = account_icon_control(
                selected_icon["value"],
                size=24,
                color=ICON_CATALOG_GLYPH,
            )
            icon_preview.bgcolor = selected_color["value"]
            color_preview.bgcolor = selected_color["value"]
            try:
                safe_update(icon_preview)
                safe_update(color_preview)
            except Exception:  # noqa: BLE001
                pass

        def _select_icon(key: str) -> None:
            selected_icon["value"] = key
            _refresh_previews()

        def _select_color(color: str) -> None:
            selected_color["value"] = color
            _refresh_previews()

        def _open_icons(_e: ft.ControlEvent | None = None) -> None:
            open_icon_picker(
                self._page,
                lang=lang,
                groups=account_icon_groups(include_exchanges=False),
                selected=selected_icon["value"],
                on_select=_select_icon,
                render_icon=lambda key: account_icon_control(
                    key, size=22, color=ICON_CATALOG_GLYPH
                ),
                overlay_key="goal_icon_picker",
            )

        def _open_colors(_e: ft.ControlEvent | None = None) -> None:
            open_color_picker(
                self._page,
                lang=lang,
                colors=ACCOUNT_COLORS,
                selected=selected_color["value"],
                on_select=_select_color,
                overlay_key="goal_color_picker",
            )

        _refresh_previews()
        appearance_row = ft.Row(
            spacing=12,
            controls=[
                ft.GestureDetector(
                    content=icon_preview,
                    on_tap=_open_icons,
                ),
                ft.GestureDetector(
                    content=color_preview,
                    on_tap=_open_colors,
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(tr("picker.choose_icon", lang), size=13),
                        ft.Text(tr("picker.choose_color", lang), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ],
                ),
            ],
        )
        def _apply_template(template: GoalTemplate) -> None:
            name_tf.value = tr(template.name_key, lang)
            selected_icon["value"] = template.icon
            selected_color["value"] = template.color
            _refresh_previews()
            if template.items:
                from lib.domain.entities.goal import GoalItem

                items_editor.load_items(
                    [
                        GoalItem(
                            name=tr(item.name_key, lang),
                            target_amount=Decimal(item.default_amount),
                        )
                        for item in template.items
                    ]
                )
            else:
                items_editor.load_items([])
                if template.default_amount:
                    target_tf.value = format_amount_value(template.default_amount, lang)
            _sync_target_visibility()
            _refresh_monthly_hint()
            safe_update(name_tf)
            safe_update(target_tf)
            safe_update(items_editor)

        template_strip = h_scroll(
            [
                goal_template_chip(
                    tmpl,
                    lang=lang,
                    on_click=_apply_template,
                )
                for tmpl in GOAL_TEMPLATES
            ],
            spacing=10,
            height=52,
            padding=ft.Padding.only(bottom=4),
        )

        progress_bits: list[ft.Control] = []
        if goal:
            progress_bits.extend(
                [
                    ft.Text(
                        f"{tr('goal.progress', lang)}: "
                        f"{format_money(goal.current_amount, goal.currency)}",
                        size=13,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    form_hint(tr("goal.progress_hint", lang), size=11),
                    form_hint(tr("goal.currency_change_hint", lang), size=11),
                ]
            )

        def _sync_target_visibility() -> None:
            target_wrap.visible = not items_editor.enabled
            _refresh_monthly_hint()
            try:
                safe_update(target_wrap)
            except Exception:  # noqa: BLE001
                pass

        def _refresh_monthly_hint(_e: ft.ControlEvent | None = None) -> None:
            ccy = currency_picker.value or self._state.base_currency
            try:
                if items_editor.enabled:
                    items = items_editor.build_items()
                    target = sum(i.target_amount for i in items) if items else Decimal("0")
                else:
                    target = parse_amount(target_tf.value)
            except (InvalidOperation, ValueError):
                target = Decimal("0")
            current = goal.current_amount if goal else Decimal("0")
            remaining = quantize_money(max(Decimal("0"), target - current))
            parts: list[str] = []
            req = required_monthly_for_goal(remaining, deadline_field.value)
            if req is not None and req > 0:
                parts.append(
                    tr(
                        "goal.monthly_hint_required",
                        lang,
                        amount=format_money(req, ccy),
                    )
                )
            try:
                planned = parse_amount(planned_tf.value)
            except (InvalidOperation, ValueError):
                planned = Decimal("0")
            if planned > 0:
                projected = projected_date_from_planned(remaining, planned)
                if projected is not None:
                    parts.append(
                        tr(
                            "goal.projected_from_plan",
                            lang,
                            date=format_date(projected),
                        )
                    )
            monthly_hint.value = " · ".join(parts)
            try:
                safe_update(monthly_hint)
            except Exception:  # noqa: BLE001
                pass

        items_editor = GoalItemsEditor(lang, on_changed=_sync_target_visibility)
        if goal and goal.items:
            items_editor.load_items(goal.items)
        _sync_target_visibility()
        attach_grouped_digits(
            target_tf, lang, extra_on_change=_refresh_monthly_hint
        )
        attach_grouped_digits(
            planned_tf, lang, extra_on_change=_refresh_monthly_hint
        )
        editor_controls: list[ft.Control] = []
        if not goal:
            editor_controls.append(
                form_section(
                    tr("goal.templates", lang),
                    [template_strip],
                    hint=tr("goal.templates_hint", lang),
                    icon=ft.Icons.APPS,
                )
            )
        editor_controls.extend(
            [
                form_section(
                    tr("form.section.main", lang),
                    [
                        appearance_row,
                        name_tf,
                        target_wrap,
                        items_editor,
                        currency_picker,
                        planned_tf,
                        monthly_hint,
                        *progress_bits,
                    ],
                    hint=tr("goal.form_main_hint", lang) if not goal else None,
                    icon=ft.Icons.FLAG,
                ),
                form_section(
                    tr("form.section.options", lang),
                    [priority_block, deadline_field],
                    icon=ft.Icons.TUNE,
                ),
            ]
        )

        async def _save() -> None:
            validation_errors = items_editor.validate()
            if validation_errors:
                snack(self._page, validation_errors[0], error=True)
                return
            items = items_editor.build_items()
            try:
                if items:
                    target = sum(i.target_amount for i in items)
                else:
                    target = parse_amount(target_tf.value)
                if target <= 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                snack(self._page, tr("invalid_amount", lang), error=True)
                return
            deadline = deadline_field.value
            planned_monthly: Decimal | None = None
            try:
                planned_raw = parse_amount(planned_tf.value)
                if planned_raw > 0:
                    planned_monthly = planned_raw
            except (InvalidOperation, ValueError):
                planned_monthly = None
            goal_name = (name_tf.value or "").strip() or "Goal"
            entity = Goal(
                id=goal.id if goal else Goal(name="tmp", target_amount=1).id,
                name=goal_name,
                target_amount=target,
                current_amount=goal.current_amount if goal else Decimal("0"),
                currency=currency_picker.value or self._state.base_currency,
                deadline=deadline,
                priority=int(priority["value"] or 3),
                category_link=goal_name,
                status=goal.status if goal else GoalStatus.ACTIVE,
                is_completed=goal.is_completed if goal else False,
                closed_early=goal.closed_early if goal else False,
                items=items,
                icon=selected_icon["value"],
                color=selected_color["value"],
                planned_monthly_contribution=planned_monthly,
                created_at=goal.created_at if goal else datetime.now(timezone.utc),
            )
            try:
                if goal:
                    saved = await self._state.container.update_goal.execute(entity)
                else:
                    saved = await self._state.container.create_goal.execute(entity)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                return
            append_audit = getattr(self._state.container, "append_goal_audit", None)
            if append_audit is not None:
                try:
                    await append_audit.execute(
                        saved.id,
                        "updated" if goal else "created",
                    )
                except Exception:  # noqa: BLE001
                    pass
            close()
            self._state.bump_refresh("dashboard")
            await self.reload()
            snack(self._page, tr("action.saved", lang))

        def _delete(_e: ft.ControlEvent | None = None) -> None:
            if not goal:
                return

            async def _do() -> None:
                try:
                    await self._state.container.delete_goal.execute(goal.id)
                except Exception as exc:  # noqa: BLE001
                    snack_exception(self._page, exc, lang=self._state.language)
                    return
                close()
                self._state.bump_refresh("dashboard")
                await self.reload()

            confirm_dialog(
                self._page,
                title=tr("action.confirm_delete", lang),
                message=tr("goal.delete_keep_txs", lang, name=goal.name),
                confirm_text=tr("action.delete", lang),
                cancel_text=tr("action.cancel", lang),
                on_confirm=_do,
            )

        if goal:
            editor_controls.append(
                ft.OutlinedButton(
                    tr("action.delete", lang),
                    icon=ft.Icons.DELETE_OUTLINE,
                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                    on_click=_delete,
                )
            )

        close = open_fullscreen_form(
            self._page,
            title=tr("action.edit", lang) if goal else tr("action.add", lang),
            lang=lang,
            overlay_key="goal_editor",
            wrap_body=False,
            body=editor_controls,
            on_save=_save,
        )
