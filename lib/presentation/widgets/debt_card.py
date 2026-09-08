"""Debt summary card."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

import flet as ft

from lib.domain.entities.debt import Debt, DebtDirection, DebtStatus
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.components.layout.text import adaptive_text, money_label
from lib.presentation.responsive import entity_card_metrics
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import amount_color, card_surface, muted_text, style_popup_menu
from lib.presentation.utils import format_date, format_money, format_money_compact


class DebtCard(ft.Container):
    """Card for a personal debt with progress and optional interest line."""

    def __init__(
        self,
        debt: Debt,
        *,
        language: str = "ru",
        interest_amount: Optional[Decimal] = None,
        projected_payoff_date=None,
        sparkline: Optional[ft.Control] = None,
        alert: bool = False,
        on_click: Optional[Callable[[Debt], None]] = None,
        on_edit: Optional[Callable[[Debt], None]] = None,
        on_delete: Optional[Callable[[Debt], None]] = None,
        on_repay: Optional[Callable[[Debt], None]] = None,
        page: ft.Page | None = None,
    ) -> None:
        from lib.presentation.utils import tr

        metrics = entity_card_metrics(page)
        i_owe = debt.direction == DebtDirection.I_OWE
        accent = amount_color(not i_owe)
        icon_key = getattr(debt, "icon", None) or "credit_card"
        icon_color = getattr(debt, "color", None) or accent
        status_value = (
            debt.status.value
            if isinstance(debt.status, DebtStatus)
            else str(debt.status)
        )
        status_color = (
            ft.Colors.ON_SURFACE_VARIANT
            if debt.status in (DebtStatus.PAID, DebtStatus.ARCHIVED)
            else (ft.Colors.ERROR if debt.status == DebtStatus.OVERDUE else accent)
        )
        interest_line: list[ft.Control] = []
        if debt.interest_rate is not None:
            text = tr(
                "debt.interest_per_year",
                language,
                rate=str(debt.interest_rate),
            )
            if interest_amount is not None:
                text += f" · {format_money(interest_amount, debt.currency)}"
            interest_line.append(muted_text(text, page=page))
        if getattr(debt, "accrued_interest", None) and debt.accrued_interest > 0:
            interest_line.append(
                muted_text(
                    tr(
                        "debt.accrued_interest",
                        language,
                        amount=format_money_compact(
                            debt.accrued_interest, debt.currency
                        ),
                    ),
                    page=page,
                )
            )

        menu_items = [
            ft.PopupMenuItem(
                content=ft.Text(tr("action.edit", language)),
                icon=ft.Icons.EDIT_OUTLINED,
                on_click=lambda _e: on_edit(debt) if on_edit else None,
            ),
            ft.PopupMenuItem(
                content=ft.Text(tr("action.delete", language)),
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=lambda _e: on_delete(debt) if on_delete else None,
            ),
        ]
        can_repay = (
            on_repay is not None
            and debt.status in (DebtStatus.ACTIVE, DebtStatus.OVERDUE)
        )
        if can_repay:
            menu_items.insert(
                0,
                ft.PopupMenuItem(
                    content=ft.Text(
                        tr("debt.repay", language)
                        if i_owe
                        else tr("debt.receive", language)
                    ),
                    icon=ft.Icons.PAYMENTS_OUTLINED,
                    on_click=lambda _e: on_repay(debt),
                ),
            )

        actions_row: list[ft.Control] = [
            style_popup_menu(
                ft.PopupMenuButton(
                    icon=ft.Icons.MORE_VERT,
                    icon_color=ft.Colors.ON_SURFACE_VARIANT,
                    items=menu_items,
                )
            )
        ]
        if alert:
            actions_row.insert(
                0,
                ft.IconButton(
                    icon=ft.Icons.PRIORITY_HIGH,
                    icon_color=ft.Colors.ON_ERROR,
                    bgcolor=ft.Colors.ERROR,
                    tooltip=tr("notify.debt_due", language),
                    on_click=lambda _e: on_click(debt) if on_click else None,
                    style=ft.ButtonStyle(
                        shape=ft.CircleBorder(),
                        padding=10,
                    ),
                ),
            )
        elif can_repay:
            actions_row.insert(
                0,
                ft.IconButton(
                    icon=ft.Icons.PAYMENTS_OUTLINED,
                    icon_color=accent,
                    tooltip=tr("debt.repay", language)
                    if i_owe
                    else tr("debt.receive", language),
                    on_click=lambda _e: on_repay(debt),
                ),
            )

        ratio = float(getattr(debt, "progress_ratio", 0.0) or 0.0)
        pct = int(round(ratio * 100))
        due_line = (
            tr("debt.due_by", language, date=format_date(debt.due_date))
            if debt.due_date
            else tr("debt.no_due_date", language)
        )
        schedule_line: list[ft.Control] = []
        if debt.next_payment_date is not None:
            amt = ""
            if debt.next_payment_amount is not None:
                amt = f" · {format_money_compact(debt.next_payment_amount, debt.currency)}"
            schedule_line.append(
                muted_text(
                    tr(
                        "debt.next_payment",
                        language,
                        date=format_date(debt.next_payment_date),
                    )
                    + amt,
                    page=page,
                )
            )
        eta_line: list[ft.Control] = []
        if projected_payoff_date is not None:
            eta_line.append(
                muted_text(
                    f"{tr('debt.projected_date', language)}: "
                    f"{format_date(projected_payoff_date)}",
                    page=page,
                )
            )

        body = ft.Column(
            spacing=metrics["gap"],
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=4,
                    controls=[
                        account_icon_badge(
                            icon_key,
                            color=icon_color,
                            size=metrics["icon"],
                            glyph_size=metrics["glyph"],
                        ),
                        adaptive_text(
                            debt.counterparty,
                            page=page,
                            size=16,
                            weight=ft.FontWeight.W_700,
                            expand=True,
                            max_lines=2,
                            minimum=13,
                            maximum=20,
                        ),
                        ft.Row(tight=True, spacing=0, controls=actions_row),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=999,
                    bgcolor=ft.Colors.ERROR_CONTAINER
                    if i_owe
                    else ft.Colors.SECONDARY_CONTAINER,
                    content=ft.Text(
                        (
                            tr("debt.i_owe", language)
                            if i_owe
                            else tr("debt.owed_to_me", language)
                        )
                        + " · "
                        + tr(f"debt.status.{status_value}", language),
                        size=metrics["chip"],
                        weight=ft.FontWeight.W_600,
                        color=status_color,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        max_lines=1,
                    ),
                ),
                money_label(
                    debt.remaining_amount,
                    debt.currency,
                    page=page,
                    size=18,
                    color=accent,
                ),
                muted_text(
                    f"{format_money_compact(debt.amount - min(debt.remaining_amount, debt.amount), debt.currency)}"
                    f" / {format_money_compact(debt.amount, debt.currency)}"
                    f" · {pct}%",
                    page=page,
                ),
                ft.ProgressBar(
                    value=ratio,
                    color=get_active_skin().primary_hex(dark=True),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    bar_height=6,
                    border_radius=999,
                ),
                muted_text(due_line, page=page),
                *schedule_line,
                *eta_line,
                *interest_line,
                sparkline if sparkline is not None else ft.Container(height=0),
            ],
        )
        card = card_surface(
            body,
            padding=metrics["padding"],
            ink=True,
            on_click=lambda _e: on_click(debt)
            if on_click
            else (on_edit(debt) if on_edit else None),
        )
        super().__init__(
            padding=card.padding,
            border_radius=card.border_radius,
            bgcolor=card.bgcolor,
            border=card.border,
            shadow=card.shadow,
            ink=True,
            on_click=card.on_click,
            animate=card.animate,
            content=body,
        )
