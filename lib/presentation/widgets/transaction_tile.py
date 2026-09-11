"""List tile for a single transaction with swipe-to-reveal actions."""

from __future__ import annotations

from math import pi
from typing import Callable, Optional

import flet as ft

from lib.domain.entities.category import Category
from lib.domain.entities.transaction import Transaction, TransactionType
from lib.domain.use_cases.debts import DEBT_INTEREST_TAG_PREFIX, DEBT_PRINCIPAL_TAG
from lib.domain.use_cases.transactions import TRANSFER_FEE_TAG_PREFIX
from lib.infrastructure.services.localization import localize_category_name
from lib.presentation.count_up import mark_money_text
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import amount_color
from lib.presentation.widgets.color_badge import color_badge
from lib.presentation.responsive import MIN_TAP, tx_tile_metrics
from lib.presentation.utils import (
    category_icon,
    format_date,
    format_money,
    format_money_compact,
    is_money_abbreviated,
    safe_update,
)

# Uniform card size across phones / tablets / desktop list widths.
_TILE_HEIGHT = 56
_AMOUNT_WIDTH = 88
_ICON = 36
_SLIDE_DURATION = 200

# Module-level ref to the currently open tile so we can auto-close it.
_currently_open: Optional["TransactionTile"] = None


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
    """Fixed-height row with swipe-to-reveal Edit / Delete actions."""

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
        page: ft.Page | None = None,
    ) -> None:
        from lib.presentation.utils import tr

        self._revealed = False
        metrics = tx_tile_metrics(page)
        tile_h = metrics["height"]
        amount_w = metrics["amount_width"]
        icon_edge = metrics["icon"]

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

        # --- Arrow toggle button (rotates 180° when open) ---
        self._arrow_container = ft.Container(
            width=MIN_TAP,
            height=tile_h,
            alignment=ft.Alignment.CENTER,
            ink=True,
            border_radius=8,
            on_click=lambda _e: self._toggle(),
            rotate=ft.Rotate(0),
            animate_rotation=ft.Animation(_SLIDE_DURATION, ft.AnimationCurve.EASE_OUT),
            content=ft.Icon(
                ft.Icons.CHEVRON_LEFT_ROUNDED,
                color=ft.Colors.ON_SURFACE_VARIANT,
                size=20,
            ),
        )

        # --- Front layer (main content) ---
        signed_amount = (
            transaction.amount
            if is_income or is_transfer
            else -abs(transaction.amount)
        )
        amount_label = mark_money_text(
            ft.Text(
                signed,
                color=amount_color_value,
                weight=ft.FontWeight.W_700,
                size=metrics["amount"],
                text_align=ft.TextAlign.RIGHT,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            signed_amount,
            currency=transaction.currency,
            compact=True,
            signed=True,
        )
        full_amount = format_money(
            abs(transaction.amount),
            transaction.currency,
            signed=False,
        )
        if not is_income and not is_transfer:
            full_amount = f"−{full_amount}"
        elif is_income and not is_transfer:
            full_amount = format_money(
                transaction.amount, transaction.currency, signed=True
            )
        can_expand = is_money_abbreviated(
            abs(transaction.amount), transaction.currency
        )

        def _show_full(
            _e: ft.ControlEvent | None = None, *, _full: str = full_amount
        ) -> None:
            if not can_expand:
                return
            page = getattr(_e, "page", None) if _e is not None else None
            if page is None:
                return
            try:
                from lib.presentation.ui_feedback import flash_message

                if not flash_message(page, _full, haptic_kind="selection"):
                    amount_label.value = _full
                    safe_update(amount_label)
            except Exception:  # noqa: BLE001
                pass

        amount_box = ft.Container(
            width=amount_w,
            alignment=ft.Alignment.CENTER_RIGHT,
            ink=can_expand,
            on_click=_show_full if can_expand else None,
            tooltip=full_amount if can_expand else None,
            content=amount_label,
        )
        front_row = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            expand=True,
            controls=[
                color_badge(
                    icon_data,
                    bgcolor=icon_bg,
                    fgcolor=icon_fg,
                    size=icon_edge,
                    glyph_size=18,
                    page=page,
                    radius=11,
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
                            size=metrics["title"],
                            overflow=ft.TextOverflow.ELLIPSIS,
                            max_lines=1,
                            no_wrap=True,
                        ),
                        ft.Text(
                            subtitle,
                            size=metrics["subtitle"],
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            max_lines=1,
                            no_wrap=True,
                        ),
                    ],
                ),
                amount_box,
                self._arrow_container,
            ],
        )

        self._front = ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
            border_radius=12,
            height=tile_h,
            alignment=ft.Alignment.CENTER_LEFT,
            offset=ft.Offset(0, 0),
            animate_offset=ft.Animation(
                _SLIDE_DURATION, ft.AnimationCurve.EASE_OUT,
            ),
            ink=True,
            content=front_row,
        )
        from lib.presentation.ui_motion import bind_press

        bind_press(
            self._front,
            haptic_kind="light",
            on_click=lambda _e: self._on_front_click(transaction, on_open, on_edit),
        )

        # --- Back layer (action buttons) — sized to fit narrow phones ---
        from lib.presentation.responsive import (
            swipe_action_strip_width,
            swipe_reveal_offset,
        )

        action_count = sum(1 for h in (on_edit, on_delete) if h is not None)
        strip_w = swipe_action_strip_width(None, buttons=max(action_count, 1))
        self._reveal_frac = swipe_reveal_offset(
            None, strip_width=strip_w, buttons=max(action_count, 1)
        )
        btn_w = max(44.0, (strip_w - 8) / max(action_count, 1))

        def _action_chip(
            *,
            icon: str,
            label: str,
            fg: str,
            on_click,
        ) -> ft.Control:
            return ft.Container(
                width=btn_w,
                height=tile_h - 8,
                bgcolor=ft.Colors.with_opacity(0.14, fg),
                border_radius=10,
                ink=True,
                tooltip=label,
                on_click=on_click,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(icon, size=18, color=fg),
            )

        def _edit_click(_e: ft.ControlEvent) -> None:
            self._close()
            if on_edit:
                on_edit(transaction)

        def _delete_click(_e: ft.ControlEvent) -> None:
            self._close()
            if on_delete:
                on_delete(transaction)

        action_controls: list[ft.Control] = []
        if on_edit is not None:
            action_controls.append(
                _action_chip(
                    icon=ft.Icons.EDIT_OUTLINED,
                    label=tr("action.edit", language),
                    fg=ft.Colors.PRIMARY,
                    on_click=_edit_click,
                )
            )
        if on_delete is not None:
            action_controls.append(
                _action_chip(
                    icon=ft.Icons.DELETE_OUTLINE,
                    label=tr("action.delete", language),
                    fg=ft.Colors.ERROR,
                    on_click=_delete_click,
                )
            )

        back = ft.Container(
            height=tile_h,
            border_radius=12,
            padding=ft.Padding.only(right=6),
            alignment=ft.Alignment.CENTER_RIGHT,
            content=ft.Container(
                width=strip_w,
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                    tight=True,
                    controls=action_controls,
                ),
            ),
        )

        super().__init__(
            height=tile_h,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            margin=ft.Margin.only(bottom=6),
            alignment=ft.Alignment.CENTER_LEFT,
            content=ft.Stack(
                controls=[back, self._front],
            ),
        )

    # --- slide logic ---

    def _on_front_click(
        self,
        tx: Transaction,
        on_open: Optional[Callable[[Transaction], None]],
        on_edit: Optional[Callable[[Transaction], None]],
    ) -> None:
        if self._revealed:
            self._close()
            return
        if on_open:
            on_open(tx)
        elif on_edit:
            on_edit(tx)

    def _toggle(self) -> None:
        if self._revealed:
            self._close()
        else:
            self._open()

    def _open(self) -> None:
        global _currently_open
        # Auto-close the previously open tile.
        if _currently_open is not None and _currently_open is not self:
            _currently_open._close()
        _currently_open = self
        self._revealed = True
        from lib.presentation.haptics import haptic
        from lib.presentation.responsive import swipe_reveal_offset

        try:
            haptic("selection")
        except Exception:  # noqa: BLE001
            pass
        frac = getattr(self, "_reveal_frac", None)
        if frac is None:
            frac = swipe_reveal_offset(getattr(self, "page", None), buttons=2)
        else:
            # Recompute with live page width when mounted.
            frac = swipe_reveal_offset(getattr(self, "page", None), buttons=2)
        self._front.offset = ft.Offset(-frac, 0)
        self._arrow_container.rotate = ft.Rotate(pi)
        safe_update(self._front)
        safe_update(self._arrow_container)

    def _close(self) -> None:
        global _currently_open
        if _currently_open is self:
            _currently_open = None
        self._revealed = False
        self._front.offset = ft.Offset(0, 0)
        self._arrow_container.rotate = ft.Rotate(0)
        safe_update(self._front)
        safe_update(self._arrow_container)
