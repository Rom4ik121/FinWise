"""Aggregate circular progress for goals list and analytics."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import flet as ft

from lib.domain.entities.goal import GoalStatus
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.count_up import mark_money_text
from lib.presentation.responsive import hero_block_metrics, tile_ring_metrics
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import card_surface, metric_chip
from lib.presentation.utils import format_money_compact, tappable_compact_money, tr
from lib.presentation.widgets.goal_progress import circular_progress_badge
from lib.presentation.widgets.period_scale import period_progress_scale

if TYPE_CHECKING:
    from lib.domain.entities.goal import Goal


def goals_summary_ring(
    *,
    saved: Decimal,
    target: Decimal,
    currency: str,
    language: str,
    page: ft.Page | None = None,
) -> ft.Control:
    """Large ring showing total saved vs target across active goals."""
    metrics = hero_block_metrics(page)
    ratio = float(saved / target) if target > 0 else 0.0
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100))
    return ft.Container(
        padding=metrics["padding"],
        border_radius=18,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Row(
            spacing=metrics["gap"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                circular_progress_badge(
                    ratio, f"{pct}%", size=metrics["ring"], page=page
                ),
                ft.Column(
                    spacing=4,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            tr("goals.total_saved", language),
                            size=metrics["title"],
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            format_money_compact(saved, currency),
                            size=metrics["amount"],
                            weight=ft.FontWeight.W_800,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
                        ),
                        ft.Text(
                            f"/ {format_money_compact(target, currency)}",
                            size=metrics["meta"],
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                ),
            ],
        ),
    )


def analytics_goals_summary(
    *,
    saved: Decimal,
    target: Decimal,
    remaining: Decimal,
    currency: str,
    language: str,
    goal_count: int,
    page: ft.Page | None = None,
) -> ft.Control:
    """Hero summary for analytics goals section."""
    metrics = hero_block_metrics(page)
    ratio = float(saved / target) if target > 0 else 0.0
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100))
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    chips: list[ft.Control] = [
        metric_chip(
            tr("goals.total_target", language),
            format_money_compact(target, currency),
            page=page,
        ),
    ]
    if remaining > 0:
        chips.append(
            metric_chip(
                tr("goals.total_remaining", language),
                format_money_compact(remaining, currency),
                page=page,
                color=ft.Colors.ERROR,
                bgcolor=ft.Colors.ERROR_CONTAINER,
            )
        )
    chips.append(
        metric_chip(
            tr("analytics.goals_count", language, count=str(goal_count)),
            "",
            page=page,
            value_hidden=True,
        )
    )
    return card_surface(
        ft.Column(
            spacing=metrics["row_gap"],
            tight=True,
            controls=[
                ft.Row(
                    spacing=metrics["gap"],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        circular_progress_badge(
                            ratio,
                            f"{pct}%",
                            size=metrics["ring"],
                            color=primary,
                            page=page,
                        ),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("nav.goals", language),
                                    size=metrics["title"],
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                mark_money_text(
                                    ft.Text(
                                        format_money_compact(saved, currency),
                                        size=metrics["amount"],
                                        weight=ft.FontWeight.W_800,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        no_wrap=True,
                                    ),
                                    saved,
                                    currency=currency,
                                    compact=True,
                                ),
                                ft.Text(
                                    tr(
                                        "analytics.goals_saved_of",
                                        language,
                                        target=format_money_compact(target, currency),
                                    ),
                                    size=metrics["meta"],
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Row(spacing=8, wrap=True, controls=chips),
            ],
        ),
        padding=metrics["padding"],
    )


def analytics_goal_tile(
    goal: "Goal",
    *,
    language: str,
    base_currency: str,
    page: ft.Page | None = None,
) -> ft.Control:
    """Compact goal row for analytics list."""
    tile = tile_ring_metrics(page)
    currency = goal.currency or base_currency
    ratio = float(goal.progress_ratio)
    ratio_clamped = max(0.0, min(ratio, 1.0))
    pct = int(round(ratio_clamped * 100))
    status = (
        goal.status
        if isinstance(goal.status, GoalStatus)
        else GoalStatus(str(goal.status))
    )
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    icon_key = getattr(goal, "icon", None) or "flag"
    icon_color = getattr(goal, "color", None) or primary
    completed = status == GoalStatus.COMPLETED
    ring_label = "✓" if completed else f"{pct}%"
    ring_color = ft.Colors.OUTLINE if completed else primary

    badge: ft.Control | None = None
    if completed:
        badge = ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=999,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            content=ft.Text(
                tr("goal.badge.completed", language),
                size=max(9, tile["meta"] - 2),
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SECONDARY_CONTAINER,
            ),
        )

    body: list[ft.Control] = [
        ft.Row(
            spacing=tile["gap"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                circular_progress_badge(
                    ratio_clamped,
                    ring_label,
                    size=tile["ring"],
                    color=ring_color,
                    page=page,
                ),
                ft.Column(
                    spacing=4,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                account_icon_badge(
                                    icon_key,
                                    color=icon_color,
                                    size=tile["icon"],
                                    glyph_size=tile["glyph"],
                                ),
                                ft.Text(
                                    goal.name,
                                    expand=True,
                                    weight=ft.FontWeight.W_700,
                                    size=tile["title"],
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                        ft.Row(
                            spacing=4,
                            tight=True,
                            controls=[
                                tappable_compact_money(
                                    page,
                                    goal.current_amount,
                                    currency,
                                    language=language,
                                    size=tile["meta"],
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    "/",
                                    size=tile["meta"],
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                tappable_compact_money(
                                    page,
                                    goal.target_amount,
                                    currency,
                                    language=language,
                                    size=tile["meta"],
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    spacing=4,
                    tight=True,
                    controls=[
                        ft.Text(
                            f"{pct}%",
                            size=tile["amount"] + 2,
                            weight=ft.FontWeight.W_800,
                            color=primary if not completed else ft.Colors.OUTLINE,
                        ),
                        badge if badge is not None else ft.Container(height=0),
                    ],
                ),
            ],
        ),
    ]
    scale = period_progress_scale(
        color=primary if not completed else ft.Colors.OUTLINE,
        start=getattr(goal, "created_at", None),
        end=getattr(goal, "deadline", None),
    )
    if scale is not None:
        body.append(scale)

    return card_surface(
        ft.Column(spacing=tile["gap"], tight=True, controls=body),
        padding=tile["padding"],
    )
