"""List tile for a single transaction."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.domain.entities.category import Category
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.use_cases.debts import DEBT_INTEREST_TAG_PREFIX, DEBT_PRINCIPAL_TAG
from lib.domain.use_cases.transactions import TRANSFER_FEE_TAG_PREFIX
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.count_up import mark_money_text
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import amount_color, style_popup_menu
from lib.presentation.utils import category_icon, format_date, format_money_compact

# Uniform card size across phones / tablets / desktop list widths.
_TILE_HEIGHT = 56
_AMOUNT_WIDTH = 96
_ICON = 36


def _is_internal_tag(tag: str) -> bool:
    """Hide system linkage tags from list subtitles (full detail is in the editor)."""
    value = (tag or "").strip().lower()
    if not value:
        return True
    if value in {"fee", DEBT_PRINCIPAL_TAG}:
        return True
    if value.startswith(TRANSFER_FEE_TAG_PREFIX):
        return True
    if value.startswith(DEBT_INTEREST_TAG_PREFIX):
        return True
    # Exchange sync / external id tags: ``binance:fee:…``, ``ext:…``
    if ":" in value and not value.startswith("#"):
        return True
    return False


def _display_tags(tags: list[str] | None, *, limit: int = 2) -> list[str]:
    visible = [t for t in (tags or []) if not _is_internal_tag(t)]
    return [f"#{tag}" for tag in visible[:limit]]


def _subtitle_line(transaction: Transaction, *, language: str) -> str:
    parts: list[str] = [format_date(transaction.date, with_time=True)]
    if transaction.has_items:
        parts.append(transaction.items_summary(limit=2))
    else:
        comment = (transaction.comment or "").strip()
        category = (transaction.category or "").strip()
        # Avoid repeating the category already shown as the title.
        if comment and comment.casefold() != category.casefold():
            if comment.casefold().startswith(f"{category.casefold()} · "):
                comment = comment[len(category) + 3 :].strip()
            elif comment.casefold().startswith(f"{category.casefold()} • "):
                comment = comment[len(category) + 3 :].strip()
            if comment:
                parts.append(comment)
    parts.extend(_display_tags(transaction.tags))
    return " · ".join(p for p in parts if p)


class TransactionTile(ft.Container):
    """Fixed-height row: category, truncated meta, signed amount."""

    def __init__(
        self,
        transaction: Transaction,
        *,
        category: Optional[Category] = None,
        on_open: Optional[Callable[[Transaction], None]] = None,
        on_edit: Optional[Callable[[Transaction], None]] = None,
        on_delete: Optional[Callable[[Transaction], None]] = None,
        language: str = "ru",
        dark: bool = True,
    ) -> None:
        from lib.presentation.utils import tr

        is_transfer = transaction.is_transfer
        is_income = transaction.type == TransactionType.INCOME
        amount_color_value = (
            get_active_skin().primary_hex(dark=dark)
            if is_transfer
            else amount_color(is_income, dark=dark)
        )
        signed = format_money_compact(
            transaction.amount,
            transaction.currency,
            signed=True,
        )
        if not is_income and not signed.startswith("−"):
            signed = f"−{format_money_compact(transaction.amount, transaction.currency)}"

        trailing_menu = style_popup_menu(
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                icon_color=ft.Colors.ON_SURFACE_VARIANT,
                items=[
                    ft.PopupMenuItem(
                        content=ft.Text(tr("action.edit", language)),
                        icon=ft.Icons.EDIT_OUTLINED,
                        on_click=lambda _e: on_edit(transaction) if on_edit else None,
                    ),
                    ft.PopupMenuItem(
                        content=ft.Text(tr("action.delete", language)),
                        icon=ft.Icons.DELETE_OUTLINE,
                        on_click=lambda _e: on_delete(transaction) if on_delete else None,
                    ),
                ],
            )
        )

        icon_bg = (
            ft.Colors.SECONDARY_CONTAINER
            if is_transfer
            else (
                category.color
                if category is not None
                else (
                    get_active_skin().badge_bg(dark=dark)
                    if is_income
                    else get_active_skin().expense_hex(dark=dark)
                )
            )
        )
        icon_data = (
            ft.Icons.SWAP_HORIZ_ROUNDED
            if is_transfer
            else (
                category_icon(category.icon)
                if category is not None
                else (ft.Icons.SOUTH_WEST if is_income else ft.Icons.NORTH_EAST)
            )
        )
        icon_fg = (
            ft.Colors.ON_SECONDARY_CONTAINER
            if is_transfer
            else (
                "#FFFFFF"
                if category is not None
                else (
                    get_active_skin().badge_fg(dark=dark)
                    if is_income
                    else "#FFFFFF"
                )
            )
        )

        title = localize_category_name(transaction.category, language)
        subtitle = _subtitle_line(transaction, language=language)

        body = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            expand=True,
            controls=[
                ft.Container(
                    width=_ICON,
                    height=_ICON,
                    border_radius=11,
                    bgcolor=icon_bg,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon_data, color=icon_fg, size=18),
                ),
                ft.Column(
                    spacing=1,
                    tight=True,
                    expand=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            title,
                            weight=ft.FontWeight.W_600,
                            size=13,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            max_lines=1,
                        ),
                        ft.Text(
                            subtitle,
                            size=10,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            max_lines=1,
                        ),
                    ],
                ),
                ft.Container(
                    width=_AMOUNT_WIDTH,
                    alignment=ft.Alignment.CENTER_RIGHT,
                    content=mark_money_text(
                        ft.Text(
                            signed,
                            color=amount_color_value,
                            weight=ft.FontWeight.W_700,
                            size=12,
                            text_align=ft.TextAlign.RIGHT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        transaction.amount
                        if is_income or is_transfer
                        else -abs(transaction.amount),
                        currency=transaction.currency,
                        compact=True,
                        signed=True,
                    ),
                ),
                trailing_menu,
            ],
        )
        super().__init__(
            height=_TILE_HEIGHT,
            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            on_click=lambda _e: (
                on_open(transaction)
                if on_open
                else (on_edit(transaction) if on_edit else None)
            ),
            margin=ft.Margin.only(bottom=6),
            alignment=ft.Alignment.CENTER_LEFT,
            content=body,
        )
