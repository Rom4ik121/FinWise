"""Horizontal account picker — circular swipe carousel."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Optional

import flet as ft

from lib.domain.entities.account import Account
from lib.presentation.account_icons import account_icon_badge, resolve_account_icon_key
from lib.presentation.haptics import haptic
from lib.presentation.responsive import clamp_content_width, scale_size
from lib.presentation.utils import format_money, run_async, safe_update, tr

OnChanged = Callable[[Optional[str]], None]

_CARD_H = 88
_VIEWPORT = 0.72
# Triple the list so swipe past the last account lands on the first (and reverse).
_LOOP_COPIES = 3


def loop_page_count(n: int, *, copies: int = _LOOP_COPIES) -> int:
    """Total PageView pages for ``n`` accounts in a circular strip."""
    if n <= 1:
        return max(0, n)
    return n * copies


def logical_index(page_index: int, n: int) -> int:
    """Map a PageView index onto ``0..n-1``."""
    if n <= 0:
        return 0
    return int(page_index) % n


def middle_copy_index(logical: int, n: int, *, copies: int = _LOOP_COPIES) -> int:
    """Index inside the middle copy for seamless wrap jumps."""
    if n <= 1:
        return 0
    mid = copies // 2
    return mid * n + (logical % n)


def should_recenter(page_index: int, n: int, *, copies: int = _LOOP_COPIES) -> bool:
    """True when the pager is near a cloned edge and should jump to the middle."""
    if n <= 1 or copies < 3:
        return False
    total = n * copies
    # Stay away from first/last copy boundaries.
    return page_index < n or page_index >= total - n


class AccountStripPicker(ft.Column):
    """Circular account carousel: icon, name, color accent, balance.

    Drop-in replacement for account ``Dropdown`` in create/edit forms.
    Swipe loops forever (last → first, first → last). Side cards stay visible
    so the strip feels like a rotating wheel.
    """

    def __init__(
        self,
        page: ft.Page,
        accounts: Sequence[Account],
        *,
        lang: str,
        label: str | None = None,
        value: str | None = None,
        on_changed: OnChanged | None = None,
        exchange_ids: Optional[dict[str, str]] = None,
        frequent_id: str | None = None,
        expand: bool = False,
    ) -> None:
        self._page = page
        self._lang = lang
        self._on_changed = on_changed
        self._exchange_ids = dict(exchange_ids or {})
        self._frequent_id = frequent_id
        self._accounts: list[Account] = list(accounts)
        self._value: str | None = None
        self._cards: dict[str, list[ft.Container]] = {}
        self._pager: ft.PageView | None = None
        self._page_accounts: list[Account] = []
        self._suppress_change = False
        self._recentering = False

        self._label = ft.Text(
            label or tr("field.account", lang),
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self._empty = ft.Text(
            tr("error.no_accounts", lang),
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=False,
        )
        self._hint = ft.Text(
            tr("account.swipe_hint", lang),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=False,
        )
        card_h = scale_size(_CARD_H, page, minimum=78, maximum=100)
        self._host = ft.Container(height=card_h + 8, expand=True, content=None)

        super().__init__(
            spacing=6,
            tight=True,
            expand=expand,
            controls=[self._label, self._host, self._hint, self._empty],
        )
        self.set_accounts(self._accounts, value=value, notify=False)

    @property
    def value(self) -> str | None:
        return self._value

    @value.setter
    def value(self, account_id: str | None) -> None:
        self.set_value(account_id, notify=False)

    def selected_account(self) -> Account | None:
        if not self._value:
            return None
        return next((a for a in self._accounts if a.id == self._value), None)

    def bind_changed(self, handler: OnChanged | None) -> None:
        """Attach or replace the selection callback."""
        self._on_changed = handler

    def set_value(self, account_id: str | None, *, notify: bool = True) -> None:
        ids = {a.id for a in self._accounts}
        next_id = account_id if account_id in ids else (
            self._accounts[0].id if self._accounts else None
        )
        changed = next_id != self._value
        self._value = next_id
        self._paint_selection()
        self._scroll_to_selected()
        if notify and changed and self._on_changed is not None:
            self._on_changed(self._value)

    def set_accounts(
        self,
        accounts: Sequence[Account],
        *,
        value: str | None = None,
        frequent_id: str | None = None,
        exchange_ids: Optional[dict[str, str]] = None,
        notify: bool = False,
    ) -> None:
        """Replace the account list (e.g. transfer fee account reorder)."""
        self._accounts = list(accounts)
        if frequent_id is not None:
            self._frequent_id = frequent_id
        if exchange_ids is not None:
            self._exchange_ids = dict(exchange_ids)
        preferred = value if value is not None else self._value
        ids = {a.id for a in self._accounts}
        self._value = preferred if preferred in ids else (
            self._accounts[0].id if self._accounts else None
        )
        self._rebuild()
        if notify and self._on_changed is not None:
            self._on_changed(self._value)

    def _rebuild(self) -> None:
        empty = not self._accounts
        multi = len(self._accounts) > 1
        self._empty.visible = empty
        self._host.visible = not empty
        self._hint.visible = multi
        self._cards.clear()
        self._page_accounts = []
        if empty:
            self._pager = None
            self._host.content = None
            safe_update(self)
            return

        pages: list[ft.Control] = []
        copies = _LOOP_COPIES if multi else 1
        for _ in range(copies):
            for account in self._accounts:
                card = self._build_card(account)
                self._cards.setdefault(account.id, []).append(card)
                self._page_accounts.append(account)
                pages.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=6),
                        alignment=ft.Alignment.CENTER,
                        content=card,
                    )
                )

        logical = 0
        if self._value:
            for i, account in enumerate(self._accounts):
                if account.id == self._value:
                    logical = i
                    break
        start = middle_copy_index(logical, len(self._accounts), copies=copies)
        self._pager = ft.PageView(
            controls=pages,
            selected_index=start,
            horizontal=True,
            snap=True,
            pad_ends=True,
            viewport_fraction=_VIEWPORT if multi else 1.0,
            height=self._host.height,
            on_change=self._on_page_change,
        )
        self._host.content = self._pager
        self._paint_selection()
        safe_update(self)

    def _build_card(self, account: Account) -> ft.Container:
        exchange_id = self._exchange_ids.get(account.id, "")
        icon_key = resolve_account_icon_key(account.icon, exchange_id)
        accent = account.color or ft.Colors.PRIMARY
        badge = account_icon_badge(
            icon_key,
            color=accent,
            size=scale_size(44, self._page, minimum=40, maximum=52),
            glyph_size=scale_size(22, self._page, minimum=18, maximum=26),
        )
        name = ft.Text(
            account.name,
            size=15,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_SURFACE,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )
        balance = ft.Text(
            format_money(account.balance, account.currency),
            size=14,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        meta_bits: list[ft.Control] = [
            ft.Text(
                account.currency,
                size=11,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        ]
        if self._frequent_id and account.id == self._frequent_id:
            meta_bits.append(
                ft.Text(
                    f"· {tr('account.frequent', self._lang)}",
                    size=11,
                    color=ft.Colors.PRIMARY,
                )
            )
        if getattr(account, "is_corporate", False):
            meta_bits.append(
                ft.Text(
                    f"· {tr('account.corporate_badge', self._lang)}",
                    size=11,
                    color=ft.Colors.PRIMARY,
                )
            )
        card_w = clamp_content_width(self._page, margin=48, max_width=420)
        return ft.Container(
            width=card_w * _VIEWPORT if len(self._accounts) > 1 else card_w,
            height=(self._host.height or _CARD_H) - 4,
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            ink=True,
            animate_opacity=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
            on_click=lambda _e, aid=account.id: self._tap_select(aid),
            content=ft.Row(
                spacing=0,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Container(width=5, bgcolor=accent),
                    ft.Container(
                        expand=True,
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        content=ft.Row(
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                badge,
                                ft.Column(
                                    spacing=2,
                                    tight=True,
                                    expand=True,
                                    controls=[
                                        ft.Row(
                                            spacing=6,
                                            tight=True,
                                            controls=[name],
                                        ),
                                        ft.Row(spacing=4, tight=True, controls=meta_bits),
                                        balance,
                                    ],
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def _paint_selection(self) -> None:
        for account_id, cards in self._cards.items():
            active = account_id == self._value
            accent = None
            account = next((a for a in self._accounts if a.id == account_id), None)
            if account is not None:
                accent = account.color or ft.Colors.PRIMARY
            for card in cards:
                card.border = None
                card.opacity = 1.0 if active else 0.55
                try:
                    card.scale = 1.0 if active else 0.92
                except Exception:  # noqa: BLE001
                    pass
                card.shadow = (
                    ft.BoxShadow(
                        blur_radius=14,
                        color="#00000040",
                        offset=ft.Offset(0, 4),
                    )
                    if active
                    else None
                )
                # Color stripe stays the accent signal; no outline frame.
                stripe = None
                row = card.content
                if isinstance(row, ft.Row) and row.controls:
                    stripe = row.controls[0]
                if isinstance(stripe, ft.Container) and accent:
                    stripe.width = 6 if active else 5
                    stripe.bgcolor = accent
                    safe_update(stripe)
                safe_update(card)

    def _scroll_to_selected(self) -> None:
        if self._pager is None or not self._value or not self._accounts:
            return
        logical = 0
        for i, account in enumerate(self._accounts):
            if account.id == self._value:
                logical = i
                break
        target = middle_copy_index(logical, len(self._accounts))
        if self._pager.selected_index == target:
            return
        self._jump_silent(target)

    def _jump_silent(self, index: int) -> None:
        if self._pager is None:
            return

        async def _do() -> None:
            if self._pager is None:
                return
            self._suppress_change = True
            try:
                await self._pager.jump_to_page(index)
            except Exception:  # noqa: BLE001
                try:
                    self._pager.selected_index = index
                    safe_update(self._pager)
                except Exception:  # noqa: BLE001
                    pass
            finally:
                self._suppress_change = False

        run_async(self._page, _do)

    async def _recenter_later(self, index: int) -> None:
        """Jump to the middle clone after the snap animation finishes."""
        import asyncio

        await asyncio.sleep(0.08)
        if self._pager is None or self._recentering:
            return
        self._recentering = True
        try:
            self._suppress_change = True
            try:
                await self._pager.jump_to_page(index)
            except Exception:  # noqa: BLE001
                try:
                    self._pager.selected_index = index
                    safe_update(self._pager)
                except Exception:  # noqa: BLE001
                    pass
            finally:
                self._suppress_change = False
        finally:
            self._recentering = False

    def _on_page_change(self, e: ft.ControlEvent | None = None) -> None:
        if self._suppress_change or self._pager is None or not self._accounts:
            return
        index = int(getattr(self._pager, "selected_index", 0) or 0)
        n = len(self._accounts)
        total = len(self._page_accounts)
        if total <= 0:
            return
        index = max(0, min(index, total - 1))
        account = self._page_accounts[index]
        changed = account.id != self._value
        self._value = account.id
        self._paint_selection()
        if changed:
            haptic("light")
            if self._on_changed is not None:
                self._on_changed(self._value)
        if should_recenter(index, n):
            target = middle_copy_index(logical_index(index, n), n)
            run_async(self._page, self._recenter_later, target)

    def _tap_select(self, account_id: str) -> None:
        if account_id == self._value:
            return
        haptic("light")
        self.set_value(account_id, notify=True)
