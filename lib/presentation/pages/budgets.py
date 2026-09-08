"""Monthly category budgets page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.budget import Budget, BudgetProgress
from lib.domain.entities.category import CategoryKind
from lib.domain.entities.transaction import TransactionType
from lib.domain.use_cases.budget_insights import (
    bucket_spend_by_month,
    budget_pace,
    shift_month,
)
from lib.domain.use_cases.budgets import month_bounds
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.budgets_templates import (
    BUDGET_TEMPLATES,
    BudgetTemplate,
    budget_template_chip,
)
from lib.presentation.layout import h_scroll, make_v_scroll
from lib.presentation.components.layout.grid import card_grid
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.ui_motion import replace_controls
from lib.presentation.money_input import make_amount_field, parse_amount
from lib.presentation.notification_badges import (
    BUDGET_ALERT_KINDS,
    mark_related_read,
    pending_related_ids,
)
from lib.presentation.styles import choice_chips, form_section, muted_text
from lib.presentation.utils import (
    format_date,
    format_money_compact,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    snack_exception,
    tr,
)
from lib.presentation.widgets.budget_sparkline import budget_spend_sparkline
from lib.presentation.widgets.budget_summary_ring import (
    budget_list_card,
    budgets_summary_ring,
)
from lib.presentation.widgets.budget_swipe_card import swipe_budget_card
from lib.presentation.widgets.category_picker import CategoryPicker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form
from lib.presentation.widgets.loading import fill_loading

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_TX_PAGE = 20
_FILTERS = ("all", "warning", "over")


class BudgetsPage(ft.Column):
    """Manage monthly spending limits per category."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        now = datetime.now(timezone.utc)
        self._month = now.month
        self._year = now.year
        self._list = make_v_scroll(spacing=12)
        self._token = -1
        self._categories_by_name: dict[str, object] = {}
        self._filter = "all"
        self._search_query = ""
        self._search_gen = 0
        self._alert_ids: set[str] = set()
        self._search_tf = ft.TextField(
            hint_text=tr("budgets.search_hint", state.language),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            filled=True,
            expand=True,
            on_change=self._on_search_change,
        )
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("budgets.title", state.language),
                    body=self._list,
                    page=page,
                    extra=[self._search_tf],
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _e: state.close_secondary(),
                    ),
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.CONTENT_COPY,
                            tooltip=tr("budgets.copy_previous", state.language),
                            on_click=lambda _e: run_async(
                                self._page, self._copy_previous
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            tooltip=tr("budgets.add", state.language),
                            on_click=lambda _e: self._open_editor(),
                        ),
                    ],
                ),
                page=page,
            )
        )
        state.subscribe(self._on_state)
        self._reload_gate = ReloadGate(page, self, self.reload)
        self._reload_gate.request()

    def did_mount(self) -> None:
        super().did_mount()
        self._reload_gate.on_mounted()

    def _on_state(self, state: "AppState") -> None:
        if state.budgets_token != self._token:
            self._reload_gate.request()

    def _on_search_change(self, e: ft.ControlEvent) -> None:
        self._search_query = str(getattr(e.control, "value", "") or "")
        run_async(self._page, self._debounced_search)

    async def _debounced_search(self) -> None:
        """Wait briefly so typing does not reload on every keystroke."""
        self._search_gen += 1
        gen = self._search_gen
        await asyncio.sleep(0.35)
        if gen != self._search_gen:
            return
        self._reload_gate.request()

    def _is_current_month(self) -> bool:
        now = datetime.now(timezone.utc)
        return self._month == now.month and self._year == now.year

    def _period_label(self, lang: str) -> str:
        return f"{tr(f'budgets.month.{self._month}', lang)} {self._year}"

    def _shift_month(self, delta: int) -> None:
        self._year, self._month = shift_month(self._year, self._month, delta)
        self._reload_gate.request()

    def _go_this_month(self) -> None:
        now = datetime.now(timezone.utc)
        self._month, self._year = now.month, now.year
        self._reload_gate.request()

    async def _copy_previous(self) -> None:
        uc = getattr(self._state.container, "copy_budgets_from_previous", None)
        if uc is None:
            return
        lang = self._state.language
        try:
            count = await uc.execute(self._month, self._year)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        self._state.bump_refresh("dashboard", "budgets", "analytics")
        snack(self._page, tr("budgets.copied", lang, count=str(count)))

    def _month_bar(self, lang: str) -> ft.Control:
        row = ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_LEFT,
                    on_click=lambda _e: self._shift_month(-1),
                ),
                ft.Text(
                    self._period_label(lang),
                    weight=ft.FontWeight.W_700,
                    size=15,
                    expand=True,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_RIGHT,
                    on_click=lambda _e: self._shift_month(1),
                ),
            ],
        )
        if self._is_current_month():
            return row
        return ft.Column(
            spacing=0,
            tight=True,
            controls=[
                row,
                ft.TextButton(
                    tr("budgets.this_month", lang),
                    on_click=lambda _e: self._go_this_month(),
                ),
            ],
        )

    async def reload(self) -> None:
        self._token = self._state.budgets_token
        lang = self._state.language
        fill_loading(self._list)
        safe_update(self._list)
        self._alert_ids = pending_related_ids(
            self._state.container,
            self._state.settings,
            BUDGET_ALERT_KINDS,
        )
        try:
            items = await self._state.container.get_budgets_for_month.execute(
                self._month, self._year
            )
            categories = await self._state.container.list_categories.execute(
                active_only=False
            )
            self._categories_by_name = {c.name: c for c in categories}
            # Keep spent accurate when opening the page (home no longer full-scans).
            recalc = getattr(self._state.container, "recalculate_budget_spent", None)
            if recalc is not None:
                try:
                    await recalc.execute(month=self._month, year=self._year)
                    items = await self._state.container.get_budgets_for_month.execute(
                        self._month, self._year
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            replace_controls(
                self._list, [EmptyState(tr("error.generic", lang))], self._page
            )
            return

        currency = self._state.base_currency
        total_limit = sum((item.limit for item in items), Decimal("0"))
        total_spent = sum((item.spent for item in items), Decimal("0"))
        remaining = total_limit - total_spent
        over_count = sum(1 for item in items if item.is_over_budget)
        warning_count = sum(
            1 for item in items if (not item.is_over_budget) and item.percent >= 80
        )
        now = datetime.now(timezone.utc)
        lookback_y, lookback_m = shift_month(self._year, self._month, -5)
        date_from = month_bounds(lookback_y, lookback_m)[0]
        date_to = month_bounds(self._year, self._month)[1]
        try:
            from lib.presentation.tx_query import fetch_transactions_paged

            recent_txs = await fetch_transactions_paged(
                self._state.container.list_transactions,
                transaction_type=TransactionType.EXPENSE,
                date_from=date_from,
                date_to=date_to,
            )
            book = await load_rate_book(self._state.container)
        except Exception:  # noqa: BLE001
            recent_txs = []
            book = None

        visible = self._apply_filters(items, lang)
        chips = choice_chips(
            [(key, tr(f"budgets.filter.{key}", lang)) for key in _FILTERS],
            value=self._filter,
            on_changed=self._on_filter,
        )
        controls: list[ft.Control] = [self._month_bar(lang), chips]
        if items:
            controls.append(
                budgets_summary_ring(
                    spent=total_spent,
                    limit=total_limit,
                    remaining=remaining,
                    currency=currency,
                    language=lang,
                    over_count=over_count,
                    warning_count=warning_count,
                    count=len(items),
                    page=self._page,
                )
            )
        if not items:
            controls.append(
                EmptyState(
                    tr("budgets.no_budgets", lang),
                    icon=ft.Icons.PIE_CHART,
                    action_label=tr("budgets.add", lang),
                    on_action=lambda _e: self._open_editor(),
                )
            )
        elif not visible:
            controls.append(EmptyState(tr("budgets.empty_filtered", lang)))
        else:
            packed: list[ft.Control] = []
            for progress in visible:
                cat = self._categories_by_name.get(progress.category_id)
                icon = getattr(cat, "icon", None) or "category"
                color = getattr(cat, "color", None) or "#546E7A"
                buckets = bucket_spend_by_month(
                    recent_txs,
                    category=progress.category_id,
                    months=6,
                    now=datetime(self._year, self._month, 15, tzinfo=timezone.utc),
                    rate_book=book,
                    to_currency=currency,
                )
                spark = None
                if any(v > 0 for _, v in buckets):
                    spark = budget_spend_sparkline(buckets, color=color)
                pace = budget_pace(
                    spent=progress.spent,
                    limit=progress.limit,
                    month=self._month,
                    year=self._year,
                    now=now,
                )
                card = budget_list_card(
                    progress,
                    language=lang,
                    currency=currency,
                    category_icon=icon,
                    category_color=color,
                    category_name=localize_category_name(
                        progress.category_id, lang
                    ),
                    pace=pace,
                    sparkline=spark,
                    alert=progress.budget.id in self._alert_ids,
                    on_open=self._open_detail,
                    page=self._page,
                )
                packed.append(
                    swipe_budget_card(
                        card,
                        language=lang,
                        on_edit=lambda p=progress: self._open_editor(p.budget),
                        on_delete=lambda p=progress: self._confirm_delete(p.budget),
                        page=self._page,
                    )
                )
            controls.extend(
                card_grid(packed, self._page, min_card=300, maximum=2)
            )
        replace_controls(self._list, controls, self._page)

    def _on_filter(self, value: str) -> None:
        self._filter = value or "all"
        self._reload_gate.request()

    def _apply_filters(
        self, items: list[BudgetProgress], lang: str
    ) -> list[BudgetProgress]:
        q = self._search_query.strip().casefold()
        out: list[BudgetProgress] = []
        for item in items:
            if self._filter == "over" and not item.is_over_budget:
                continue
            if self._filter == "warning" and (
                item.is_over_budget or item.percent < 80
            ):
                continue
            if q:
                name = localize_category_name(item.category_id, lang).casefold()
                raw = (item.category_id or "").casefold()
                if q not in name and q not in raw:
                    continue
            out.append(item)
        return out

    def _open_detail(self, progress: BudgetProgress) -> None:
        run_async(self._page, self._open_detail_async, progress)

    async def _open_detail_async(self, progress: BudgetProgress) -> None:
        lang = self._state.language
        currency = self._state.base_currency
        mark_related_read(
            self._state.container, progress.budget.id, BUDGET_ALERT_KINDS
        )
        self._alert_ids.discard(progress.budget.id)
        date_from, date_to = month_bounds(self._year, self._month)
        try:
            txs = await self._state.container.list_transactions.execute(
                category=progress.category_id,
                transaction_type=TransactionType.EXPENSE,
                date_from=date_from,
                date_to=date_to,
                limit=_TX_PAGE + 1,
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        has_more = len(txs) > _TX_PAGE
        shown = txs[:_TX_PAGE]
        offset = {"n": len(shown)}
        pace = budget_pace(
            spent=progress.spent,
            limit=progress.limit,
            month=self._month,
            year=self._year,
        )
        daily = format_money_compact(pace.daily_allowance, currency)
        if progress.is_over_budget:
            pace_txt = tr("budgets.pace_over", lang)
        elif pace.on_track:
            pace_txt = tr("budgets.pace_ok", lang, daily=daily)
        else:
            pace_txt = tr("budgets.pace_fast", lang, daily=daily)
        rows = ft.Column(spacing=6, tight=True)
        if not shown:
            rows.controls.append(muted_text("—"))
        else:
            for tx in shown:
                rows.controls.append(
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            muted_text(format_date(tx.date)),
                            ft.Text(
                                format_money_compact(tx.amount, tx.currency),
                                size=13,
                                weight=ft.FontWeight.W_700,
                            ),
                        ],
                    )
                )

        async def _more(_e: ft.ControlEvent | None = None) -> None:
            more = await self._state.container.list_transactions.execute(
                category=progress.category_id,
                transaction_type=TransactionType.EXPENSE,
                date_from=date_from,
                date_to=date_to,
                limit=_TX_PAGE + 1,
                offset=offset["n"],
            )
            chunk = more[:_TX_PAGE]
            offset["n"] += len(chunk)
            for tx in chunk:
                rows.controls.append(
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            muted_text(format_date(tx.date)),
                            ft.Text(
                                format_money_compact(tx.amount, tx.currency),
                                size=13,
                                weight=ft.FontWeight.W_700,
                            ),
                        ],
                    )
                )
            load_more.visible = len(more) > _TX_PAGE
            safe_update(rows)
            safe_update(load_more)

        load_more = ft.TextButton(
            tr("action.load_more", lang),
            visible=has_more,
            on_click=lambda e: run_async(self._page, _more, e),
        )
        leftover = progress.remaining
        leftover_label = (
            tr("budgets.overspend", lang)
            if progress.is_over_budget
            else tr("budgets.remaining", lang)
        )

        async def _edit_from_detail() -> None:
            closer()
            self._open_editor(progress.budget)

        closer = open_fullscreen_form(
            self._page,
            title=localize_category_name(progress.category_id, lang),
            lang=lang,
            overlay_key="budget_detail",
            wrap_body=False,
            save_label=tr("budgets.edit", lang),
            save_icon=ft.Icons.EDIT_OUTLINED,
            on_save=_edit_from_detail,
            body=[
                form_section(
                    tr("budgets.limit", lang),
                    [
                        ft.Text(
                            f"{format_money_compact(progress.spent, currency)} / "
                            f"{format_money_compact(progress.limit, currency)}",
                            weight=ft.FontWeight.W_700,
                            size=18,
                        ),
                        muted_text(
                            f"{leftover_label}: "
                            f"{format_money_compact(leftover, currency, signed=progress.is_over_budget)}"
                        ),
                        muted_text(pace_txt),
                    ],
                    icon=ft.Icons.PIE_CHART,
                ),
                form_section(
                    tr("budgets.operations", lang),
                    [rows, load_more],
                    icon=ft.Icons.RECEIPT_LONG,
                ),
            ],
        )

    def _confirm_delete(self, budget: Budget) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.delete_budget.execute(budget.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh("dashboard", "budgets", "analytics")
            snack(self._page, tr("budgets.deleted", lang))

        confirm_dialog(
            self._page,
            title=tr("budgets.delete", lang),
            message=tr("budgets.delete_confirm", lang, category=budget.category_id),
            confirm_text=tr("budgets.delete", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=_do,
        )

    def _open_editor(self, budget: Optional[Budget] = None) -> None:
        run_async(self._page, self._open_editor_async, budget)

    async def _open_editor_async(self, budget: Optional[Budget] = None) -> None:
        lang = self._state.language
        suggest_holder = {"amount": Decimal("0")}
        hint = muted_text("")
        picker = CategoryPicker(
            self._page,
            self._state,
            tx_type=TransactionType.EXPENSE.value,
            initial_name=budget.category_id if budget else None,
            on_changed=lambda: run_async(self._page, _refresh_suggest),
        )
        run_async(self._page, picker.reload)
        limit_tf = make_amount_field(
            lang,
            label=tr("budgets.limit", lang),
            value=budget.amount_limit if budget else "",
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
        )

        async def _refresh_suggest() -> None:
            uc = getattr(self._state.container, "suggest_budget_limit", None)
            name = picker.selected_name
            if uc is None or not name:
                hint.value = ""
                safe_update(hint)
                return
            try:
                avg = await uc.execute(name, self._month, self._year)
            except Exception:  # noqa: BLE001
                avg = Decimal("0")
            suggest_holder["amount"] = avg
            if avg > 0:
                hint.value = tr(
                    "budgets.suggest_avg",
                    lang,
                    amount=format_money_compact(avg, self._state.base_currency),
                )
            else:
                hint.value = ""
            safe_update(hint)

        def _use_suggest(_e: ft.ControlEvent | None = None) -> None:
            avg = suggest_holder["amount"]
            if avg <= 0:
                return
            limit_tf.value = str(avg)
            safe_update(limit_tf)

        async def _apply_template(template: BudgetTemplate) -> None:
            finder = getattr(self._state.container, "find_or_create_category", None)
            if finder is not None:
                try:
                    await finder.execute(
                        template.category,
                        kind=CategoryKind.EXPENSE,
                        icon=template.icon,
                        color=template.color,
                    )
                    await picker.reload()
                except Exception:  # noqa: BLE001
                    pass
            picker.select_name(template.category)
            if not (limit_tf.value or "").strip():
                limit_tf.value = template.default_amount
                safe_update(limit_tf)
            await _refresh_suggest()

        async def _apply_sub_hint(
            name: str,
            monthly: Decimal,
            icon: str = "autorenew",
            color: str = "#A78BFA",
        ) -> None:
            finder = getattr(self._state.container, "find_or_create_category", None)
            if finder is not None:
                try:
                    await finder.execute(
                        name,
                        kind=CategoryKind.EXPENSE,
                        icon=icon,
                        color=color,
                    )
                    await picker.reload()
                except Exception:  # noqa: BLE001
                    pass
            picker.select_name(name)
            limit_tf.value = str(monthly)
            safe_update(limit_tf)
            await _refresh_suggest()

        template_strip = h_scroll(
            [
                budget_template_chip(
                    t,
                    language=lang,
                    on_click=lambda tmpl=t: run_async(
                        self._page, _apply_template, tmpl
                    ),
                )
                for t in BUDGET_TEMPLATES
            ],
            spacing=10,
            height=52,
            padding=ft.Padding.only(bottom=4),
        )
        sub_controls: list[ft.Control] = []
        suggest_subs = getattr(
            self._state.container, "suggest_subscription_budgets", None
        )
        if suggest_subs is not None and budget is None:
            try:
                hints = await suggest_subs.execute(self._month, self._year)
            except Exception:  # noqa: BLE001
                hints = []
            pending = [h for h in hints if not h.has_budget]
            if pending:
                sub_controls.append(muted_text(tr("budgets.from_subs", lang)))
                sub_controls.append(
                    h_scroll(
                        [
                            ft.Container(
                                padding=ft.Padding.symmetric(
                                    horizontal=12, vertical=8
                                ),
                                border_radius=12,
                                bgcolor=ft.Colors.SURFACE_CONTAINER,
                                ink=True,
                                on_click=lambda _e, h=item: run_async(
                                    self._page,
                                    _apply_sub_hint,
                                    h.name,
                                    h.monthly,
                                    h.icon,
                                    h.color,
                                ),
                                content=ft.Row(
                                    spacing=8,
                                    tight=True,
                                    controls=[
                                        account_icon_badge(
                                            item.icon,
                                            color=item.color,
                                            size=28,
                                            glyph_size=14,
                                            glyph_color="#FFFFFF",
                                        ),
                                        ft.Text(
                                            item.name,
                                            size=12,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                        muted_text(
                                            format_money_compact(
                                                item.monthly,
                                                self._state.base_currency,
                                            )
                                        ),
                                    ],
                                ),
                            )
                            for item in pending[:8]
                        ],
                        spacing=10,
                        height=48,
                    )
                )

        async def _save() -> None:
            name = picker.selected_name
            if not name:
                snack(self._page, tr("budgets.category_required", lang), error=True)
                return
            try:
                limit = parse_amount(limit_tf.value)
            except (InvalidOperation, ValueError):
                snack(self._page, tr("budgets.limit_required", lang), error=True)
                return
            try:
                await self._state.container.set_budget.execute(
                    name, self._month, self._year, limit
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            close()
            self._state.bump_refresh("dashboard", "budgets", "analytics")
            snack(self._page, tr("budgets.saved", lang))

        close = open_fullscreen_form(
            self._page,
            title=tr("budgets.edit" if budget else "budgets.add", lang),
            lang=lang,
            overlay_key="budget_form",
            wrap_body=False,
            body=[
                template_strip,
                *sub_controls,
                form_section(
                    tr("form.section.category", lang),
                    [
                        picker,
                        limit_tf,
                        hint,
                        ft.TextButton(
                            tr("budgets.use_suggest", lang),
                            on_click=_use_suggest,
                        ),
                    ],
                    icon=ft.Icons.PIE_CHART,
                ),
            ],
            on_save=_save,
        )
        if picker.selected_name:
            run_async(self._page, _refresh_suggest)
