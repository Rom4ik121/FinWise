"""Preset monthly budget templates (seed category names)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import flet as ft

from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.account_icons import account_icon_badge


@dataclass(frozen=True)
class BudgetTemplate:
    id: str
    category: str
    icon: str
    color: str
    default_amount: str


BUDGET_TEMPLATES: tuple[BudgetTemplate, ...] = (
    BudgetTemplate("food", "Еда", "restaurant", "#EF6C00", "15000"),
    BudgetTemplate("transport", "Транспорт", "directions_car", "#1565C0", "8000"),
    BudgetTemplate("housing", "Жильё", "home", "#5D4037", "25000"),
    BudgetTemplate("utilities", "Коммунальные", "electrical_services", "#00838F", "6000"),
    BudgetTemplate("health", "Здоровье", "local_hospital", "#C62828", "5000"),
    BudgetTemplate("entertainment", "Развлечения", "movie", "#6A1B9A", "4000"),
    BudgetTemplate("clothes", "Одежда", "checkroom", "#AD1457", "4000"),
    BudgetTemplate("education", "Образование", "school", "#283593", "3000"),
)


def budget_template_chip(
    template: BudgetTemplate,
    *,
    language: str,
    on_click,
) -> ft.Control:
    label = localize_category_name(template.category, language)
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
                    glyph_color="#FFFFFF",
                ),
                ft.Text(label, size=12, weight=ft.FontWeight.W_600, no_wrap=True),
            ],
        ),
    )


def template_amount(template: BudgetTemplate) -> Decimal:
    return Decimal(template.default_amount)
