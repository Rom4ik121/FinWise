"""Aggregate debt summary ring and analytics tiles."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import flet as ft

from lib.domain.entities.debt import DebtDirection, DebtStatus
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import amount_color, card_surface, muted_text
from lib.presentation.widgets.goal_progress import circular_progress_badge
from lib.presentation.utils import format_money_compact, tr

if TYPE_CHECKING:
    from lib.domain.entities.debt import Debt


def debts_summary_ring(
    *,
    i_owe: Decimal,
    owed_to_me: Decimal,
    currency: str,
    language: str,
    overdue_count: int = 0,
) -> ft.Control:
    """Net debt position with directional totals."""
    net = owed_to_me - i_owe
    skin = get_active_skin()
    primary = skin.primary_hex(dark=True)
    total_exposure = i_owe + owed_to_me
    ratio = float(i_owe / total_exposure) if total_exposure > 0 else 0.0
    pct = int(round(ratio * 100))
    net_color = amount_color(net >= 0, dark=True)
    chips: list[ft.Control] = [
        _metric_chip(
            tr("debts.total_i_owe", language),
            format_money_compact(i_owe, currency),
            color=ft.Colors.ERROR,
            bgcolor=ft.Colors.ERROR_CONTAINER,
        ),
        _metric_chip(
            tr("debts.total_owed_to_me", language),
            format_money_compact(owed_to_me, currency),
            color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
        ),
    ]
    if overdue_count > 0:
        chips.append(
            _metric_chip(
                tr("debt.overdue_count", language, count=str(overdue_count)),
                "",
                color=ft.Colors.ON_ERROR,
                bgcolor=ft.Colors.ERROR,
                value_hidden=True,
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
                            ratio if total_exposure > 0 else 0.0,
                            f"{pct}%",
                            size=88,
                            color=ft.Colors.ERROR if i_owe > owed_to_me else primary,
                        ),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("debts.net_position", language),
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    format_money_compact(net, currency),
                                    size=22,
                                    weight=ft.FontWeight.W_800,
                                    color=net_color,
                                ),
                                muted_text(tr("debts.net_position_hint", language)),
                            ],
                        ),
                    ],
                ),
                ft.Row(spacing=8, wrap=True, controls=chips),
            ],
        ),
        padding=16,
    )


def analytics_debts_summary(
    *,
    i_owe: Decimal,
    owed_to_me: Decimal,
    currency: str,
    language: str,
    debt_count: int,
    overdue_count: int,
) -> ft.Control:
    """Hero summary for analytics debts section."""
    net = owed_to_me - i_owe
    net_color = amount_color(net >= 0, dark=True)
    chips: list[ft.Control] = [
        _metric_chip(
            tr("analytics.i_owe", language),
            format_money_compact(i_owe, currency),
            color=ft.Colors.ERROR,
            bgcolor=ft.Colors.ERROR_CONTAINER,
        ),
        _metric_chip(
            tr("analytics.owed_to_me", language),
            format_money_compact(owed_to_me, currency),
        ),
    ]
    if overdue_count:
        chips.append(
            _metric_chip(
                tr("debt.overdue_count", language, count=str(overdue_count)),
                "",
                value_hidden=True,
                color=ft.Colors.ON_ERROR,
                bgcolor=ft.Colors.ERROR,
            )
        )
    chips.append(
        _metric_chip(
            tr("analytics.debts_count", language, count=str(debt_count)),
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
                        ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=48, color=net_color),
                        ft.Column(
                            spacing=4,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    tr("nav.debts", language),
                                    size=12,
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    format_money_compact(net, currency),
                                    size=26,
                                    weight=ft.FontWeight.W_800,
                                    color=net_color,
                                ),
                                muted_text(tr("debts.net_position_hint", language)),
                            ],
                        ),
                    ],
                ),
                ft.Row(spacing=8, wrap=True, controls=chips),
            ],
        ),
        padding=16,
    )


def analytics_debt_tile(
    debt: "Debt",
    *,
    language: str,
    base_currency: str,
) -> ft.Control:
    """Compact debt row for analytics."""
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
                size=10,
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
                size=10,
                weight=ft.FontWeight.W_700,
            ),
        )

    return card_surface(
        ft.Column(
            spacing=10,
            tight=True,
            controls=[
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        circular_progress_badge(ratio, f"{pct}%", size=52, color=accent),
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
                                            size=28,
                                            glyph_size=14,
                                        ),
                                        ft.Text(
                                            debt.counterparty,
                                            expand=True,
                                            weight=ft.FontWeight.W_700,
                                            size=15,
                                            max_lines=2,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                    ],
                                ),
                                muted_text(
                                    tr("debt.i_owe", language)
                                    if i_owe
                                    else tr("debt.owed_to_me", language)
                                ),
                            ],
                        ),
                        ft.Column(
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            spacing=4,
                            tight=True,
                            controls=[
                                ft.Text(
                                    format_money_compact(
                                        debt.remaining_amount, currency
                                    ),
                                    size=16,
                                    weight=ft.FontWeight.W_800,
                                    color=accent,
                                ),
                                badge if badge is not None else ft.Container(height=0),
                            ],
                        ),
                    ],
                ),
                ft.ProgressBar(
                    value=max(0.0, min(ratio, 1.0)),
                    color=accent,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    bar_height=6,
                    border_radius=999,
                ),
            ],
        ),
        padding=14,
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
