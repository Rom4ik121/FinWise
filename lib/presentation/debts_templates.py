"""Preset debt templates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import flet as ft

from lib.domain.entities.debt import DebtDirection
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.utils import tr


@dataclass(frozen=True)
class DebtTemplate:
    id: str
    name_key: str
    icon: str
    color: str
    direction: DebtDirection = DebtDirection.I_OWE
    default_amount: str | None = None
    interest_rate: str | None = None
    accrue_interest: bool = False
    next_payment_amount: str | None = None
    payment_interval_months: int = 1


DEBT_TEMPLATES: tuple[DebtTemplate, ...] = (
    DebtTemplate(
        id="bank_loan",
        name_key="debt.template.bank_loan",
        icon="account_balance",
        color="#60A5FA",
        default_amount="500000",
        interest_rate="18",
    ),
    DebtTemplate(
        id="credit_card",
        name_key="debt.template.credit_card",
        icon="credit_card",
        color="#F87171",
        default_amount="100000",
        interest_rate="24",
        accrue_interest=True,
    ),
    DebtTemplate(
        id="mortgage",
        name_key="debt.template.mortgage",
        icon="home",
        color="#34D399",
        default_amount="50000000",
        interest_rate="12",
        next_payment_amount="2500000",
        payment_interval_months=1,
    ),
    DebtTemplate(
        id="installment",
        name_key="debt.template.installment",
        icon="shopping_bag",
        color="#A78BFA",
        default_amount="3000000",
        interest_rate="0",
        next_payment_amount="500000",
    ),
    DebtTemplate(
        id="friend_loan",
        name_key="debt.template.friend_loan",
        icon="person",
        color="#FBBF24",
        default_amount="50000",
        direction=DebtDirection.I_OWE,
    ),
    DebtTemplate(
        id="lent",
        name_key="debt.template.lent",
        icon="handshake",
        color="#2DD4BF",
        default_amount="100000",
        direction=DebtDirection.OWED_TO_ME,
    ),
    DebtTemplate(
        id="microloan",
        name_key="debt.template.microloan",
        icon="payments",
        color="#FB7185",
        default_amount="2000000",
        interest_rate="36",
        next_payment_amount="400000",
    ),
)


def debt_template_chip(
    template: DebtTemplate,
    *,
    language: str,
    on_click,
) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        ink=True,
        on_click=lambda _e: on_click(template),
        content=ft.Row(
            spacing=8,
            tight=True,
            controls=[
                account_icon_badge(
                    template.icon,
                    color=template.color,
                    size=32,
                    glyph_size=16,
                ),
                ft.Text(
                    tr(template.name_key, language),
                    size=12,
                    weight=ft.FontWeight.W_600,
                    no_wrap=True,
                ),
            ],
        ),
    )
