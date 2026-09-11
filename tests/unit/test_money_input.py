"""Grouped amount input parsing and formatting."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest

from lib.presentation.money_input import (
    amount_separators,
    attach_grouped_digits,
    format_amount_input,
    format_amount_value,
    parse_amount,
    parse_optional_amount,
    repair_amount_caret_prepend,
)


def test_separators_by_language() -> None:
    assert amount_separators("en") == (",", ".")
    assert amount_separators("zh") == (",", ".")
    assert amount_separators("ja") == (",", ".")
    assert amount_separators("ru") == (".", ",")
    assert amount_separators("uz") == (".", ",")
    assert amount_separators("de") == (".", ",")
    assert amount_separators("pt") == (".", ",")
    assert amount_separators("id") == (".", ",")


def test_format_groups_while_typing_ru() -> None:
    assert format_amount_input("1", "ru") == "1"
    assert format_amount_input("12", "ru") == "12"
    assert format_amount_input("123", "ru") == "123"
    assert format_amount_input("1234", "ru") == "1.234"
    assert format_amount_input("1234567", "ru") == "1.234.567"
    assert format_amount_input("1000000", "ru") == "1.000.000"
    assert format_amount_input("1,000000", "ru") == "1.000.000"
    assert format_amount_input("1.000000", "ru") == "1.000.000"
    assert format_amount_input("1000000", "en") == "1,000,000"
    assert format_amount_input("1,000000", "en") == "1,000,000"
    assert format_amount_input("1234,", "ru") == "1.234,"
    assert format_amount_input("1234,5", "ru") == "1.234,5"
    assert format_amount_input("1234,50", "ru") == "1.234,50"
    assert format_amount_input("50", "ru") == "50"
    assert format_amount_input("50", "en") == "50"
    # Bare "05" (no previous keystroke) still strips; live typing is repaired
    # in attach_grouped_digits via repair_amount_caret_prepend.
    assert format_amount_input("05", "ru") == "5"
    assert format_amount_input("05", "en") == "5"


def test_repair_caret_prepend_turns_05_into_50() -> None:
    assert repair_amount_caret_prepend("5", "05") == "50"
    assert repair_amount_caret_prepend("5", "50") == "50"
    assert repair_amount_caret_prepend("5", "15") == "51"
    assert repair_amount_caret_prepend("5", "51") == "51"
    assert repair_amount_caret_prepend("", "5") == "5"
    assert repair_amount_caret_prepend("50", "500") == "500"
    assert repair_amount_caret_prepend("12", "1.234") == "1.234"


def test_attach_grouped_digits_keeps_fifty() -> None:
    import flet as ft

    class _Evt:
        pass

    field = ft.TextField(value="")
    attach_grouped_digits(field, "ru")
    field.value = "5"
    field.on_change(_Evt())
    assert field.value == "5"
    field.value = "50"
    field.on_change(_Evt())
    assert field.value == "50"
    field.value = "5"
    field.on_change(_Evt())
    field.value = "05"
    field.on_change(_Evt())
    assert field.value == "50"


def test_format_groups_while_typing_en() -> None:
    assert format_amount_input("1234", "en") == "1,234"
    assert format_amount_input("1234.", "en") == "1,234."
    assert format_amount_input("1234.5", "en") == "1,234.5"
    assert format_amount_input("25000.00", "en") == "25,000.00"


def test_parse_grouped_amounts() -> None:
    assert parse_amount("1.234,50") == Decimal("1234.50")
    assert parse_amount("1,234.50") == Decimal("1234.50")
    assert parse_amount("25.000") == Decimal("25000")
    assert parse_amount("25,000") == Decimal("25000")
    assert parse_amount("1 234,5") == Decimal("1234.5")
    with pytest.raises(InvalidOperation):
        parse_amount("")
    with pytest.raises(InvalidOperation):
        parse_amount("   ")
    assert parse_optional_amount("") == Decimal("0")
    assert parse_optional_amount("  ") == Decimal("0")
    assert parse_optional_amount("1,50") == Decimal("1.50")


def test_format_amount_value_from_decimal() -> None:
    assert format_amount_value(Decimal("25000"), "ru") == "25.000"
    assert format_amount_value(Decimal("25000.5"), "ru") == "25.000,50"
    assert format_amount_value(Decimal("25000"), "en") == "25,000"
    assert format_amount_value("", "ru") == ""
