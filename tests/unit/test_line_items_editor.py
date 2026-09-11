"""Line-item editor: vertical cards and optional per-line photo path."""

from __future__ import annotations

from decimal import Decimal

import flet as ft

from lib.domain.entities.transaction import TransactionItem
from lib.presentation.widgets.line_items_editor import (
    LineItemsEditor,
    merge_line_item_photos,
)


def test_merge_line_item_photos_dedupes() -> None:
    items = [
        TransactionItem(name="A", amount=Decimal("1"), attachment="a.jpg"),
        TransactionItem(name="B", amount=Decimal("1"), attachment="b.jpg"),
        TransactionItem(name="C", amount=Decimal("1"), attachment="a.jpg"),
    ]
    assert merge_line_item_photos(["tx.jpg", "a.jpg"], items) == [
        "tx.jpg",
        "a.jpg",
        "b.jpg",
    ]


def test_line_items_editor_stacks_name_above_amount() -> None:
    editor = LineItemsEditor("en")
    editor.set_items(
        [
            TransactionItem(
                name="Bread",
                amount=Decimal("12.5"),
                category="Food",
                attachment="tx/1/bread.jpg",
            )
        ]
    )
    assert editor.enabled is True
    assert len(editor._list.controls) == 1
    card = editor._list.controls[0]
    body = card.content
    assert isinstance(body, ft.Column)
    fields = [c for c in body.controls if isinstance(c, ft.TextField)]
    assert len(fields) == 2
    assert fields[0].value == "Bread"
    assert "12" in (fields[1].value or "")
    cramped = [
        c
        for c in body.controls
        if isinstance(c, ft.Row)
        and sum(isinstance(x, ft.TextField) for x in c.controls) >= 2
    ]
    assert cramped == []
    collected = editor.collect(default_category="Food")
    assert collected is not None
    assert collected[0].name == "Bread"
    assert collected[0].attachment == "tx/1/bread.jpg"


def _walk(control: object):
    yield control
    for child in list(getattr(control, "controls", None) or []):
        yield from _walk(child)
    inner = getattr(control, "content", None)
    if inner is not None and inner is not control:
        yield from _walk(inner)
    for item in list(getattr(control, "items", None) or []):
        yield from _walk(item)


def test_line_items_editor_photo_is_single_camera_menu() -> None:
    """Empty row: one camera PopupMenuButton with Gallery / Take photo — no extra glyph."""
    editor = LineItemsEditor("en")
    editor._add_row()
    menus = [c for c in _walk(editor) if isinstance(c, ft.PopupMenuButton)]
    assert len(menus) == 1
    menu = menus[0]
    assert menu.icon == ft.Icons.PHOTO_CAMERA_OUTLINED
    assert menu.visible is True
    assert len(menu.items) == 2
    labels = []
    for item in menu.items:
        content = item.content
        labels.append(content.value if isinstance(content, ft.Text) else str(content))
        assert item.icon in (
            ft.Icons.PHOTO_LIBRARY_OUTLINED,
            ft.Icons.PHOTO_CAMERA_OUTLINED,
        )
    assert labels == ["Gallery", "Take photo"]
    icons = [
        c
        for c in _walk(editor)
        if isinstance(c, ft.Icon)
        and getattr(c, "icon", None)
        in {ft.Icons.ADD_A_PHOTO_OUTLINED, ft.Icons.PHOTO_CAMERA_OUTLINED}
    ]
    assert icons == []
    texts = [
        c.value
        for c in _walk(editor)
        if isinstance(c, ft.Text) and c.value == "Attach photo"
    ]
    assert texts == []


def test_line_items_editor_hides_camera_when_photo_attached() -> None:
    editor = LineItemsEditor("en")
    editor.set_items(
        [
            TransactionItem(
                name="Bread",
                amount=Decimal("1"),
                category="Food",
                attachment="tx/1/bread.jpg",
            )
        ]
    )
    menus = [c for c in _walk(editor) if isinstance(c, ft.PopupMenuButton)]
    assert len(menus) == 1
    assert menus[0].visible is False
    row = editor._rows[0]
    assert row.photo_preview is not None
    assert row.photo_preview.visible is True
    assert row.photo_clear is not None
    assert row.photo_clear.visible is True
