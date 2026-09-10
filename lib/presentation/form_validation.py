"""Shared form validation: field errors + a toast the overlay cannot hide."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import flet as ft

from lib.presentation.money_input import parse_amount
from lib.presentation.utils import safe_update, snack, tr


def set_field_error(field: Any, message: str | None) -> None:
    """Set ``TextField.error`` when the control supports it."""
    if field is None or not hasattr(field, "error"):
        return
    try:
        field.error = message
        if message and hasattr(field, "error_max_lines"):
            field.error_max_lines = 2
        safe_update(field)
    except Exception:  # noqa: BLE001
        pass


def clear_field_error(field: Any) -> None:
    set_field_error(field, None)


def require_name(
    field: Any,
    page: ft.Page,
    lang: str,
    *,
    message_key: str = "form.name_required",
) -> str | None:
    """Return a stripped name, or show an error and ``None``."""
    value = (getattr(field, "value", None) or "").strip()
    if value:
        clear_field_error(field)
        return value
    message = tr(message_key, lang)
    set_field_error(field, message)
    snack(page, message, error=True)
    return None


def require_positive_amount(
    field: Any,
    page: ft.Page,
    lang: str,
    *,
    message_key: str = "invalid_amount",
) -> Decimal | None:
    """Parse a positive amount from ``field``, or show an error and ``None``."""
    message = tr(message_key, lang)
    try:
        amount = parse_amount(getattr(field, "value", None))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError, ArithmeticError):
        set_field_error(field, message)
        snack(page, message, error=True)
        return None
    clear_field_error(field)
    return amount
