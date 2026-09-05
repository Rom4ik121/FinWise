"""Aggregate subscription monthly / yearly summary."""

from __future__ import annotations

from decimal import Decimal

import flet as ft

from lib.presentation.skins import get_active_skin
from lib.presentation.styles import card_surface, muted_text
from lib.presentation.widgets.goal_progress import circular_progress_badge
from lib.presentation.utils import format_money_compact, tappable_compact_money, tr
from lib.presentation.count_up import mark_money_text
from lib.presentation.widgets.period_scale import period_progress_scale


def subscriptions_summary_ring(
    *,
    monthly: Decimal,
    yearly: Decimal,
    currency: str,
    language: str,
    due_week_count: int = 0,
    due_week_amount: Decimal = Decimal("0"),
    active_count: int = 0,
) -> ft.Control:
    """Monthly cost with yearly equivalent and due-this-week chip."""
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    year_ratio = float(monthly / yearly) if yearly > 0 else 0.0
    chips: list[ft.Control] = [
        _metric_chip(
            tr("subscriptions.yearly_total", language),
            format_money_compact(yearly, currency),
        ),
        _metric_chip(
            tr("subscriptions.active_count", language, count=str(active_count)),
            "",
            value_hidden=True,
        ),
    ]
    if due_week_count > 0:
        chips.append(
            _metric_chip(
                tr("subscription.due_this_week", language, count=str(due_week_count)),
                format_money_compact(due_week_amount, currency),
                color=ft.Colors.ON_ERROR,
                bgcolor=ft.Colors.ERROR,
            )
        )
    return card_surface(
        ft.Column(
            spacing=12,
            tight=True,
            controls=[
                ft.Row(
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        circular_progress_badge(
                            year_ratio if yearly > 0 else 0.0,
                            tr("subscriptions.per_month_short", language),
                            size=88,
                            color=primary,
                        ),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("subscriptions.monthly_total", language),
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    format_money_compact(monthly, currency),
                                    size=22,
                                    weight=ft.FontWeight.W_800,
                                    color=primary,
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Row(spacing=8, wrap=True, controls=chips),
            ],
        ),
        padding=16,
    )


def _metric_chip(
    label: str,
    value: str,
    *,
    color: str | None = None,
    bgcolor: str | None = None,
    value_hidden: bool = False,
) -> ft.Control:
    text_color = color or ft.Colors.ON_SURFACE_VARIANT
    children: list[ft.Control] = [
        ft.Text(label, size=11, color=text_color),
    ]
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


def analytics_subscriptions_summary(
    *,
    spent: Decimal,
    monthly: Decimal,
    yearly: Decimal,
    currency: str,
    language: str,
    active_count: int,
) -> ft.Control:
    """Hero summary for the analytics subscriptions section."""
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    ratio = float(spent / monthly) if monthly > 0 else 0.0
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100))
    chips: list[ft.Control] = [
        _metric_chip(
            tr("analytics.subscriptions_monthly_cost", language),
            format_money_compact(monthly, currency),
        ),
        _metric_chip(
            tr("subscriptions.yearly_total", language),
            format_money_compact(yearly, currency),
        ),
        _metric_chip(
            tr("subscriptions.active_count", language, count=str(active_count)),
            "",
            value_hidden=True,
        ),
    ]
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
                            color=primary,
                        ),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("analytics.subscriptions", language),
                                    size=12,
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                mark_money_text(
                                    ft.Text(
                                        format_money_compact(spent, currency),
                                        size=26,
                                        weight=ft.FontWeight.W_800,
                                        color=primary,
                                    ),
                                    spent,
                                    currency=currency,
                                    compact=True,
                                ),
                                muted_text(
                                    tr("analytics.subscriptions_spent", language)
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Row(spacing=8, wrap=True, controls=chips),
            ],
        ),
        padding=16,
    )


def analytics_subscription_tile(
    *,
    name: str,
    icon: str,
    color: str,
    spent: Decimal,
    monthly: Decimal,
    currency: str,
    language: str,
    share: float = 0.0,
    period_start=None,
    period_end=None,
) -> ft.Control:
    """One subscription row: icon, spend in period, monthly run-rate."""
    from lib.presentation.account_icons import account_icon_badge

    share_clamped = max(0.0, min(float(share), 1.0))
    pct = int(round(share_clamped * 100))
    accent = color or get_active_skin().primary_hex(dark=True)
    body: list[ft.Control] = [
        ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                account_icon_badge(
                    icon or "autorenew",
                    color=accent,
                    size=40,
                    glyph_size=18,
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            name,
                            weight=ft.FontWeight.W_700,
                            size=15,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Row(
                            spacing=4,
                            tight=True,
                            controls=[
                                muted_text(
                                    tr(
                                        "analytics.subscriptions_monthly_cost",
                                        language,
                                    )
                                    + " ·"
                                ),
                                tappable_compact_money(
                                    None,
                                    monthly,
                                    currency,
                                    language=language,
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Column(
                    spacing=0,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        tappable_compact_money(
                            None,
                            spent,
                            currency,
                            language=language,
                            size=15,
                            weight=ft.FontWeight.W_800,
                        ),
                        muted_text(f"{pct}%") if pct > 0 else muted_text("—"),
                    ],
                ),
            ],
        ),
    ]
    # Only when subscription has an explicit end date.
    scale = period_progress_scale(
        color=accent,
        start=period_start,
        end=period_end,
    )
    if scale is not None:
        body.append(scale)
    return card_surface(
        ft.Column(spacing=8, tight=True, controls=body),
        padding=12,
    )
