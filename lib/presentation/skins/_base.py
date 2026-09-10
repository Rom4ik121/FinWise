"""Shared UI skin contract used by every visual style file."""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class UiSkin:
    """Palette + layout tokens for one application look.

    Light and dark palettes both exist so the same skin stays readable on
    phone, tablet, and desktop, including system light/dark.
    """

    id: str
    dark_bg: str
    dark_surface: str
    dark_surface_2: str
    dark_surface_3: str
    dark_border: str
    dark_text: str
    dark_muted: str
    dark_primary: str
    dark_primary_dim: str
    dark_on_primary: str
    dark_primary_container: str
    dark_on_primary_container: str
    dark_income: str
    dark_expense: str
    dark_warn: str
    light_bg: str
    light_surface: str
    light_surface_2: str
    light_surface_3: str
    light_border: str
    light_text: str
    light_muted: str
    light_primary: str
    light_primary_dim: str
    light_on_primary: str
    light_primary_container: str
    light_on_primary_container: str
    light_income: str
    light_expense: str
    light_warn: str
    card_radius: int = 18
    chip_radius: int = 14
    hero_radius: int = 22
    glow: str = "#00000022"
    card_blur: int = 18
    seed: str = "#2DD4BF"
    chart_kind: str = "bars"
    accent_fill: str = "container"
    glass: bool = False
    page_gradient_dark: tuple[str, ...] = ()
    page_gradient_light: tuple[str, ...] = ()
    chart_colors: tuple[str, ...] = (
        "#2DD4BF",
        "#38BDF8",
        "#4ADE80",
        "#FBBF24",
        "#F87171",
        "#A78BFA",
        "#FB7185",
        "#34D399",
    )

    def dark_color_scheme(self) -> ft.ColorScheme:
        return ft.ColorScheme(
            primary=self.dark_primary,
            on_primary=self.dark_on_primary,
            primary_container=self.dark_primary_container,
            on_primary_container=self.dark_on_primary_container,
            secondary=self.dark_primary_dim,
            on_secondary=self.dark_on_primary,
            secondary_container=self.dark_surface_2,
            on_secondary_container=self.dark_text,
            tertiary=self.dark_income,
            on_tertiary=self.dark_on_primary,
            tertiary_container=self.dark_surface_3,
            on_tertiary_container=self.dark_text,
            surface=self.dark_bg,
            on_surface=self.dark_text,
            surface_container_lowest=self.dark_bg,
            surface_container_low=self.dark_surface,
            surface_container=self.dark_surface,
            surface_container_high=self.dark_surface_2,
            surface_container_highest=self.dark_surface_3,
            on_surface_variant=self.dark_muted,
            outline=self.dark_border,
            outline_variant=self.dark_border,
            error=self.dark_expense,
            on_error=self.dark_on_primary,
            error_container="#7F1D1D",
            on_error_container="#FECACA",
            inverse_surface=self.light_surface,
            on_inverse_surface=self.light_text,
            inverse_primary=self.light_primary,
            shadow=self.glow,
            scrim="#00000099",
        )

    def light_color_scheme(self) -> ft.ColorScheme:
        return ft.ColorScheme(
            primary=self.light_primary,
            on_primary=self.light_on_primary,
            primary_container=self.light_primary_container,
            on_primary_container=self.light_on_primary_container,
            secondary=self.light_primary_dim,
            on_secondary=self.light_on_primary,
            secondary_container=self.light_surface_2,
            on_secondary_container=self.light_text,
            tertiary=self.light_income,
            on_tertiary=self.light_on_primary,
            tertiary_container=self.light_surface_3,
            on_tertiary_container=self.light_text,
            surface=self.light_bg,
            on_surface=self.light_text,
            surface_container_lowest=self.light_surface,
            surface_container_low=self.light_surface_2,
            surface_container=self.light_surface,
            surface_container_high=self.light_surface_2,
            surface_container_highest=self.light_surface_3,
            on_surface_variant=self.light_muted,
            outline=self.light_border,
            outline_variant=self.light_border,
            error=self.light_expense,
            on_error="#FFFFFF",
            error_container="#FEE2E2",
            on_error_container="#7F1D1D",
            inverse_surface=self.dark_surface,
            on_inverse_surface=self.dark_text,
            inverse_primary=self.dark_primary,
            shadow="#0F172A33",
            scrim="#0F172A66",
        )

    def color_scheme(self, *, dark: bool) -> ft.ColorScheme:
        return self.dark_color_scheme() if dark else self.light_color_scheme()

    def page_gradient(self, *, dark: bool) -> ft.LinearGradient:
        stops = self.page_gradient_dark if dark else self.page_gradient_light
        if len(stops) >= 2:
            colors = list(stops)
        elif dark:
            colors = [self.dark_bg, self.dark_surface, self.dark_bg]
        else:
            colors = [self.light_bg, self.light_primary_container, self.light_bg]
        return ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=colors,
        )

    def backdrop_blur(self) -> ft.Blur | None:
        if not self.glass:
            return None
        sigma = min(10, max(8, self.card_blur // 2))
        return ft.Blur(sigma, sigma, ft.BlurTileMode.CLAMP)

    def glass_fill(self, token: str, *, opacity: float | None = None) -> str:
        if not self.glass:
            return token
        return ft.Colors.with_opacity(0.38 if opacity is None else opacity, token)

    def income_hex(self, *, dark: bool) -> str:
        return self.dark_income if dark else self.light_income

    def expense_hex(self, *, dark: bool) -> str:
        return self.dark_expense if dark else self.light_expense

    def text_hex(self, *, dark: bool) -> str:
        return self.dark_text if dark else self.light_text

    def muted_hex(self, *, dark: bool) -> str:
        return self.dark_muted if dark else self.light_muted

    def warn_hex(self, *, dark: bool) -> str:
        return self.dark_warn if dark else self.light_warn

    def primary_hex(self, *, dark: bool) -> str:
        return self.dark_primary if dark else self.light_primary

    def on_primary_hex(self, *, dark: bool) -> str:
        return self.dark_on_primary if dark else self.light_on_primary

    def _solid_accent(self) -> bool:
        return self.accent_fill == "solid"

    def badge_bg(self, *, dark: bool) -> str:
        if self._solid_accent():
            return self.primary_hex(dark=dark)
        return self.dark_primary_container if dark else self.light_primary_container

    def badge_fg(self, *, dark: bool) -> str:
        if self._solid_accent():
            return self.on_primary_hex(dark=dark)
        return (
            self.dark_on_primary_container if dark else self.light_on_primary_container
        )

    def nav_selected_bg(self, *, dark: bool) -> str:
        return self.badge_bg(dark=dark)

    def nav_selected_fg(self, *, dark: bool) -> str:
        return self.badge_fg(dark=dark)

    def action_income_bg(self, *, dark: bool) -> str:
        if self._solid_accent():
            return self.income_hex(dark=dark)
        return self.dark_primary_container if dark else self.light_primary_container

    def action_income_fg(self, *, dark: bool) -> str:
        if self._solid_accent():
            return self.on_primary_hex(dark=dark)
        return (
            self.dark_on_primary_container if dark else self.light_on_primary_container
        )

    def action_expense_bg(self, *, dark: bool) -> str:
        if self._solid_accent():
            return self.expense_hex(dark=dark)
        return "#7F1D1D" if dark else "#FEE2E2"

    def action_expense_fg(self, *, dark: bool) -> str:
        if self._solid_accent():
            return "#FFFFFF"
        return "#FECACA" if dark else "#7F1D1D"

    def hero_gradient(self, *, dark: bool) -> ft.LinearGradient:
        if self._solid_accent():
            start = self.dark_surface if dark else self.light_surface
            end = self.dark_surface_2 if dark else self.light_primary_container
        else:
            start = (
                self.dark_primary_container if dark else self.light_primary_container
            )
            end = self.dark_surface_2 if dark else self.light_surface_2
        return ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[start, end],
        )
