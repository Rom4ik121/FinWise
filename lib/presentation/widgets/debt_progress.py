"""Debt payoff projection card for detail view."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

import flet as ft

from lib.presentation.styles import card_surface, muted_text
from lib.presentation.utils import format_date, format_money, tr


def debt_projection_card(
    *,
    language: str,
    currency: str,
    recommended_monthly: Optional[Decimal] = None,
    average_monthly: Optional[Decimal] = None,
    projected_date: Optional[datetime] = None,
    is_on_track: Optional[bool] = None,
    streak_months: int = 0,
) -> ft.Control:
    """Formatted projection block."""
    rows: list[ft.Control] = [
        ft.Text(tr("debt.projection", language), weight=ft.FontWeight.W_700),
    ]
    if recommended_monthly is not None:
        rows.append(
            muted_text(
                f"{tr('debt.recommended_monthly', language)}: "
                f"{format_money(recommended_monthly, currency)}"
            )
        )
    if average_monthly is not None and average_monthly > 0:
        rows.append(
            muted_text(
                f"{tr('debt.average_monthly', language)}: "
                f"{format_money(average_monthly, currency)}"
            )
        )
    if projected_date is not None:
        rows.append(
            muted_text(
                f"{tr('debt.projected_date', language)}: "
                f"{format_date(projected_date)}"
            )
        )
    if is_on_track is True:
        rows.append(ft.Text(tr("debt.on_track", language), color=ft.Colors.PRIMARY))
    elif is_on_track is False:
        rows.append(ft.Text(tr("debt.off_track", language), color=ft.Colors.ERROR))
    if streak_months > 0:
        rows.append(
            muted_text(
                tr("debt.payment_streak", language, months=str(streak_months))
            )
        )
    return card_surface(ft.Column(spacing=6, tight=True, controls=rows))
