"""Adaptive text and money labels — ellipsis + viewport-scaled type."""

from __future__ import annotations

from decimal import Decimal

import flet as ft

from lib.presentation.count_up import mark_money_text
from lib.presentation.responsive import fit_font
from lib.presentation.utils import format_money, format_money_compact


def adaptive_text(
    value: str,
    *,
    page: ft.Page | None = None,
    size: int = 14,
    weight: ft.FontWeight | None = None,
    color: str | None = None,
    max_lines: int = 1,
    expand: bool = False,
    text_align: ft.TextAlign | None = None,
    minimum: int = 10,
    maximum: int = 28,
) -> ft.Text:
    """Primary UI copy that shrinks on phones and never overflows its card."""
    return ft.Text(
        value,
        size=fit_font(size, page, minimum=minimum, maximum=maximum),
        weight=weight,
        color=color,
        overflow=ft.TextOverflow.ELLIPSIS,
        max_lines=max_lines,
        no_wrap=max_lines == 1,
        expand=expand,
        text_align=text_align,
    )


def money_label(
    amount: Decimal | float | int | str,
    currency: str,
    *,
    page: ft.Page | None = None,
    size: int = 16,
    weight: ft.FontWeight = ft.FontWeight.W_700,
    color: str | None = None,
    compact: bool = False,
    signed: bool = False,
    mark: bool = True,
    expand: bool = False,
    text_align: ft.TextAlign | None = None,
) -> ft.Text:
    """Ledger amount via ``format_money`` / compact helper (never raw Decimal)."""
    display = (
        format_money_compact(amount, currency, signed=signed)
        if compact
        else format_money(amount, currency, signed=signed)
    )
    text = ft.Text(
        display,
        size=fit_font(size, page, minimum=11, maximum=28),
        weight=weight,
        color=color,
        overflow=ft.TextOverflow.ELLIPSIS,
        max_lines=1,
        no_wrap=True,
        expand=expand,
        text_align=text_align,
    )
    if mark:
        mark_money_text(
            text,
            amount,
            currency=currency,
            compact=compact,
            signed=signed,
        )
    return text
