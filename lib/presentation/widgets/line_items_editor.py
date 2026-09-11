"""Reusable multi-line amount editor for income/expense forms."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from uuid import uuid4

import flet as ft

from lib.domain.entities.transaction import TransactionItem
from lib.presentation.money_input import amount_text, make_amount_field, parse_amount
from lib.presentation.responsive import tap_icon_button
from lib.presentation.styles import card_surface, style_popup_menu
from lib.presentation.utils import control_page, run_async, safe_update, tr


def merge_line_item_photos(
    paths: list[str],
    items: list[TransactionItem],
) -> list[str]:
    """Keep transaction-level attachments plus per-line photos (no duplicates)."""
    out: list[str] = []
    seen: set[str] = set()
    for rel in list(paths or []) + [
        (item.attachment or "").strip() for item in items
    ]:
        if rel and rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


@dataclass
class _LineRow:
    name: ft.TextField
    amount: ft.TextField
    photo_rel: str = ""
    pending: tuple[str, bytes] | None = None
    photo_btn: ft.Control | None = None
    photo_clear: ft.Control | None = None
    photo_preview: ft.Container | None = None
    card: ft.Control | None = None


class LineItemsEditor(ft.Column):
    """Vertical name / amount cards that sum into one transaction total."""

    def __init__(
        self,
        lang: str,
        *,
        on_changed: Callable[[], None] | None = None,
        page: ft.Page | None = None,
        transaction_id: str | None = None,
    ) -> None:
        self._lang = lang
        self._on_changed = on_changed
        self._page = page
        self._tx_id = transaction_id or str(uuid4())
        self._rows: list[_LineRow] = []
        self._list = ft.Column(spacing=10, tight=True, controls=[])
        self._total = ft.Text(
            "",
            size=13,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.PRIMARY,
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
            spacing=10,
            tight=True,
            controls=[self._toggle, self._list, self._add_btn, self._total],
        )

    def set_on_changed(self, callback: Callable[[], None] | None) -> None:
        """Register a callback invoked when rows or multi-mode toggle change."""
        self._on_changed = callback

    def set_transaction_id(self, tx_id: str) -> None:
        """Bind pending photos to the transaction that will own the files."""
        if tx_id:
            self._tx_id = tx_id

    def _host_page(self) -> ft.Page | None:
        return self._page or control_page(self)

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
        attachment: str = "",
    ) -> None:
        name_tf = ft.TextField(
            label=tr("tx.item_name", self._lang),
            value=name,
            dense=True,
            border_radius=12,
            filled=True,
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(name_tf, "text")
        amount_tf = make_amount_field(
            self._lang,
            label=tr("field.amount", self._lang),
            value=amount or None,
            extra_on_change=lambda _e: self._refresh_total(),
            dense=True,
            border_radius=12,
            filled=True,
        )
        name_tf.on_change = lambda _e: self._refresh_total()
        row = _LineRow(name=name_tf, amount=amount_tf, photo_rel=attachment or "")
        remove = tap_icon_button(
            icon=ft.Icons.CLOSE,
            icon_size=18,
            tooltip=tr("action.delete", self._lang),
            on_click=lambda _e, current=row: self._remove_row(current),
            padding=8,
        )
        photo_preview = ft.Container(
            width=40,
            height=40,
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            alignment=ft.Alignment.CENTER,
            visible=False,
            content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=18),
        )
        photo_btn = style_popup_menu(
            ft.PopupMenuButton(
                icon=ft.Icons.PHOTO_CAMERA_OUTLINED,
                icon_color=ft.Colors.ON_SURFACE_VARIANT,
                icon_size=20,
                tooltip=tr("tx.attach_photo", self._lang),
                padding=12,
                items=[
                    ft.PopupMenuItem(
                        content=ft.Text(tr("tx.photo_gallery", self._lang)),
                        icon=ft.Icons.PHOTO_LIBRARY_OUTLINED,
                        on_click=lambda _e, current=row: self._pick_photo(
                            current, source="gallery"
                        ),
                    ),
                    ft.PopupMenuItem(
                        content=ft.Text(tr("tx.take_photo", self._lang)),
                        icon=ft.Icons.PHOTO_CAMERA_OUTLINED,
                        on_click=lambda _e, current=row: self._pick_photo(
                            current, source="camera"
                        ),
                    ),
                ],
            )
        )
        photo_clear = tap_icon_button(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            tooltip=tr("tx.item_photo_remove", self._lang),
            on_click=lambda _e, current=row: self._clear_photo(current),
            padding=6,
        )
        row.photo_btn = photo_btn
        row.photo_clear = photo_clear
        row.photo_preview = photo_preview
        self._refresh_photo_row(row)
        photo_strip = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            visible=self._page is not None,
            controls=[photo_preview, photo_btn, photo_clear],
        )
        body = ft.Column(
            spacing=10,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[remove],
                ),
                name_tf,
                amount_tf,
                photo_strip,
            ],
        )
        card = card_surface(body, padding=ft.Padding.symmetric(horizontal=12, vertical=10))
        row.card = card
        wire_field_chain(self._host_page(), [name_tf, amount_tf])
        self._rows.append(row)
        self._list.controls.append(card)
        self._refresh_total()
        safe_update(self._list)

    def _refresh_photo_row(self, row: _LineRow) -> None:
        has = bool(row.photo_rel or row.pending)
        if row.photo_clear is not None:
            row.photo_clear.visible = has
        if row.photo_btn is not None:
            row.photo_btn.visible = not has
        if row.photo_preview is not None:
            row.photo_preview.visible = has
            if has:
                abs_path = self._preview_path(row)
                if abs_path is not None and abs_path.is_file():
                    row.photo_preview.content = ft.Image(
                        src=str(abs_path),
                        width=40,
                        height=40,
                        fit=ft.BoxFit.COVER,
                    )
                else:
                    row.photo_preview.content = ft.Icon(
                        ft.Icons.IMAGE_OUTLINED,
                        size=18,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
            safe_update(row.photo_preview)
            safe_update(row.photo_clear)
            safe_update(row.photo_btn)

    def _preview_path(self, row: _LineRow) -> Path | None:
        if not row.photo_rel:
            return None
        try:
            from lib.infrastructure.services.media_store import MediaStore

            return MediaStore().absolute(row.photo_rel)
        except Exception:  # noqa: BLE001
            return None

    def _pick_photo(self, row: _LineRow, *, source: str = "gallery") -> None:
        page = self._host_page()
        if page is None:
            return
        run_async(page, self._pick_photo_async, row, source)

    async def _pick_photo_async(self, row: _LineRow, source: str = "gallery") -> None:
        from lib.presentation.file_transfer import pick_image_bytes
        from lib.presentation.utils import snack

        page = self._host_page()
        if page is None:
            return
        title_key = "tx.take_photo" if source == "camera" else "tx.photo_gallery"
        picked = await pick_image_bytes(
            page,
            title=tr(title_key, self._lang),
            source=source,
        )
        if picked is None:
            return
        name, payload = picked
        if len(payload) > 12 * 1024 * 1024:
            snack(page, tr("tx.attachment_too_large", self._lang), error=True)
            return
        row.pending = (name, payload)
        row.photo_rel = ""
        self._refresh_photo_row(row)
        snack(page, tr("tx.attachment_added", self._lang))

    def _clear_photo(self, row: _LineRow) -> None:
        if row.photo_rel:
            try:
                from lib.infrastructure.services.media_store import MediaStore

                MediaStore().delete_paths([row.photo_rel])
            except Exception:  # noqa: BLE001
                pass
        row.photo_rel = ""
        row.pending = None
        self._refresh_photo_row(row)

    def _remove_row(self, row: _LineRow) -> None:
        if row not in self._rows:
            return
        if len(self._rows) <= 1:
            return
        idx = self._rows.index(row)
        self._rows.pop(idx)
        self._list.controls.pop(idx)
        self._refresh_total()
        safe_update(self._list)

    def _persist_photo(self, row: _LineRow) -> str:
        if row.pending is None:
            return (row.photo_rel or "").strip()
        from lib.infrastructure.services.media_store import MediaStore

        name, payload = row.pending
        rel = MediaStore().save_receipt(
            transaction_id=self._tx_id,
            filename=name,
            payload=payload,
        )
        row.pending = None
        row.photo_rel = rel
        return rel

    def _refresh_total(self) -> None:
        total = Decimal("0")
        for row in self._rows:
            try:
                total += parse_amount(amount_text(row.amount))
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
        for row in self._rows:
            raw_name = (row.name.value or "").strip()
            raw_amt = amount_text(row.amount).strip()
            if not raw_name and not raw_amt:
                continue
            try:
                amount = parse_amount(raw_amt)
            except (InvalidOperation, ValueError):
                return []
            if amount <= 0:
                return []
            items.append(
                TransactionItem(
                    name=raw_name or default_category,
                    amount=amount,
                    category=default_category,
                    attachment=self._persist_photo(row),
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
                    attachment=getattr(item, "attachment", "") or "",
                )
        self._refresh_total()
