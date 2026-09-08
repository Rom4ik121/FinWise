"""Aggregate subscription monthly / yearly summary."""

from __future__ import annotations

from decimal import Decimal

import flet as ft

from lib.presentation.count_up import mark_money_text
from lib.presentation.responsive import hero_block_metrics, tile_ring_metrics
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import card_surface, metric_chip, muted_text
from lib.presentation.utils import format_money_compact, tappable_compact_money, tr
from lib.presentation.widgets.goal_progress import circular_progress_badge
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
    page: ft.Page | None = None,
) -> ft.Control:
    """Monthly cost with yearly equivalent and due-this-week chip."""
    metrics = hero_block_metrics(page)
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    year_ratio = float(monthly / yearly) if yearly > 0 else 0.0
    chips: list[ft.Control] = [
        metric_chip(
            tr("subscriptions.yearly_total", language),
            format_money_compact(yearly, currency),
            page=page,
        ),
        metric_chip(
            tr("subscriptions.active_count", language, count=str(active_count)),
            "",
            page=page,
            value_hidden=True,
        ),
    ]
    if due_week_count > 0:
        chips.append(
            metric_chip(
                tr("subscription.due_this_week", language, count=str(due_week_count)),
                format_money_compact(due_week_amount, currency),
                page=page,
                color=ft.Colors.ON_ERROR,
                bgcolor=ft.Colors.ERROR,
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
                            year_ratio if yearly > 0 else 0.0,
                            tr("subscriptions.per_month_short", language),
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
                                    tr("subscriptions.monthly_total", language),
                                    size=metrics["title"],
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    format_money_compact(monthly, currency),
                                    size=metrics["amount"],
                                    weight=ft.FontWeight.W_800,
                                    color=primary,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    no_wrap=True,
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


def analytics_subscriptions_summary(
    *,
    spent: Decimal,
    monthly: Decimal,
    yearly: Decimal,
    currency: str,
    language: str,
    active_count: int,
    page: ft.Page | None = None,
) -> ft.Control:
    """Hero summary for the analytics subscriptions section."""
    metrics = hero_block_metrics(page)
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    ratio = float(spent / monthly) if monthly > 0 else 0.0
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100))
    chips: list[ft.Control] = [
        metric_chip(
            tr("analytics.subscriptions_monthly_cost", language),
            format_money_compact(monthly, currency),
            page=page,
        ),
        metric_chip(
            tr("subscriptions.yearly_total", language),
            format_money_compact(yearly, currency),
            page=page,
        ),
        metric_chip(
            tr("subscriptions.active_count", language, count=str(active_count)),
            "",
            page=page,
            value_hidden=True,
        ),
    ]
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
                            min(ratio, 1.0),
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
                                    tr("analytics.subscriptions", language),
                                    size=metrics["title"],
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                mark_money_text(
                                    ft.Text(
                                        format_money_compact(spent, currency),
                                        size=metrics["amount"],
                                        weight=ft.FontWeight.W_800,
                                        color=primary,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        no_wrap=True,
                                    ),
                                    spent,
                                    currency=currency,
                                    compact=True,
                                ),
                                muted_text(
                                    tr("analytics.subscriptions_spent", language),
                                    page=page,
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
    page: ft.Page | None = None,
) -> ft.Control:
    """One subscription row: icon, spend in period, monthly run-rate."""
    from lib.presentation.account_icons import account_icon_badge

    tile = tile_ring_metrics(page)
    share_clamped = max(0.0, min(float(share), 1.0))
    pct = int(round(share_clamped * 100))
    accent = color or get_active_skin().primary_hex(dark=True)
    body: list[ft.Control] = [
        ft.Row(
            spacing=tile["gap"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                account_icon_badge(
                    icon or "autorenew",
                    color=accent,
                    size=max(32, tile["icon"] + 8),
                    glyph_size=tile["glyph"] + 2,
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
                                    + " ·",
                                    page=page,
                                ),
                                tappable_compact_money(
                                    page,
                                    monthly,
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
                    spacing=0,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        tappable_compact_money(
                            page,
                            spent,
                            currency,
                            language=language,
                            size=tile["amount"],
                            weight=ft.FontWeight.W_800,
                        ),
                        muted_text(f"{pct}%", page=page)
                        if pct > 0
                        else muted_text("—", page=page),
                    ],
                ),
            ],
        ),
    ]
    scale = period_progress_scale(
        color=accent,
        start=period_start,
        end=period_end,
    )
    if scale is not None:
        body.append(scale)
    return card_surface(
        ft.Column(spacing=tile["gap"], tight=True, controls=body),
        padding=tile["padding"],
    )
