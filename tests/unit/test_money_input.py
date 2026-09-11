"""Grouped amount input parsing and formatting."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest

from lib.presentation.money_input import (
    amount_separators,
    amount_text,
    attach_grouped_digits,
    format_amount_input,
    format_amount_value,
    is_amount_write_echo,
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
    assert repair_amount_caret_prepend("50", "050") == "50"
    assert repair_amount_caret_prepend("12", "1.234") == "1.234"
    assert repair_amount_caret_prepend("", "05") == "50"
    assert repair_amount_caret_prepend("", "5") == "5"


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


def test_attach_grouped_digits_repairs_orphan_05() -> None:
    """Flet web can skip the first on_change and deliver only ``05``."""
    import flet as ft

    class _Evt:
        pass

    field = ft.TextField(value="")
    attach_grouped_digits(field, "en")
    field.value = "05"
    field.on_change(_Evt())
    assert field.value == "50"


def test_is_amount_write_echo_detects_flet_extra_zero() -> None:
    assert is_amount_write_echo("50", "500")
    assert is_amount_write_echo("50", "050")
    assert not is_amount_write_echo("50", "51")
    assert not is_amount_write_echo("5", "50")
    assert not is_amount_write_echo("50", "50")


def test_attach_grouped_digits_ignores_immediate_echo_500() -> None:
    import flet as ft

    class _Evt:
        pass

    field = ft.TextField(value="")
    attach_grouped_digits(field, "en")
    field.value = "5"
    field.on_change(_Evt())
    field.value = "05"
    field.on_change(_Evt())
    assert field.value == "50"
    field.value = "500"
    field.on_change(_Evt())
    assert field.value == "50"


def test_attach_grouped_digits_accepts_real_500_after_echo_window(monkeypatch) -> None:
    import flet as ft

    from lib.presentation import money_input as money_input_mod

    monkeypatch.setattr(money_input_mod, "AMOUNT_WRITE_ECHO_SECONDS", 0)

    class _Evt:
        pass

    field = ft.TextField(value="")
    attach_grouped_digits(field, "en")
    field.value = "5"
    field.on_change(_Evt())
    field.value = "50"
    field.on_change(_Evt())
    assert field.value == "50"
    field.value = "500"
    field.on_change(_Evt())
    assert field.value == "500"


def test_format_groups_while_typing_en() -> None:
    assert format_amount_input("1234", "en") == "1,234"
    assert format_amount_input("1234.", "en") == "1,234."
    assert format_amount_input("1234.5", "en") == "1,234.5"
    assert format_amount_input("25000.00", "en") == "25,000.00"


def test_parse_grouped_amounts() -> None:
    assert parse_amount("10") == Decimal("10")
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


def test_parse_filter_amount_blank_is_unbounded() -> None:
    from lib.presentation.money_input import amount_list_filters, parse_filter_amount

    assert parse_filter_amount("") is None
    assert parse_filter_amount("   ") is None
    assert parse_filter_amount(None) is None
    assert parse_filter_amount("abc") is None
    assert parse_filter_amount("10") == Decimal("10")
    assert parse_filter_amount("0") == Decimal("0")
    assert amount_list_filters("", "") == {}
    assert amount_list_filters("  ", None) == {}
    assert amount_list_filters("1.50", "") == {"amount_min": Decimal("1.50")}
    assert amount_list_filters("", "20") == {"amount_max": Decimal("20")}
    assert amount_list_filters("5", "9") == {
        "amount_min": Decimal("5"),
        "amount_max": Decimal("9"),
    }


def test_amount_text_prefers_live_then_grouped_cache() -> None:
    class _Field:
        def __init__(self, value: str = "") -> None:
            self.value = value

    live = _Field("10")
    live._fw_amount_text = {"text": "99"}
    assert amount_text(live) == "10"
    stale = _Field("")
    stale._fw_amount_text = {"text": "10"}
    assert amount_text(stale) == "10"
    assert amount_text(_Field("")) == ""


def test_format_amount_value_from_decimal() -> None:
    assert format_amount_value(Decimal("25000"), "ru") == "25.000"
    assert format_amount_value(Decimal("25000.5"), "ru") == "25.000,50"
    assert format_amount_value(Decimal("25000"), "en") == "25,000"
    assert format_amount_value("", "ru") == ""
