"""Goal progress bar widget."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

import flet as ft

from lib.domain.entities.goal import Goal, GoalItem, GoalStatus
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.components.layout.text import adaptive_text
from lib.presentation.layout import h_scroll
from lib.presentation.responsive import entity_card_metrics, ring_label_font, tile_ring_metrics
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import card_surface, muted_text
from lib.presentation.utils import format_date, format_money_compact, tr


def circular_progress_badge(
    ratio: float,
    label: str,
    *,
    size: int = 56,
    color: str | None = None,
    track_color: str | None = None,
    page: ft.Page | None = None,
) -> ft.Control:
    """Determinate ring with centered label (percent or checkmark)."""
    _ = page
    clamped = max(0.0, min(float(ratio), 1.0))
    skin = get_active_skin()
    ring_color = color or skin.primary_hex(dark=True)
    track = track_color or ft.Colors.SURFACE_CONTAINER_HIGHEST
    font_size = ring_label_font(size, label)
    from lib.presentation.count_up import mark_progress
    from lib.presentation.ui_motion import is_ui_animating

    animate = is_ui_animating()
    ring = ft.ProgressRing(
        value=0.0 if animate else clamped,
        width=size,
        height=size,
        stroke_width=max(4, size // 10),
        color=ring_color,
        bgcolor=track,
    )
    if animate:
        mark_progress(ring, clamped)
    return ft.Container(
        width=size,
        height=size,
        content=ft.Stack(
            controls=[
                ring,
                ft.Container(
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        label,
                        size=font_size,
                        weight=ft.FontWeight.W_800,
                        text_align=ft.TextAlign.CENTER,
                        max_lines=1,
                    ),
                ),
            ],
        ),
    )


def goal_item_ring_tile(
    item: GoalItem,
    *,
    currency: str,
    language: str,
    size: int | None = None,
    on_tap: Optional[Callable[[], None]] = None,
    page: ft.Page | None = None,
) -> ft.Control:
    """Compact ring + name for goal list cards."""
    metrics = entity_card_metrics(page)
    ring_size = size if size is not None else metrics["ring"]
    ratio = float(item.progress_ratio)
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100))
    closed = item.is_closed
    label = "✓" if closed else f"{pct}%"
    ring_color = (
        ft.Colors.OUTLINE
        if closed
        else get_active_skin().primary_hex(dark=True)
    )
    # Single-line ellipsis — avoids mid-word wraps like «Футболк» / «-».
    name = (item.name or "").strip()
    tile = ft.Container(
        width=metrics["ring_tile"],
        padding=ft.Padding.only(top=4, right=2),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            tight=True,
            controls=[
                circular_progress_badge(
                    ratio,
                    label,
                    size=ring_size,
                    color=ring_color,
                    page=page,
                ),
                ft.Text(
                    name,
                    size=max(9, metrics["meta"] - 2),
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    no_wrap=True,
                    tooltip=name if len(name) > 10 else None,
                ),
            ],
        ),
    )
    if on_tap is not None and not closed:
        return ft.Container(
            content=tile,
            ink=True,
            border_radius=10,
            tooltip=tr("goal.contribute", language),
            on_click=lambda _e: on_tap(),
        )
    return tile


def goal_item_progress_card(
    item: GoalItem,
    *,
    currency: str,
    language: str,
    on_close: Optional[Callable[[], None]] = None,
    on_contribute: Optional[Callable[[], None]] = None,
    page: ft.Page | None = None,
) -> ft.Control:
    """Detail row: circular progress, amounts, optional close action."""
    tile = tile_ring_metrics(page)
    ratio = float(item.progress_ratio)
    clamped = max(0.0, min(ratio, 1.0))
    pct = int(round(clamped * 100))
    closed = item.is_closed
    status_txt = (
        tr("goal.item_closed", language)
        if closed
        else tr("goal.item_open", language)
    )
    label = "✓" if closed else f"{pct}%"
    ring_color = (
        ft.Colors.OUTLINE
        if closed
        else get_active_skin().primary_hex(dark=True)
    )
    trailing: list[ft.Control] = []
    if on_close is not None and not closed:
        trailing.append(
            ft.IconButton(
                icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                icon_size=20,
                tooltip=tr("goal.close_item", language),
                icon_color=get_active_skin().primary_hex(dark=True),
                style=ft.ButtonStyle(padding=6),
                on_click=lambda _e: on_close(),
            )
        )
    can_contribute = on_contribute is not None and not closed
    name = (item.name or "").strip()
    return card_surface(
        ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                circular_progress_badge(
                    ratio,
                    label,
                    size=tile["ring"],
                    color=ring_color,
                    page=page,
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            name,
                            weight=ft.FontWeight.W_700,
                            size=tile["title"],
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
                        ),
                        ft.Text(
                            tr(
                                "goal.item_progress",
                                language,
                                saved=format_money_compact(
                                    item.current_amount, currency
                                ),
                                target=format_money_compact(
                                    item.target_amount, currency
                                ),
                            ),
                            size=tile["meta"],
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
                        ),
                        muted_text(status_txt, size=10, page=page),
                    ],
                ),
                *trailing,
            ],
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        ink=can_contribute,
        on_click=lambda _e: on_contribute() if can_contribute else None,
        animate=False,
    )


class GoalProgress(ft.Container):
    """Shows goal name, amounts, and a progress bar."""

    def __init__(
        self,
        goal: Goal,
        *,
        currency: str = "RUB",
        language: str = "ru",
        alert: bool = False,
        required_monthly: Optional[Decimal] = None,
        required_pace_amount: Optional[Decimal] = None,
        required_pace_unit: Optional[str] = None,
        is_on_track: Optional[bool] = None,
        on_click: Optional[Callable[[Goal], None]] = None,
        on_contribute: Optional[Callable[[Goal], None]] = None,
        on_item_contribute: Optional[Callable[[GoalItem], None]] = None,
        on_alert: Optional[Callable[[Goal], None]] = None,
        show_item_rings: bool = True,
        page: ft.Page | None = None,
    ) -> None:
        metrics = entity_card_metrics(page)
        ratio = float(goal.progress_ratio)
        ratio = max(0.0, min(ratio, 1.0))
        pct = int(round(ratio * 100))
        deadline = (
            tr("goal.deadline_by", language, date=format_date(goal.deadline))
            if goal.deadline
            else tr("goal.no_deadline", language)
        )
        status = (
            goal.status
            if isinstance(goal.status, GoalStatus)
            else GoalStatus(goal.status)
        )
        badge_key = f"goal.badge.{status.value}"
        status_label = tr(badge_key, language, default=status.value)
        status_bg = {
            GoalStatus.ACTIVE: ft.Colors.PRIMARY_CONTAINER,
            GoalStatus.COMPLETED: ft.Colors.SECONDARY_CONTAINER,
            GoalStatus.ARCHIVED: ft.Colors.SURFACE_CONTAINER_HIGHEST,
        }.get(status, ft.Colors.PRIMARY_CONTAINER)
        status_fg = {
            GoalStatus.ACTIVE: ft.Colors.ON_PRIMARY_CONTAINER,
            GoalStatus.COMPLETED: ft.Colors.ON_SECONDARY_CONTAINER,
            GoalStatus.ARCHIVED: ft.Colors.ON_SURFACE_VARIANT,
        }.get(status, ft.Colors.ON_PRIMARY_CONTAINER)

        def _chip(text: str, *, bgcolor: str, color: str) -> ft.Container:
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                border_radius=999,
                bgcolor=bgcolor,
                content=ft.Text(
                    text,
                    size=metrics["chip"],
                    weight=ft.FontWeight.W_700,
                    color=color,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1,
                ),
            )

        chips: list[ft.Control] = [
            _chip(status_label, bgcolor=status_bg, color=status_fg),
            _chip(
                f"P{goal.priority}",
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                color=ft.Colors.ON_SURFACE,
            ),
        ]
        if getattr(goal, "closed_early", False):
            chips.append(
                _chip(
                    tr("goal.badge.closed_early", language),
                    bgcolor=ft.Colors.ERROR_CONTAINER,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                )
            )
        if goal.items:
            open_count = sum(1 for i in goal.items if not i.is_closed)
            chips.append(
                _chip(
                    f"{len(goal.items) - open_count}/{len(goal.items)}",
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    color=ft.Colors.ON_SURFACE,
                )
            )
        if is_on_track is True:
            chips.append(
                _chip(
                    tr("goal.on_track", language),
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                    color=ft.Colors.ON_PRIMARY_CONTAINER,
                )
            )
        elif is_on_track is False:
            chips.append(
                _chip(
                    tr("goal.off_track", language),
                    bgcolor=ft.Colors.ERROR_CONTAINER,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                )
            )

        can_contribute = on_contribute is not None and status == GoalStatus.ACTIVE
        alert_handler = on_alert or on_click
        show_alert_btn = alert and is_on_track is not False
        if show_alert_btn:
            action_btn = ft.IconButton(
                icon=ft.Icons.PRIORITY_HIGH,
                icon_size=20,
                icon_color=ft.Colors.ERROR,
                tooltip=tr("notify.goal_off_track_title", language),
                on_click=lambda _e: alert_handler(goal) if alert_handler else None,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    padding=10,
                    bgcolor=ft.Colors.ERROR_CONTAINER,
                ),
            )
        elif can_contribute:
            action_btn = ft.IconButton(
                icon=ft.Icons.ADD,
                icon_size=20,
                icon_color=get_active_skin().on_primary_hex(dark=True),
                bgcolor=get_active_skin().primary_hex(dark=True),
                tooltip=tr("goal.contribute", language),
                on_click=lambda _e: on_contribute(goal) if on_contribute else None,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    padding=10,
                ),
            )
        else:
            action_btn = ft.Container(width=0, height=0)

        footer_bits = [deadline]
        pace_amount = required_pace_amount
        pace_unit = required_pace_unit
        if pace_amount is None and required_monthly is not None:
            pace_amount = required_monthly
            pace_unit = "month"
        if pace_amount is not None and status == GoalStatus.ACTIVE:
            unit_key = {
                "day": "goal.required_daily_short",
                "week": "goal.required_weekly_short",
                "total": "goal.required_now_short",
            }.get(pace_unit or "month", "goal.required_monthly_short")
            footer_bits.append(
                tr(
                    unit_key,
                    language,
                    amount=format_money_compact(pace_amount, currency),
                )
            )

        item_rings: list[ft.Control] = []
        if goal.items:
            sorted_items = sorted(goal.items, key=lambda i: i.sort_order)
            item_rings = [
                goal_item_ring_tile(
                    item,
                    currency=currency,
                    language=language,
                    page=page,
                    on_tap=(
                        (lambda it=item: on_item_contribute(it))
                        if on_item_contribute is not None and not item.is_closed
                        else None
                    ),
                )
                for item in sorted_items
            ]

        body_controls: list[ft.Control] = [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        spacing=6,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Row(
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    account_icon_badge(
                                        getattr(goal, "icon", None) or "flag",
                                        color=getattr(goal, "color", None)
                                        or get_active_skin().primary_hex(dark=True),
                                        size=metrics["icon"],
                                        glyph_size=metrics["glyph"],
                                    ),
                                    adaptive_text(
                                        goal.name,
                                        page=page,
                                        size=17,
                                        weight=ft.FontWeight.W_700,
                                        expand=True,
                                        max_lines=2,
                                        minimum=13,
                                        maximum=22,
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=6,
                                wrap=True,
                                controls=chips,
                            ),
                        ],
                    ),
                    action_btn,
                ],
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=[
                    ft.Text(
                        f"{format_money_compact(goal.current_amount, currency)} / "
                        f"{format_money_compact(goal.target_amount, currency)}",
                        size=metrics["meta"],
                        weight=ft.FontWeight.W_600,
                        expand=True,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        f"{pct}%",
                        size=metrics["amount"],
                        weight=ft.FontWeight.W_800,
                        color=get_active_skin().primary_hex(dark=True),
                    ),
                ],
            ),
            ft.ProgressBar(
                value=ratio,
                color=get_active_skin().primary_hex(dark=True),
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                bar_height=8,
                border_radius=999,
            ),
        ]
        if item_rings and show_item_rings:
            body_controls.append(
                ft.Column(
                    spacing=8,
                    tight=True,
                    controls=[
                        ft.Text(
                            tr("goal.items_section", language),
                            size=metrics["meta"],
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        h_scroll(
                            item_rings,
                            spacing=8,
                            height=metrics["ring"] + 52,
                            padding=ft.Padding.only(top=8, bottom=4),
                        ),
                    ],
                )
            )
        body_controls.append(muted_text(" · ".join(footer_bits), page=page))

        body = ft.Column(
            spacing=metrics["gap"],
            tight=True,
            controls=body_controls,
        )
        card = card_surface(
            body,
            padding=metrics["padding"],
            ink=on_click is not None,
            on_click=lambda _e: on_click(goal) if on_click else None,
            animate=False,
        )
        super().__init__(
            padding=card.padding,
            border_radius=card.border_radius,
            bgcolor=card.bgcolor,
            border=card.border,
            shadow=card.shadow,
            ink=on_click is not None,
            on_click=card.on_click,
            animate=card.animate,
            content=body,
        )
