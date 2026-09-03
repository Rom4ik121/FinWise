"""Preset subscription templates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import flet as ft

from lib.domain.entities.subscription import Periodicity
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.utils import tr


@dataclass(frozen=True)
class SubscriptionTemplate:
    id: str
    name_key: str
    icon: str
    color: str
    category: str
    default_amount: str
    periodicity: Periodicity = Periodicity.MONTHLY


SUBSCRIPTION_TEMPLATES: tuple[SubscriptionTemplate, ...] = (
    SubscriptionTemplate(
        id="netflix",
        name_key="subscription.template.netflix",
        icon="movie",
        color="#F87171",
        category="Развлечения",
        default_amount="799",
    ),
    SubscriptionTemplate(
        id="spotify",
        name_key="subscription.template.spotify",
        icon="music_note",
        color="#4ADE80",
        category="Развлечения",
        default_amount="399",
    ),
    SubscriptionTemplate(
        id="youtube",
        name_key="subscription.template.youtube",
        icon="live_tv",
        color="#FB7185",
        category="Развлечения",
        default_amount="299",
    ),
    SubscriptionTemplate(
        id="cloud",
        name_key="subscription.template.cloud",
        icon="cloud",
        color="#60A5FA",
        category="Прочее",
        default_amount="199",
    ),
    SubscriptionTemplate(
        id="gym",
        name_key="subscription.template.gym",
        icon="sports",
        color="#FBBF24",
        category="Здоровье",
        default_amount="3500",
    ),
    SubscriptionTemplate(
        id="mobile",
        name_key="subscription.template.mobile",
        icon="smartphone",
        color="#A78BFA",
        category="Коммунальные",
        default_amount="500",
    ),
    SubscriptionTemplate(
        id="internet",
        name_key="subscription.template.internet",
        icon="wifi",
        color="#2DD4BF",
        category="Коммунальные",
        default_amount="800",
    ),
    SubscriptionTemplate(
        id="insurance",
        name_key="subscription.template.insurance",
        icon="security",
        color="#38BDF8",
        category="Здоровье",
        default_amount="2500",
        periodicity=Periodicity.YEARLY,
    ),
    SubscriptionTemplate(
        id="rent",
        name_key="subscription.template.rent",
        icon="home",
        color="#F59E0B",
        category="Жильё",
        default_amount="25000",
    ),
    SubscriptionTemplate(
        id="custom",
        name_key="subscription.template.custom",
        icon="autorenew",
        color="#A78BFA",
        category="Прочее",
        default_amount="500",
    ),
)


def subscription_template_chip(
    template: SubscriptionTemplate,
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


def template_amount(template: SubscriptionTemplate) -> Decimal:
    return Decimal(template.default_amount)
