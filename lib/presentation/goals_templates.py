"""Preset goal templates with typical sub-items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from lib.presentation.account_icons import account_icon_badge
from lib.presentation.utils import tr


@dataclass(frozen=True)
class GoalTemplateItem:
    name_key: str
    default_amount: str


@dataclass(frozen=True)
class GoalTemplate:
    id: str
    name_key: str
    icon: str
    color: str
    items: tuple[GoalTemplateItem, ...] = ()
    default_amount: str | None = None


GOAL_TEMPLATES: tuple[GoalTemplate, ...] = (
    GoalTemplate(
        id="vacation",
        name_key="goal.template.vacation",
        icon="flight",
        color="#38BDF8",
        items=(
            GoalTemplateItem("goal.template.vacation.tickets", "1500000"),
            GoalTemplateItem("goal.template.vacation.hotel", "2000000"),
            GoalTemplateItem("goal.template.vacation.spending", "1000000"),
        ),
    ),
    GoalTemplate(
        id="cushion",
        name_key="goal.template.cushion",
        icon="savings",
        color="#4ADE80",
        default_amount="2000000",
    ),
    GoalTemplate(
        id="tech",
        name_key="goal.template.tech",
        icon="devices",
        color="#A78BFA",
        items=(
            GoalTemplateItem("goal.template.tech.device", "8000000"),
            GoalTemplateItem("goal.template.tech.accessories", "1500000"),
        ),
    ),
    GoalTemplate(
        id="car",
        name_key="goal.template.car",
        icon="directions_car",
        color="#60A5FA",
        items=(
            GoalTemplateItem("goal.template.car.down", "50000000"),
            GoalTemplateItem("goal.template.car.insurance", "2000000"),
            GoalTemplateItem("goal.template.car.registration", "1000000"),
        ),
    ),
    GoalTemplate(
        id="home",
        name_key="goal.template.home",
        icon="home",
        color="#F59E0B",
        items=(
            GoalTemplateItem("goal.template.home.down", "100000000"),
            GoalTemplateItem("goal.template.home.renovation", "30000000"),
            GoalTemplateItem("goal.template.home.furniture", "20000000"),
        ),
    ),
    GoalTemplate(
        id="wedding",
        name_key="goal.template.wedding",
        icon="favorite",
        color="#F472B6",
        items=(
            GoalTemplateItem("goal.template.wedding.rings", "5000000"),
            GoalTemplateItem("goal.template.wedding.banquet", "30000000"),
            GoalTemplateItem("goal.template.wedding.outfit", "8000000"),
        ),
    ),
    GoalTemplate(
        id="education",
        name_key="goal.template.education",
        icon="school",
        color="#818CF8",
        items=(
            GoalTemplateItem("goal.template.education.tuition", "12000000"),
            GoalTemplateItem("goal.template.education.books", "2000000"),
            GoalTemplateItem("goal.template.education.laptop", "8000000"),
        ),
    ),
    GoalTemplate(
        id="baby",
        name_key="goal.template.baby",
        icon="child_care",
        color="#FB7185",
        items=(
            GoalTemplateItem("goal.template.baby.crib", "3000000"),
            GoalTemplateItem("goal.template.baby.stroller", "2000000"),
            GoalTemplateItem("goal.template.baby.clothes", "2000000"),
        ),
    ),
    GoalTemplate(
        id="health",
        name_key="goal.template.health",
        icon="local_hospital",
        color="#34D399",
        items=(
            GoalTemplateItem("goal.template.health.treatment", "5000000"),
            GoalTemplateItem("goal.template.health.checkups", "1000000"),
        ),
    ),
    GoalTemplate(
        id="renovation",
        name_key="goal.template.renovation",
        icon="construction",
        color="#FB923C",
        items=(
            GoalTemplateItem("goal.template.renovation.materials", "15000000"),
            GoalTemplateItem("goal.template.renovation.labor", "10000000"),
        ),
    ),
    GoalTemplate(
        id="business",
        name_key="goal.template.business",
        icon="work",
        color="#2DD4BF",
        items=(
            GoalTemplateItem("goal.template.business.equipment", "10000000"),
            GoalTemplateItem("goal.template.business.stock", "15000000"),
            GoalTemplateItem("goal.template.business.marketing", "3000000"),
        ),
    ),
    GoalTemplate(
        id="phone",
        name_key="goal.template.phone",
        icon="phone_android",
        color="#C084FC",
        items=(
            GoalTemplateItem("goal.template.phone.device", "6000000"),
            GoalTemplateItem("goal.template.phone.accessories", "500000"),
        ),
    ),
    GoalTemplate(
        id="sport",
        name_key="goal.template.sport",
        icon="fitness_center",
        color="#22D3EE",
        items=(
            GoalTemplateItem("goal.template.sport.gear", "3000000"),
            GoalTemplateItem("goal.template.sport.membership", "1200000"),
        ),
    ),
    GoalTemplate(
        id="gifts",
        name_key="goal.template.gifts",
        icon="card_giftcard",
        color="#E879F9",
        items=(
            GoalTemplateItem("goal.template.gifts.holidays", "2000000"),
            GoalTemplateItem("goal.template.gifts.birthdays", "1000000"),
        ),
    ),
    GoalTemplate(
        id="emergency",
        name_key="goal.template.emergency",
        icon="emergency",
        color="#F87171",
        default_amount="3000000",
    ),
    GoalTemplate(
        id="investment",
        name_key="goal.template.investment",
        icon="trending_up",
        color="#4ADE80",
        default_amount="5000000",
    ),
    GoalTemplate(
        id="motorcycle",
        name_key="goal.template.motorcycle",
        icon="two_wheeler",
        color="#38BDF8",
        items=(
            GoalTemplateItem("goal.template.motorcycle.bike", "15000000"),
            GoalTemplateItem("goal.template.motorcycle.gear", "2000000"),
            GoalTemplateItem("goal.template.motorcycle.insurance", "1000000"),
        ),
    ),
    GoalTemplate(
        id="pet",
        name_key="goal.template.pet",
        icon="pets",
        color="#FBBF24",
        items=(
            GoalTemplateItem("goal.template.pet.vet", "1000000"),
            GoalTemplateItem("goal.template.pet.supplies", "500000"),
        ),
    ),
    GoalTemplate(
        id="move",
        name_key="goal.template.move",
        icon="local_shipping",
        color="#94A3B8",
        items=(
            GoalTemplateItem("goal.template.move.transport", "3000000"),
            GoalTemplateItem("goal.template.move.deposit", "20000000"),
            GoalTemplateItem("goal.template.move.setup", "2000000"),
        ),
    ),
    GoalTemplate(
        id="laptop",
        name_key="goal.template.laptop",
        icon="computer",
        color="#A78BFA",
        default_amount="10000000",
    ),
    GoalTemplate(
        id="courses",
        name_key="goal.template.courses",
        icon="menu_book",
        color="#6366F1",
        default_amount="2000000",
    ),
    GoalTemplate(
        id="celebration",
        name_key="goal.template.celebration",
        icon="celebration",
        color="#F472B6",
        items=(
            GoalTemplateItem("goal.template.celebration.venue", "5000000"),
            GoalTemplateItem("goal.template.celebration.catering", "3000000"),
            GoalTemplateItem("goal.template.celebration.decor", "1500000"),
        ),
    ),
    GoalTemplate(
        id="furniture",
        name_key="goal.template.furniture",
        icon="chair",
        color="#D97706",
        default_amount="8000000",
    ),
)


def goal_template_chip(
    template: GoalTemplate,
    *,
    lang: str,
    on_click: Callable[[GoalTemplate], None],
) -> ft.Control:
    """Compact chip for horizontal template picker."""
    return ft.Container(
        content=ft.Row(
            tight=True,
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                account_icon_badge(
                    template.icon,
                    color=template.color,
                    size=32,
                    glyph_size=16,
                ),
                ft.Text(
                    tr(template.name_key, lang),
                    size=13,
                    weight=ft.FontWeight.W_600,
                    no_wrap=True,
                ),
            ],
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        ink=True,
        on_click=lambda _e, tmpl=template: on_click(tmpl),
    )
