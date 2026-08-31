"""Helpers to build DropdownOption rows with leading icons."""

from __future__ import annotations

from typing import Optional, Sequence

import flet as ft

from lib.domain.entities.account import Account
from lib.presentation.account_icons import (
    account_icon_control,
    crypto_icon_src,
    exchange_icon_src,
    parse_currency_icon_key,
    parse_exchange_icon_key,
    resolve_account_icon_key,
)


def _leading_from_account_icon(key: str | None, *, size: float = 22) -> ft.Control:
    """Small leading glyph / clipped logo for a dropdown row."""
    exchange_id = parse_exchange_icon_key(key)
    code = parse_currency_icon_key(key)
    is_logo = bool(
        (exchange_id and exchange_icon_src(exchange_id))
        or (code and crypto_icon_src(code))
    )
    glyph = account_icon_control(
        key,
        size=size if is_logo else size,
        color=ft.Colors.ON_SURFACE,
    )
    if is_logo:
        return ft.Container(
            width=size,
            height=size,
            border_radius=999,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=glyph,
        )
    return glyph


def account_dropdown_option(
    account: Account,
    *,
    text: str | None = None,
    exchange_id: str = "",
) -> ft.DropdownOption:
    """Dropdown row for an account with its badge icon."""
    key = resolve_account_icon_key(account.icon, exchange_id)
    label = text if text is not None else f"{account.name} ({account.currency})"
    return ft.DropdownOption(
        key=account.id,
        text=label,
        leading_icon=_leading_from_account_icon(key),
    )


def account_dropdown_options(
    accounts: Sequence[Account],
    *,
    label_fn=None,
    exchange_ids: Optional[dict[str, str]] = None,
) -> list[ft.DropdownOption]:
    """Build options for every account in ``accounts``."""
    links = exchange_ids or {}
    out: list[ft.DropdownOption] = []
    for account in accounts:
        text = label_fn(account) if label_fn is not None else None
        out.append(
            account_dropdown_option(
                account,
                text=text,
                exchange_id=links.get(account.id, ""),
            )
        )
    return out


def icon_dropdown_option(
    key: str,
    text: str,
    icon: ft.IconData,
    *,
    icon_color: str | None = None,
) -> ft.DropdownOption:
    """Dropdown row with a Material leading icon."""
    return ft.DropdownOption(
        key=key,
        text=text,
        leading_icon=ft.Icon(
            icon,
            size=20,
            color=icon_color or ft.Colors.ON_SURFACE_VARIANT,
        ),
    )
