"""Searchable currency ticker picker (fullscreen overlay with live filter)."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import flet as ft

from lib.domain.entities.currency import Currency
from lib.domain.entities.currency_codes import normalize_currency_code
from lib.presentation.currency_options import (
    _currency_display_name,
    load_currency_catalog,
)
from lib.presentation.ui_motion import bind_press, overlay_enter_style
from lib.presentation.utils import safe_update, tr


def currency_row_matches(row: dict[str, str], query: str) -> bool:
    """Match ticker code, symbol, or localized name."""
    q = query.strip().casefold().replace(" ", "")
    if not q:
        return True
    code = row.get("code", "").casefold()
    name = row.get("name", "").casefold()
    symbol = (row.get("symbol") or "").casefold()
    return q in code or q in name or (bool(symbol) and q in symbol)


def _sort_key(row: dict[str, str], query: str) -> tuple[int, str]:
    q = query.strip().casefold()
    code = row["code"].casefold()
    if q and code == q:
        return (0, row["code"])
    if q and code.startswith(q):
        return (1, row["code"])
    return (2, row["code"])


def _rows_from_currencies(
    currencies: Sequence[Currency] | None,
    *,
    lang: str,
    include_crypto: bool = True,
) -> list[dict[str, str]]:
    if currencies:
        return [
            {
                "code": c.code.upper(),
                "name": c.name,
                "symbol": c.symbol or c.code,
            }
            for c in currencies
            if include_crypto or not c.is_crypto
        ]
    catalog = load_currency_catalog(include_crypto=include_crypto)
    return [
        {
            "code": row["code"],
            "name": _currency_display_name(row, lang),
            "symbol": row.get("symbol") or row["code"],
        }
        for row in catalog
    ]


def _label_for(code: str, rows: Sequence[dict[str, str]]) -> str:
    code = normalize_currency_code(code)
    for row in rows:
        if row["code"] == code:
            return f"{code} — {row['name']}"
    return code


class CurrencyTickerPicker(ft.Container):
    """Field that opens a searchable ticker list when tapped."""

    def __init__(
        self,
        page: ft.Page,
        *,
        lang: str,
        label: str,
        value: str,
        currencies: Sequence[Currency] | None = None,
        on_changed: Optional[Callable[[str], None]] = None,
        expand: bool = True,
        include_crypto: bool = True,
        code_only: bool = False,
    ) -> None:
        self._page = page
        self._lang = lang
        self._label = label
        self._on_changed = on_changed
        self._include_crypto = include_crypto
        self._code_only = code_only
        self._overlay_key = f"currency_ticker_{id(self)}"
        self._rows = _rows_from_currencies(
            currencies, lang=lang, include_crypto=include_crypto
        )
        self._value = normalize_currency_code(value)

        self._display = ft.Text(
            self._display_text(),
            size=16 if code_only else 14,
            weight=ft.FontWeight.W_700 if code_only else ft.FontWeight.W_600,
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
            padding=ft.Padding.symmetric(
                horizontal=10,
                vertical=6 if code_only else 10,
            ),
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
                        ft.Icons.SEARCH,
                        size=18,
                        color=ft.Colors.PRIMARY,
                    ),
                ],
            ),
        )

    def _display_text(self) -> str:
        if self._code_only:
            return self._value
        return _label_for(self._value, self._rows)

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, code: str) -> None:
        self.set_value(code, notify=False)

    def set_currencies(self, currencies: Sequence[Currency]) -> None:
        """Refresh catalog used by the picker dialog."""
        self._rows = _rows_from_currencies(
            currencies, lang=self._lang, include_crypto=self._include_crypto
        )
        self._display.value = self._display_text()
        try:
            safe_update(self._display)
        except Exception:  # noqa: BLE001
            pass

    def set_value(self, code: str, *, notify: bool = True) -> None:
        self._value = normalize_currency_code(code)
        self._display.value = self._display_text()
        try:
            safe_update(self._display)
        except Exception:  # noqa: BLE001
            pass
        if notify and self._on_changed is not None:
            self._on_changed(self._value)

    def close_overlay(self) -> None:
        from lib.presentation.widgets.fullscreen_form import dismiss_fullscreen

        dismiss_fullscreen(self._page, key=self._overlay_key)

    def open(self) -> None:
        """Open searchable ticker picker as a fullscreen overlay."""
        from lib.presentation.responsive import form_shell_inset, wrap_safe_area
        from lib.presentation.skins import get_active_skin
        from lib.presentation.styles import card_surface, form_header_bar, polish_form_control
        from lib.presentation.theme import is_dark_mode
        from lib.presentation.widgets.fullscreen_form import dismiss_fullscreen

        lang = self._lang
        overlay_key = self._overlay_key
        dismiss_fullscreen(self._page, key=overlay_key)

        list_col = ft.ListView(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)
        search = ft.TextField(
            label=tr("currencies.search", lang),
            hint_text=tr("currencies.search_hint", lang),
            prefix_icon=ft.Icons.SEARCH,
            autofocus=True,
            dense=True,
            border_radius=14,
            filled=True,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            capitalization=ft.TextCapitalization.CHARACTERS,
        )
        polish_form_control(search)

        def _close(_e: ft.ControlEvent | None = None) -> None:
            dismiss_fullscreen(self._page, key=overlay_key)

        def _row_tile(row: dict[str, str]) -> ft.Control:
            selected = row["code"] == self._value
            tile = ft.Container(
                border_radius=14,
                bgcolor=(
                    ft.Colors.PRIMARY_CONTAINER
                    if selected
                    else ft.Colors.SURFACE_CONTAINER
                ),
                border=ft.Border.all(
                    1,
                    ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                ink=True,
                on_click=lambda _e, code=row["code"]: _pick(code),
                content=ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=40,
                            height=40,
                            border_radius=20,
                            alignment=ft.Alignment.CENTER,
                            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY),
                            content=ft.Text(
                                row["code"][:4],
                                size=11,
                                weight=ft.FontWeight.W_700,
                                color=ft.Colors.PRIMARY,
                            ),
                        ),
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    row["code"],
                                    weight=ft.FontWeight.W_700,
                                    size=15,
                                ),
                                ft.Text(
                                    row["name"],
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if selected else ft.Icons.CHEVRON_RIGHT,
                            size=18,
                            color=ft.Colors.PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                ),
            )
            bind_press(tile, haptic_kind="selection", page=self._page)
            return tile

        def _fill(query: str = "") -> None:
            rows = [r for r in self._rows if currency_row_matches(r, query)]
            rows.sort(key=lambda r: _sort_key(r, query))

            if not rows:
                list_col.controls = [
                    ft.Container(
                        padding=16,
                        content=ft.Text(
                            tr("currencies.not_found", lang),
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    )
                ]
            else:
                list_col.controls = [_row_tile(row) for row in rows]
            try:
                safe_update(list_col)
            except Exception:  # noqa: BLE001
                pass

        def _pick(code: str) -> None:
            _close()
            self.set_value(code, notify=True)

        def _on_search(_e: ft.ControlEvent) -> None:
            _fill(search.value or "")

        def _on_submit(_e: ft.ControlEvent) -> None:
            query = normalize_currency_code(search.value or "")
            if not query:
                return
            exact = next((r for r in self._rows if r["code"] == query), None)
            if exact is not None:
                _pick(exact["code"])
                return
            filtered = [r for r in self._rows if currency_row_matches(r, search.value or "")]
            filtered.sort(key=lambda r: _sort_key(r, search.value or ""))
            if filtered:
                _pick(filtered[0]["code"])

        search.on_change = _on_search
        search.on_submit = _on_submit
        _fill("")

        skin = get_active_skin()
        dark = is_dark_mode(self._page)
        overlay = ft.Container(
            left=0,
            top=0,
            right=0,
            bottom=0,
            bgcolor=ft.Colors.SURFACE,
            data=overlay_key,
            **overlay_enter_style(self._page),
            content=wrap_safe_area(
                ft.Container(
                    expand=True,
                    gradient=skin.page_gradient(dark=dark),
                    content=ft.Column(
                        expand=True,
                        spacing=0,
                        controls=[
                            form_header_bar(
                                self._label,
                                leading=ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK,
                                    icon_color=ft.Colors.ON_SURFACE,
                                    tooltip=tr("action.cancel", lang),
                                    on_click=_close,
                                ),
                                page=self._page,
                            ),
                            ft.Container(
                                expand=True,
                                padding=ft.Padding.symmetric(
                                    horizontal=form_shell_inset(self._page),
                                    vertical=12,
                                ),
                                content=ft.Column(
                                    expand=True,
                                    spacing=12,
                                    controls=[
                                        card_surface(
                                            ft.Column(
                                                spacing=10,
                                                tight=True,
                                                controls=[search],
                                            ),
                                            padding=14,
                                        ),
                                        ft.Container(expand=True, content=list_col),
                                    ],
                                ),
                            ),
                        ],
                    ),
                ),
            ),
        )
        from lib.presentation.widgets.fullscreen_form import push_overlay

        push_overlay(self._page, overlay)
