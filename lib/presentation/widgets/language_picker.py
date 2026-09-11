"""Fullscreen language picker — endonyms, English first, no dropdown clipping."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.infrastructure.services.localization import (
    LANG_LABELS,
    language_picker_choices,
    normalize_lang,
)
from lib.presentation.responsive import MIN_TAP
from lib.presentation.utils import safe_update, tr
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form


class LanguagePicker(ft.Container):
    """Field that opens a scrollable list of all live UI languages."""

    def __init__(
        self,
        page: ft.Page,
        *,
        lang: str,
        label: str,
        value: str,
        on_changed: Optional[Callable[[str], None]] = None,
        expand: bool = True,
    ) -> None:
        self._page = page
        self._lang = lang
        self._on_changed = on_changed
        self._value = normalize_lang(value)
        self._overlay_key = f"language_picker_{id(self)}"

        self._display = ft.Text(
            LANG_LABELS.get(self._value, LANG_LABELS["en"]),
            size=14,
            weight=ft.FontWeight.W_600,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
            expand=True,
        )
        self._caption = ft.Text(
            label,
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        super().__init__(
            expand=expand,
            border_radius=14,
            bgcolor=ft.Colors.SURFACE,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            ink=True,
            on_click=lambda _e: self.open(),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[self._caption, self._display],
                    ),
                    ft.Icon(
                        ft.Icons.LANGUAGE,
                        size=18,
                        color=ft.Colors.PRIMARY,
                    ),
                ],
            ),
        )

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, code: str) -> None:
        self.set_value(code, notify=False)

    def set_value(self, code: str, *, notify: bool = True) -> None:
        self._value = normalize_lang(code)
        self._display.value = LANG_LABELS.get(self._value, LANG_LABELS["en"])
        try:
            safe_update(self._display)
        except Exception:  # noqa: BLE001
            pass
        if notify and self._on_changed is not None:
            self._on_changed(self._value)

    def open(self) -> None:
        """Show every supported language as an endonym row (English first)."""
        close_holder: dict[str, Callable[[], None]] = {}
        rows: list[ft.Control] = []
        for code, endonym in language_picker_choices():
            selected = code == self._value
            rows.append(
                ft.Container(
                    ink=True,
                    border_radius=12,
                    bgcolor=(
                        ft.Colors.PRIMARY_CONTAINER if selected else ft.Colors.SURFACE
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=12),
                    height=max(MIN_TAP + 4, 48),
                    on_click=lambda _e, c=code: self._pick(c, close_holder),
                    content=ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                endonym,
                                size=16,
                                weight=(
                                    ft.FontWeight.W_700
                                    if selected
                                    else ft.FontWeight.W_500
                                ),
                                expand=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Icon(
                                ft.Icons.CHECK,
                                size=20,
                                color=ft.Colors.PRIMARY,
                                visible=selected,
                            ),
                        ],
                    ),
                )
            )
        close = open_fullscreen_form(
            self._page,
            title=tr("settings.language", self._lang),
            lang=self._lang,
            overlay_key=self._overlay_key,
            body=rows,
            show_save=False,
        )
        close_holder["close"] = close

    def _pick(
        self,
        code: str,
        close_holder: dict[str, Callable[[], None]],
    ) -> None:
        closer = close_holder.get("close")
        if callable(closer):
            closer()
        self.set_value(code, notify=True)
