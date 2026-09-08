"""Aggregate debt summary ring and analytics tiles."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import flet as ft

from lib.domain.entities.debt import DebtDirection, DebtStatus
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.count_up import mark_money_text
from lib.presentation.responsive import hero_block_metrics, tile_ring_metrics
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import amount_color, card_surface, metric_chip, muted_text
from lib.presentation.utils import format_money_compact, tappable_compact_money, tr
from lib.presentation.widgets.goal_progress import circular_progress_badge
from lib.presentation.widgets.period_scale import period_progress_scale

if TYPE_CHECKING:
    from lib.domain.entities.debt import Debt


def debts_summary_ring(
    *,
    i_owe: Decimal,
    owed_to_me: Decimal,
    currency: str,
    language: str,
    overdue_count: int = 0,
    page: ft.Page | None = None,
) -> ft.Control:
    """Net debt position with directional totals."""
    metrics = hero_block_metrics(page)
    net = owed_to_me - i_owe
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    total_exposure = i_owe + owed_to_me
    ratio = float(i_owe / total_exposure) if total_exposure > 0 else 0.0
    pct = int(round(ratio * 100))
    net_color = amount_color(net >= 0, dark=True)
    chips: list[ft.Control] = [
        metric_chip(
            tr("debts.total_i_owe", language),
            format_money_compact(i_owe, currency),
            page=page,
            color=ft.Colors.ERROR,
            bgcolor=ft.Colors.ERROR_CONTAINER,
        ),
        metric_chip(
            tr("debts.total_owed_to_me", language),
            format_money_compact(owed_to_me, currency),
            page=page,
            color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
        ),
    ]
    if overdue_count > 0:
        chips.append(
            metric_chip(
                tr("debt.overdue_count", language, count=str(overdue_count)),
                "",
                page=page,
                color=ft.Colors.ON_ERROR,
                bgcolor=ft.Colors.ERROR,
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
                            ratio if total_exposure > 0 else 0.0,
                            f"{pct}%",
                            size=metrics["ring"],
                            color=ft.Colors.ERROR if i_owe > owed_to_me else primary,
                            page=page,
                        ),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("debts.net_position", language),
                                    size=metrics["title"],
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    format_money_compact(net, currency),
                                    size=metrics["amount"],
                                    weight=ft.FontWeight.W_800,
                                    color=net_color,
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


def analytics_debts_summary(
    *,
    i_owe: Decimal,
    owed_to_me: Decimal,
    currency: str,
    language: str,
    debt_count: int,
    overdue_count: int,
    page: ft.Page | None = None,
) -> ft.Control:
    """Hero summary for analytics debts section."""
    metrics = hero_block_metrics(page)
    net = owed_to_me - i_owe
    net_color = amount_color(net >= 0, dark=True)
    chips: list[ft.Control] = [
        metric_chip(
            tr("analytics.i_owe", language),
            format_money_compact(i_owe, currency),
            page=page,
            color=ft.Colors.ERROR,
            bgcolor=ft.Colors.ERROR_CONTAINER,
        ),
        metric_chip(
            tr("analytics.owed_to_me", language),
            format_money_compact(owed_to_me, currency),
            page=page,
        ),
    ]
    if overdue_count:
        chips.append(
            metric_chip(
                tr("debt.overdue_count", language, count=str(overdue_count)),
                "",
                page=page,
                value_hidden=True,
                color=ft.Colors.ON_ERROR,
                bgcolor=ft.Colors.ERROR,
            )
        )
    chips.append(
        metric_chip(
            tr("analytics.debts_count", language, count=str(debt_count)),
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
                        ft.Icon(
                            ft.Icons.ACCOUNT_BALANCE,
                            size=max(32, metrics["ring"] // 2),
                            color=net_color,
                        ),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("nav.debts", language),
                                    size=metrics["title"],
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                mark_money_text(
                                    ft.Text(
                                        format_money_compact(net, currency),
                                        size=metrics["amount"],
                                        weight=ft.FontWeight.W_800,
                                        color=net_color,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        no_wrap=True,
                                    ),
                                    net,
                                    currency=currency,
                                    compact=True,
                                    signed=True,
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


def analytics_debt_tile(
    debt: "Debt",
    *,
    language: str,
    base_currency: str,
    page: ft.Page | None = None,
) -> ft.Control:
    """Compact debt row for analytics."""
    tile = tile_ring_metrics(page)
    currency = debt.currency or base_currency
    ratio = float(debt.progress_ratio)
    pct = int(round(max(0.0, min(ratio, 1.0)) * 100))
    status = (
        debt.status
        if isinstance(debt.status, DebtStatus)
        else DebtStatus(str(debt.status))
    )
    i_owe = debt.direction == DebtDirection.I_OWE
    accent = ft.Colors.ERROR if i_owe else ft.Colors.PRIMARY
    icon_key = getattr(debt, "icon", None) or "credit_card"
    icon_color = getattr(debt, "color", None) or accent
    badge: ft.Control | None = None
    if status == DebtStatus.OVERDUE:
        badge = ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=999,
            bgcolor=ft.Colors.ERROR_CONTAINER,
            content=ft.Text(
                tr("debt.status.overdue", language),
                size=max(9, tile["meta"] - 2),
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ERROR,
            ),
        )
    elif status == DebtStatus.PAID:
        badge = ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=999,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            content=ft.Text(
                tr("debt.status.paid", language),
                size=max(9, tile["meta"] - 2),
                weight=ft.FontWeight.W_700,
            ),
        )

    body_controls: list[ft.Control] = [
        ft.Row(
            spacing=tile["gap"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                circular_progress_badge(
                    ratio, f"{pct}%", size=tile["ring"], color=accent, page=page
                ),
                ft.Column(
                    spacing=4,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Row(
                            spacing=8,
                            controls=[
                                account_icon_badge(
                                    icon_key,
                                    color=icon_color,
                                    size=tile["icon"],
                                    glyph_size=tile["glyph"],
                                ),
                                ft.Text(
                                    debt.counterparty,
                                    expand=True,
                                    weight=ft.FontWeight.W_700,
                                    size=tile["title"],
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                        muted_text(
                            tr("debt.i_owe", language)
                            if i_owe
                            else tr("debt.owed_to_me", language),
                            page=page,
                        ),
                    ],
                ),
                ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    spacing=4,
                    tight=True,
                    controls=[
                        tappable_compact_money(
                            page,
                            debt.remaining_amount,
                            currency,
                            language=language,
                            size=tile["amount"],
                            weight=ft.FontWeight.W_800,
                            color=accent,
                        ),
                        badge if badge is not None else ft.Container(height=0),
                    ],
                ),
            ],
        ),
    ]
    scale = period_progress_scale(
        color=accent,
        start=getattr(debt, "started_at", None),
        end=getattr(debt, "due_date", None),
    )
    if scale is not None:
        body_controls.append(scale)

    return card_surface(
        ft.Column(spacing=tile["gap"], tight=True, controls=body_controls),
        padding=tile["padding"],
    )
