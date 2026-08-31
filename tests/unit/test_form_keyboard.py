"""Keyboard type helpers for mobile forms."""

from __future__ import annotations

import flet as ft

from lib.presentation.form_keyboard import configure_field, keyboard_for, wire_field_chain


def test_keyboard_for_kinds() -> None:
    assert keyboard_for("number") is ft.KeyboardType.NUMBER
    assert keyboard_for("name") is ft.KeyboardType.NAME
    assert keyboard_for("text") is ft.KeyboardType.TEXT
    assert keyboard_for("search") is ft.KeyboardType.WEB_SEARCH
    assert keyboard_for("password") is ft.KeyboardType.VISIBLE_PASSWORD


def test_configure_field_number_flags() -> None:
    field = ft.TextField()
    configure_field(field, "number")
    assert field.keyboard_type is ft.KeyboardType.NUMBER
    assert field.autocorrect is False
    assert field.enable_suggestions is False
    assert field.multiline is False
    assert field.on_tap_outside is not None


def test_wire_field_chain_sets_on_submit() -> None:
    a = ft.TextField()
    b = ft.TextField()
    configure_field(a, "number")
    configure_field(b, "text")
    wire_field_chain(None, [a, b])
    assert callable(a.on_submit)
    assert callable(b.on_submit)
