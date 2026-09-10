"""UI helpers for attaching receipt photos to a transaction."""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from uuid import uuid4

import flet as ft

from lib.infrastructure.services.media_store import MediaStore
from lib.presentation.file_transfer import pick_restore_bytes
from lib.presentation.utils import run_async, safe_update, snack, tr
from lib.presentation.widgets.fullscreen_form import dismiss_fullscreen, push_overlay


class AttachmentPicker(ft.Column):
    """Pending + existing attachment list with add/remove controls."""

    def __init__(
        self,
        page: ft.Page,
        *,
        lang: str,
        transaction_id: str | None = None,
        existing: list[str] | None = None,
    ) -> None:
        self._page = page
        self._lang = lang
        self._tx_id = transaction_id or str(uuid4())
        self._store = MediaStore()
        self._paths: list[str] = list(existing or [])
        self._pending: list[tuple[str, bytes]] = []
        self._list = ft.Column(spacing=6, tight=True, controls=[])
        super().__init__(
            spacing=8,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.OutlinedButton(
                            tr("tx.attach_photo", lang),
                            icon=ft.Icons.ADD_A_PHOTO_OUTLINED,
                            on_click=lambda _e: run_async(page, self._pick),
                        ),
                    ],
                ),
                self._list,
            ],
        )
        self._rebuild()

    @property
    def transaction_id(self) -> str:
        return self._tx_id

    def set_transaction_id(self, tx_id: str) -> None:
        self._tx_id = tx_id

    def collected_paths(self) -> list[str]:
        """Persist pending bytes and return the full relative path list."""
        out = list(self._paths)
        for name, payload in self._pending:
            rel = self._store.save_receipt(
                transaction_id=self._tx_id,
                filename=name,
                payload=payload,
            )
            out.append(rel)
        self._pending.clear()
        self._paths = out
        return list(out)

    async def _pick(self) -> None:
        picked = await pick_restore_bytes(
            self._page,
            title=tr("tx.attach_photo", self._lang),
            extensions=["jpg", "jpeg", "png", "webp", "gif", "heic"],
            images=True,
        )
        if picked is None:
            return
        name, payload = picked
        if len(self._paths) + len(self._pending) >= 8:
            snack(self._page, tr("tx.attachments_limit", self._lang), error=True)
            return
        if len(payload) > 12 * 1024 * 1024:
            snack(self._page, tr("tx.attachment_too_large", self._lang), error=True)
            return
        self._pending.append((name, payload))
        self._rebuild()
        snack(self._page, tr("tx.attachment_added", self._lang))

    def _rebuild(self) -> None:
        rows: list[ft.Control] = []
        for idx, rel in enumerate(self._paths):
            abs_path = self._store.absolute(rel)
            rows.append(self._row(label=Path(rel).name, path=abs_path, on_remove=lambda i=idx: self._remove_existing(i)))
        for idx, (name, _payload) in enumerate(self._pending):
            rows.append(
                self._row(
                    label=f"{name} *",
                    path=None,
                    on_remove=lambda i=idx: self._remove_pending(i),
                )
            )
        self._list.controls = rows
        safe_update(self._list)

    def _remove_existing(self, index: int) -> None:
        if 0 <= index < len(self._paths):
            rel = self._paths.pop(index)
            self._store.delete_paths([rel])
            self._rebuild()

    def _remove_pending(self, index: int) -> None:
        if 0 <= index < len(self._pending):
            self._pending.pop(index)
            self._rebuild()

    def _row(
        self,
        *,
        label: str,
        path: Path | None,
        on_remove: Callable[[], None],
    ) -> ft.Control:
        preview: ft.Control
        if path is not None and path.is_file():
            preview = ft.Image(
                src=str(path),
                width=56,
                height=56,
                fit=ft.BoxFit.COVER,
                border_radius=8,
            )
        else:
            preview = ft.Container(
                width=56,
                height=56,
                border_radius=8,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=22),
            )
        return ft.Container(
            padding=8,
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    preview,
                    ft.Text(label, size=12, expand=True, max_lines=2),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=18,
                        on_click=lambda _e: on_remove(),
                    ),
                ],
            ),
        )


def open_attachment_viewer(
    page: ft.Page,
    path: Path | str,
    *,
    lang: str,
) -> None:
    """Show a single attachment image full-screen; tap or close dismisses."""
    abs_path = Path(path)
    if not abs_path.is_file():
        return
    key = "attachment_viewer"
    dismiss_fullscreen(page, key=key)

    def _close(_e: ft.ControlEvent | None = None) -> None:
        dismiss_fullscreen(page, key=key)

    overlay = ft.Container(
        data=key,
        expand=True,
        bgcolor=ft.Colors.BLACK,
        alignment=ft.Alignment.CENTER,
        content=ft.Stack(
            expand=True,
            controls=[
                ft.GestureDetector(
                    on_tap=_close,
                    content=ft.Container(
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                        padding=12,
                        content=ft.Image(
                            src=str(abs_path),
                            fit=ft.BoxFit.CONTAIN,
                            expand=True,
                        ),
                    ),
                ),
                ft.Container(
                    top=8,
                    right=8,
                    content=ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.with_opacity(0.35, ft.Colors.BLACK),
                        tooltip=tr("action.close", lang),
                        on_click=_close,
                    ),
                ),
            ],
        ),
    )
    push_overlay(page, overlay)


def attachment_gallery(
    paths: list[str],
    *,
    page: ft.Page,
    lang: str,
    store: MediaStore | None = None,
) -> list[ft.Control]:
    """Read-only gallery controls for transaction detail (tap → fullscreen)."""
    if not paths:
        return []
    media = store or MediaStore()
    images: list[ft.Control] = [
        ft.Text(
            tr("tx.attachments", lang),
            weight=ft.FontWeight.W_700,
            size=14,
        )
    ]
    for rel in paths:
        abs_path = media.absolute(rel)
        if not abs_path.is_file():
            continue
        images.append(
            ft.Container(
                border_radius=12,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ink=True,
                on_click=lambda _e, p=abs_path: open_attachment_viewer(
                    page, p, lang=lang
                ),
                content=ft.Image(
                    src=str(abs_path),
                    width=280,
                    height=200,
                    fit=ft.BoxFit.COVER,
                ),
            )
        )
    return images
