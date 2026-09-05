"""Budget hero ring, list card, and analytics tiles."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Optional

import flet as ft

from lib.domain.use_cases.budget_insights import BudgetPace
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import alert_corner, card_surface, muted_text
from lib.presentation.widgets.goal_progress import circular_progress_badge
from lib.presentation.utils import format_money_compact, tappable_compact_money, tr
from lib.presentation.count_up import mark_money_text, mark_progress
from lib.presentation.widgets.period_scale import (
    budget_month_bounds,
    period_progress_scale,
)

if TYPE_CHECKING:
    from lib.domain.entities.budget import BudgetProgress


def _bar_color(percent: Decimal) -> str:
    if percent > 100:
        return ft.Colors.ERROR
    if percent >= 80:
        return ft.Colors.AMBER
    return ft.Colors.GREEN


def budgets_summary_ring(
    *,
    spent: Decimal,
    limit: Decimal,
    remaining: Decimal,
    currency: str,
    language: str,
    over_count: int = 0,
    warning_count: int = 0,
    count: int = 0,
) -> ft.Control:
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    ratio = float(spent / limit) if limit > 0 else 0.0
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100))
    over = remaining < 0
    leftover_label = (
        tr("budgets.overspend", language) if over else tr("budgets.remaining", language)
    )
    leftover_color = ft.Colors.ERROR if over else None
    chips: list[ft.Control] = [
        _metric_chip(
            leftover_label,
            format_money_compact(remaining, currency, signed=over),
            color=leftover_color,
            bgcolor=ft.Colors.ERROR_CONTAINER if over else None,
        ),
        _metric_chip(
            tr("budgets.total_limit", language),
            format_money_compact(limit, currency),
        ),
        _metric_chip(tr("budgets.filter.all", language) + f": {count}", "", value_hidden=True),
    ]
    if over_count:
        chips.append(
            _metric_chip(
                tr("budgets.filter.over", language) + f": {over_count}",
                "",
                value_hidden=True,
                color=ft.Colors.ON_ERROR,
                bgcolor=ft.Colors.ERROR,
            )
        )
    elif warning_count:
        chips.append(
            _metric_chip(
                tr("budgets.filter.warning", language) + f": {warning_count}",
                "",
                value_hidden=True,
            )
        )
    return card_surface(
        ft.Column(
            spacing=14,
            tight=True,
            controls=[
                ft.Row(
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        circular_progress_badge(
                            min(ratio, 1.0),
                            f"{pct}%",
                            size=96,
                            color=ft.Colors.ERROR if over else primary,
                        ),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("nav.budgets", language),
                                    size=12,
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                mark_money_text(
                                    ft.Text(
                                        format_money_compact(spent, currency),
                                        size=26,
                                        weight=ft.FontWeight.W_800,
                                        color=ft.Colors.ERROR if over else primary,
                                    ),
                                    spent,
                                    currency=currency,
                                    compact=True,
                                ),
                                muted_text(tr("budgets.total_spent", language)),
                            ],
                        ),
                    ],
                ),
                ft.Row(spacing=8, wrap=True, controls=chips),
            ],
        ),
        padding=16,
    )


def budget_list_card(
    progress: "BudgetProgress",
    *,
    language: str,
    currency: str,
    category_icon: str = "category",
    category_color: str = "#546E7A",
    category_name: str,
    pace: BudgetPace | None = None,
    sparkline: ft.Control | None = None,
    alert: bool = False,
    on_open: Optional[Callable] = None,
    compact: bool = False,
) -> ft.Control:
    percent = progress.percent
    color = _bar_color(percent)
    over = progress.is_over_budget
    leftover = progress.remaining
    leftover_txt = (
        f"{tr('budgets.overspend', language)}: "
        f"{format_money_compact(leftover, currency, signed=True)}"
        if over
        else f"{tr('budgets.remaining', language)}: "
        f"{format_money_compact(leftover, currency)}"
    )
    if compact:
        accent = ft.Colors.ERROR if over else color
        inner: ft.Control = ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        account_icon_badge(
                            category_icon,
                            color=category_color,
                            size=30,
                            glyph_size=14,
                            glyph_color="#FFFFFF",
                        ),
                        ft.Column(
                            spacing=1,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    category_name,
                                    weight=ft.FontWeight.W_700,
                                    size=13,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    f"{format_money_compact(progress.spent, currency)}"
                                    f" / {format_money_compact(progress.limit, currency)}"
                                    f" · {leftover_txt}",
                                    size=10,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                            border_radius=999,
                            bgcolor=ft.Colors.with_opacity(0.14, accent),
                            content=ft.Text(
                                f"{percent:.0f}%",
                                size=12,
                                weight=ft.FontWeight.W_800,
                                color=accent,
                            ),
                        ),
                    ],
                ),
                _budget_spend_bar(percent, color),
            ],
        )
        return card_surface(
            inner,
            ink=on_open is not None,
            on_click=(lambda _e: on_open(progress) if on_open else None),
            padding=10,
        )

    pace_line: ft.Control | None = None
    if pace is not None:
        daily = format_money_compact(pace.daily_allowance, currency)
        if over:
            pace_line = muted_text(tr("budgets.pace_over", language))
        elif pace.on_track:
            pace_line = muted_text(tr("budgets.pace_ok", language, daily=daily))
        else:
            pace_line = muted_text(tr("budgets.pace_fast", language, daily=daily))
    body: list[ft.Control] = [
        ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                account_icon_badge(
                    category_icon,
                    color=category_color,
                    size=40,
                    glyph_size=18,
                    glyph_color="#FFFFFF",
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            category_name,
                            weight=ft.FontWeight.W_700,
                            size=15,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"{format_money_compact(progress.spent, currency)} / "
                            f"{format_money_compact(progress.limit, currency)}",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                ),
                ft.Text(
                    f"{percent:.0f}%",
                    size=14,
                    weight=ft.FontWeight.W_800,
                    color=color,
                ),
            ],
        ),
        _budget_spend_bar(percent, color),
        muted_text(leftover_txt),
    ]
    if pace_line is not None:
        body.append(pace_line)
    if sparkline is not None:
        body.append(sparkline)
    inner = ft.Column(spacing=8, tight=True, controls=body)
    if alert:
        inner = ft.Stack(
            clip_behavior=ft.ClipBehavior.NONE,
            controls=[
                inner,
                alert_corner(tooltip=tr("budgets.title", language)),
            ],
        )
    return card_surface(
        inner,
        ink=on_open is not None,
        on_click=(lambda _e: on_open(progress) if on_open else None),
        padding=14,
    )


def analytics_budget_tile(
    progress: "BudgetProgress",
    *,
    language: str,
    currency: str,
    category_icon: str = "category",
    category_color: str = "#546E7A",
    category_name: str,
) -> ft.Control:
    percent = progress.percent
    ratio = min(float(percent) / 100.0, 1.0) if percent > 0 else 0.0
    color = _bar_color(percent)
    over = progress.is_over_budget
    body: list[ft.Control] = [
        ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                circular_progress_badge(
                    ratio,
                    f"{int(round(min(float(percent), 999)))}%",
                    size=52,
                    color=color,
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Row(
                            spacing=8,
                            controls=[
                                account_icon_badge(
                                    category_icon,
                                    color=category_color,
                                    size=28,
                                    glyph_size=14,
                                    glyph_color="#FFFFFF",
                                ),
                                ft.Text(
                                    category_name,
                                    expand=True,
                                    weight=ft.FontWeight.W_700,
                                    size=15,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                        muted_text(
                            tr("budgets.overspend", language)
                            if over
                            else tr("budgets.remaining", language)
                        ),
                    ],
                ),
                tappable_compact_money(
                    None,
                    progress.spent,
                    currency,
                    language=language,
                    size=15,
                    weight=ft.FontWeight.W_800,
                    color=color,
                ),
            ],
        ),
    ]
    month = int(getattr(progress, "month", 0) or 0)
    year = int(getattr(progress, "year", 0) or 0)
    if month and year:
        start, end = budget_month_bounds(month, year)
        scale = period_progress_scale(
            color=color,
            start=start,
            end=end,
        )
        if scale is not None:
            body.append(scale)

    return card_surface(
        ft.Column(spacing=8, tight=True, controls=body),
        padding=12,
    )


def _budget_spend_bar(percent: float, color: str) -> ft.Control:
    from lib.presentation.ui_motion import is_ui_animating

    clamped = min(float(percent) / 100.0, 1.0)
    animate = is_ui_animating()
    bar = ft.ProgressBar(
        value=0.0 if animate else clamped,
        color=color,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )
    if animate:
        mark_progress(bar, clamped)
    return bar


def _metric_chip(
    label: str,
    value: str,
    *,
    color: str | None = None,
    bgcolor: str | None = None,
    value_hidden: bool = False,
) -> ft.Control:
    text_color = color or ft.Colors.ON_SURFACE_VARIANT
    children: list[ft.Control] = [ft.Text(label, size=11, color=text_color)]
    if not value_hidden and value:
        children.append(
            ft.Text(
                value,
                size=13,
                weight=ft.FontWeight.W_700,
                color=color or ft.Colors.ON_SURFACE,
            )
        )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=10,
        bgcolor=bgcolor or ft.Colors.SURFACE_CONTAINER,
        content=ft.Column(spacing=2, tight=True, controls=children),
    )
