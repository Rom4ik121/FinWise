"""Editor for goal sub-positions (name + target amount)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable
from uuid import uuid4

import flet as ft

from lib.domain.entities.goal import GoalItem
from lib.presentation.money_input import amount_text, make_amount_field, parse_amount
from lib.presentation.styles import labeled_field, labeled_switch, polish_form_control
from lib.presentation.utils import safe_update, tr


class GoalItemsEditor(ft.Column):
    """Rows of name + target that sum into the goal target."""

    def __init__(
        self,
        lang: str,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        self._lang = lang
        self._on_changed = on_changed
        self._rows: list[tuple[str, ft.TextField, ft.TextField, ft.IconButton]] = []
        self._row_cards: dict[str, ft.Container] = {}
        self._name_errors: dict[str, ft.Text] = {}
        self._amount_errors: dict[str, ft.Text] = {}
        self._invalid_rows: set[str] = set()
        self._list = ft.Column(spacing=10, tight=True, controls=[])
        self._total = ft.Text(
            "",
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.PRIMARY,
        )
        self._enabled = False
        self._toggle = ft.Switch(value=False, on_change=self._on_toggle)
        self._toggle_row = labeled_switch(tr("goal.multi_items", lang), self._toggle)
        self._add_btn = ft.FilledTonalButton(
            tr("goal.add_item", lang),
            icon=ft.Icons.ADD,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            ),
            on_click=lambda _e: self._add_row(),
        )
        self._body = ft.Column(
            spacing=10,
            tight=True,
            visible=False,
            controls=[self._list, self._total, self._add_btn],
        )
        super().__init__(
            spacing=10,
            tight=True,
            controls=[self._toggle_row, self._body],
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def load_items(self, items: list[GoalItem]) -> None:
        """Populate editor from existing goal items."""
        self._clear_rows()
        if items:
            self._toggle.value = True
            self._enabled = True
            self._body.visible = True
            for item in sorted(items, key=lambda i: i.sort_order):
                self._add_row(
                    name=item.name,
                    amount=str(item.target_amount),
                    row_id=item.id,
                    update=False,
                )
        else:
            self._toggle.value = False
            self._enabled = False
            self._body.visible = False
        self._refresh_total()
        safe_update(self)

    def _on_toggle(self, _e: ft.ControlEvent) -> None:
        self._enabled = bool(self._toggle.value)
        self._body.visible = self._enabled
        if self._enabled and not self._rows:
            self._add_row(update=False)
        if not self._enabled:
            self._clear_rows()
        self._refresh_total()
        safe_update(self._body)
        safe_update(self._list)
        safe_update(self)
        self._notify_changed()

    def _clear_rows(self) -> None:
        self._rows.clear()
        self._list.controls.clear()
        self._row_cards.clear()
        self._name_errors.clear()
        self._amount_errors.clear()
        self._invalid_rows.clear()

    def _notify_changed(self) -> None:
        if self._on_changed:
            self._on_changed()

    def _set_row_invalid(self, row_id: str, *, invalid: bool) -> None:
        card = self._row_cards.get(row_id)
        if card is None:
            return
        if invalid:
            self._invalid_rows.add(row_id)
            card.border = ft.Border.all(2, ft.Colors.ERROR)
        else:
            self._invalid_rows.discard(row_id)
            card.border = ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
        try:
            safe_update(card)
        except Exception:  # noqa: BLE001
            pass

    def _make_row_card(
        self,
        *,
        row_id: str,
        index: int,
        name_tf: ft.TextField,
        amount_tf: ft.TextField,
        remove: ft.IconButton,
    ) -> ft.Container:
        row_title = tr("goal.item_row", self._lang, n=str(index + 1))
        name_err = ft.Text("", size=11, color=ft.Colors.ERROR, visible=False)
        amount_err = ft.Text("", size=11, color=ft.Colors.ERROR, visible=False)
        self._name_errors[row_id] = name_err
        self._amount_errors[row_id] = amount_err
        card = ft.Container(
            padding=12,
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Column(
                spacing=10,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                row_title,
                                size=12,
                                weight=ft.FontWeight.W_700,
                                expand=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            remove,
                        ],
                    ),
                    labeled_field(tr("goal.item_name", self._lang), name_tf),
                    name_err,
                    labeled_field(tr("goal.item_target", self._lang), amount_tf),
                    amount_err,
                ],
            ),
        )
        self._row_cards[row_id] = card
        return card

    def _add_row(
        self,
        *,
        name: str = "",
        amount: str = "",
        row_id: str | None = None,
        update: bool = True,
    ) -> None:
        item_id = row_id or str(uuid4())
        name_tf = ft.TextField(value=name, expand=True, dense=True)
        amount_tf = make_amount_field(
            self._lang,
            label="",
            expand=True,
            value=amount or None,
            extra_on_change=lambda _e: self._refresh_total(),
            dense=True,
        )
        polish_form_control(name_tf)
        polish_form_control(amount_tf)
        name_tf.on_change = lambda _e, rid=item_id: self._on_row_change(rid)
        amount_tf.on_change = lambda _e, rid=item_id: self._on_row_change(rid)
        remove = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=ft.Colors.ERROR,
            tooltip=tr("action.delete", self._lang),
            style=ft.ButtonStyle(
                padding=ft.Padding.all(8),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=lambda _e, rid=item_id: self._remove_row(rid),
        )
        index = len(self._rows)
        self._rows.append((item_id, name_tf, amount_tf, remove))
        self._list.controls.append(
            self._make_row_card(
                row_id=item_id,
                index=index,
                name_tf=name_tf,
                amount_tf=amount_tf,
                remove=remove,
            )
        )
        self._refresh_total()
        if update:
            safe_update(self)
            self._notify_changed()

    def _on_row_change(self, row_id: str) -> None:
        self._refresh_total()
        if row_id in self._invalid_rows:
            self._clear_row_errors(row_id)
            self._set_row_invalid(row_id, invalid=False)

    def _clear_row_errors(self, row_id: str) -> None:
        for err in (self._name_errors.get(row_id), self._amount_errors.get(row_id)):
            if err is not None:
                err.value = ""
                err.visible = False
                try:
                    safe_update(err)
                except Exception:  # noqa: BLE001
                    pass

    def _remove_row(self, row_id: str) -> None:
        idx = next((i for i, row in enumerate(self._rows) if row[0] == row_id), None)
        if idx is None:
            return
        self._rows.pop(idx)
        self._list.controls.pop(idx)
        self._row_cards.pop(row_id, None)
        self._name_errors.pop(row_id, None)
        self._amount_errors.pop(row_id, None)
        self._invalid_rows.discard(row_id)
        self._rebuild_row_titles()
        self._refresh_total()
        safe_update(self)
        self._notify_changed()

    def _rebuild_row_titles(self) -> None:
        """Refresh row headers after insert/remove."""
        for idx, card in enumerate(self._list.controls):
            if not isinstance(card, ft.Container):
                continue
            col = card.content
            if not isinstance(col, ft.Column) or not col.controls:
                continue
            header = col.controls[0]
            if not isinstance(header, ft.Row) or not header.controls:
                continue
            title = header.controls[0]
            if isinstance(title, ft.Text):
                title.value = tr("goal.item_row", self._lang, n=str(idx + 1))

    def _refresh_total(self) -> None:
        if not self._enabled:
            self._total.value = ""
            return
        total = Decimal("0")
        for _, _, amount_tf, _ in self._rows:
            try:
                total += parse_amount(amount_text(amount_tf))
            except (InvalidOperation, ValueError):
                continue
        count = len(self._rows)
        self._total.value = tr(
            "goal.items_total_count",
            self._lang,
            amount=str(total),
            count=str(count),
        )
        safe_update(self._total)

    def build_items(self) -> list[GoalItem]:
        """Parse rows into goal items (empty when disabled)."""
        if not self._enabled:
            return []
        items: list[GoalItem] = []
        for idx, (item_id, name_tf, amount_tf, _) in enumerate(self._rows):
            name = (name_tf.value or "").strip()
            if not name:
                continue
            try:
                target = parse_amount(amount_text(amount_tf))
            except (InvalidOperation, ValueError):
                continue
            if target <= 0:
                continue
            items.append(
                GoalItem(
                    id=item_id,
                    name=name,
                    target_amount=target,
                    sort_order=idx,
                )
            )
        return items

    def validate(self) -> list[str]:
        """Return validation errors; highlight invalid rows."""
        errors: list[str] = []
        if not self._enabled:
            return errors

        for row_id, name_tf, amount_tf, _ in self._rows:
            self._clear_row_errors(row_id)
            self._set_row_invalid(row_id, invalid=False)
            name = (name_tf.value or "").strip()
            row_invalid = False
            if not name:
                msg = tr("goal.item_name_required", self._lang)
                errors.append(msg)
                row_invalid = True
                err = self._name_errors.get(row_id)
                if err is not None:
                    err.value = msg
                    err.visible = True
                    safe_update(err)
            try:
                target = parse_amount(amount_text(amount_tf))
                if target <= 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                msg = tr("goal.item_amount_invalid", self._lang)
                errors.append(msg)
                row_invalid = True
                err = self._amount_errors.get(row_id)
                if err is not None:
                    err.value = msg
                    err.visible = True
                    safe_update(err)
            if row_invalid:
                self._set_row_invalid(row_id, invalid=True)

        if not errors and not self.build_items():
            errors.append(tr("goal.items_required", self._lang))
        return errors
