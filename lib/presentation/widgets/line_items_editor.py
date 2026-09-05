"""Reusable multi-line amount editor for income/expense forms."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

import flet as ft

from lib.domain.entities.transaction import TransactionItem
from lib.presentation.money_input import make_amount_field, parse_amount
from lib.presentation.utils import safe_update, tr


class LineItemsEditor(ft.Column):
    """Name + amount rows that sum into one transaction total."""

    def __init__(
        self,
        lang: str,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        self._lang = lang
        self._on_changed = on_changed
        self._rows: list[tuple[ft.TextField, ft.TextField, ft.IconButton]] = []
        self._list = ft.Column(spacing=8, tight=True, controls=[])
        self._total = ft.Text(
            "",
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self._enabled = False
        self._toggle = ft.Switch(
            label=tr("tx.multi_items", lang),
            value=False,
            on_change=self._on_toggle,
        )
        self._add_btn = ft.TextButton(
            tr("tx.add_item", lang),
            icon=ft.Icons.ADD,
            on_click=lambda _e: self._add_row(),
            visible=False,
        )
        super().__init__(
            spacing=8,
            tight=True,
            controls=[self._toggle, self._list, self._add_btn, self._total],
        )

    def set_on_changed(self, callback: Callable[[], None] | None) -> None:
        """Register a callback invoked when rows or multi-mode toggle change."""
        self._on_changed = callback

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _on_toggle(self, _e: ft.ControlEvent) -> None:
        self._enabled = bool(self._toggle.value)
        self._list.visible = self._enabled
        self._add_btn.visible = self._enabled
        self._total.visible = self._enabled
        if self._enabled and not self._rows:
            self._add_row()
            self._add_row()
        self._refresh_total()
        safe_update(self)
        if self._on_changed:
            self._on_changed()

    def _add_row(
        self,
        *,
        name: str = "",
        amount: str = "",
    ) -> None:
        name_tf = ft.TextField(
            label=tr("tx.item_name", self._lang),
            value=name,
            expand=3,
            dense=True,
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(name_tf, "text")
        amount_tf = make_amount_field(
            self._lang,
            label=tr("field.amount", self._lang),
            expand=2,
            value=amount or None,
            extra_on_change=lambda _e: self._refresh_total(),
            dense=True,
        )
        name_tf.on_change = lambda _e: self._refresh_total()
        remove = ft.IconButton(
            icon=ft.Icons.CLOSE,
            tooltip=tr("action.delete", self._lang),
            on_click=lambda _e, row_id=len(self._rows): self._remove_at(row_id),
            style=ft.ButtonStyle(padding=ft.Padding.all(8)),
        )
        # Capture by object identity instead of stale index.
        remove.on_click = lambda _e, n=name_tf: self._remove_field(n)
        wire_field_chain(getattr(self, "page", None), [name_tf, amount_tf])
        row = ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[name_tf, amount_tf, remove],
        )
        self._rows.append((name_tf, amount_tf, remove))
        self._list.controls.append(row)
        self._refresh_total()
        safe_update(self._list)

    def _remove_field(self, name_tf: ft.TextField) -> None:
        for idx, (n, _a, _r) in enumerate(self._rows):
            if n is name_tf:
                self._remove_at(idx)
                return

    def _remove_at(self, index: int) -> None:
        if index < 0 or index >= len(self._rows):
            return
        if len(self._rows) <= 1:
            return
        self._rows.pop(index)
        self._list.controls.pop(index)
        self._refresh_total()
        safe_update(self._list)

    def _refresh_total(self) -> None:
        total = Decimal("0")
        for _name, amount_tf, _rm in self._rows:
            try:
                total += parse_amount(amount_tf.value)
            except (InvalidOperation, ValueError):
                continue
        self._total.value = tr(
            "tx.items_total",
            self._lang,
            amount=f"{total:,.2f}".replace(",", " "),
        )
        safe_update(self._total)
        if self._on_changed:
            self._on_changed()

    def collect(self, *, default_category: str) -> list[TransactionItem] | None:
        """Return items when multi-mode is on; ``None`` means use single amount field."""
        if not self._enabled:
            return None
        items: list[TransactionItem] = []
        for name_tf, amount_tf, _rm in self._rows:
            raw_name = (name_tf.value or "").strip()
            try:
                amount = parse_amount(amount_tf.value)
            except (InvalidOperation, ValueError):
                continue
            if amount <= 0:
                continue
            items.append(
                TransactionItem(
                    name=raw_name or default_category,
                    amount=amount,
                    category=default_category,
                )
            )
        return items

    def set_items(self, items: list[TransactionItem]) -> None:
        """Prefill editor from an existing multi-line transaction."""
        self._toggle.value = True
        self._enabled = True
        self._list.visible = True
        self._add_btn.visible = True
        self._total.visible = True
        self._rows.clear()
        self._list.controls.clear()
        if not items:
            self._add_row()
            self._add_row()
        else:
            for item in items:
                self._add_row(
                    name=item.name,
                    amount=str(item.amount),
                )
        self._refresh_total()
