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
