"""Fullscreen PDF export options: period, accounts, sections."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import flet as ft

from lib.domain.entities.account import Account
from lib.infrastructure.services.export_service import PdfSectionFlags
from lib.presentation.analytics_period import (
    EXPORT_PERIOD_KEYS,
    resolve_export_period,
)
from lib.presentation.responsive import clamp_content_width
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import form_save_button, form_section, labeled_switch
from lib.presentation.theme import is_dark_mode
from lib.presentation.ui_motion import DUR_FAST, bind_press, motion_animation
from lib.presentation.utils import format_date, run_async, safe_update, snack, tr
from lib.presentation.widgets.date_time_field import DateTimeField
from lib.presentation.widgets.fullscreen_form import CloseFn, open_fullscreen_form

AccountScope = Literal["all", "personal", "corporate", "selected"]
_CHIP_SCALE = 1.03


@dataclass(frozen=True)
class PdfExportChoice:
    """Validated options from the export sheet."""

    period_key: str
    date_from: datetime | None
    date_to: datetime
    period_label: str
    account_scope: AccountScope
    account_ids: frozenset[str]
    sections: PdfSectionFlags


def _chip(
    label: str,
    *,
    selected: bool,
    on_click,
    dark: bool,
    page: ft.Page | None = None,
) -> ft.Container:
    skin = get_active_skin()
    chip = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=20,
        ink=True,
        bgcolor=skin.badge_bg(dark=dark) if selected else None,
        border=ft.Border.all(
            1,
            skin.primary_hex(dark=dark) if selected else ft.Colors.OUTLINE_VARIANT,
        ),
        scale=_CHIP_SCALE if selected else 1,
        animate_scale=motion_animation(DUR_FAST, page),
        on_click=on_click,
        content=ft.Text(
            label,
            size=12,
            weight=ft.FontWeight.W_600,
            no_wrap=True,
            color=skin.badge_fg(dark=dark) if selected else ft.Colors.ON_SURFACE_VARIANT,
        ),
    )
    bind_press(chip, haptic_kind="selection", page=page)
    return chip


def _tint_chip(chip: ft.Container, *, selected: bool, dark: bool) -> None:
    skin = get_active_skin()
    chip.bgcolor = skin.badge_bg(dark=dark) if selected else None
    chip.border = ft.Border.all(
        1,
        skin.primary_hex(dark=dark) if selected else ft.Colors.OUTLINE_VARIANT,
    )
    label = chip.content
    if isinstance(label, ft.Text):
        label.color = (
            skin.badge_fg(dark=dark) if selected else ft.Colors.ON_SURFACE_VARIANT
        )
    chip.scale = _CHIP_SCALE if selected else 1


def _end_of_local_day(dt: datetime) -> datetime:
    local = dt.astimezone()
    end = local.replace(hour=23, minute=59, second=59, microsecond=999999)
    return end.astimezone(timezone.utc)


def format_export_period_label(
    lang: str,
    key: str,
    date_from: datetime | None,
    date_to: datetime,
) -> str:
    if key == "custom" and date_from is not None:
        return (
            f"{format_date(date_from, with_time=False)}"
            f" — {format_date(date_to, with_time=False)}"
        )
    return tr(f"dashboard.period.{key}", lang)


def open_pdf_export_sheet(
    page: ft.Page,
    *,
    lang: str,
    accounts: Sequence[Account],
    on_export: Callable[[PdfExportChoice], Awaitable[None]],
    mode: Literal["global", "account"] = "global",
    locked_account: Account | None = None,
    default_period: str = "30d",
) -> CloseFn:
    """Show export settings and call ``on_export`` after validation."""
    now = datetime.now().astimezone()
    dark = is_dark_mode(page)
    period_key = default_period if default_period in EXPORT_PERIOD_KEYS else "30d"
    if period_key == "1d":
        period_key = "30d"
    scope: AccountScope = "all"
    if locked_account is not None:
        scope = "selected"

    period_chips: dict[str, ft.Container] = {}
    scope_chips: dict[str, ft.Container] = {}

    date_from_field = DateTimeField(
        page,
        lang=lang,
        label=tr("settings.export_date_from", lang),
        value=now - timedelta(days=30),
        with_time=False,
    )
    date_to_field = DateTimeField(
        page,
        lang=lang,
        label=tr("settings.export_date_to", lang),
        value=now,
        with_time=False,
    )
    custom_box = ft.Column(
        spacing=10,
        tight=True,
        visible=period_key == "custom",
        controls=[date_from_field, date_to_field],
    )

    def _set_period(key: str) -> None:
        nonlocal period_key
        changed = period_key != key
        period_key = key
        for item_key, chip in period_chips.items():
            _tint_chip(chip, selected=item_key == key, dark=dark)
            safe_update(chip)
        if not changed:
            return
        custom_box.visible = key == "custom"
        safe_update(custom_box)

    for key in EXPORT_PERIOD_KEYS:
        period_chips[key] = _chip(
            tr(f"dashboard.period.{key}", lang),
            selected=key == period_key,
            on_click=lambda _e, k=key: _set_period(k),
            dark=dark,
            page=page,
        )

    account_checks: dict[str, ft.Checkbox] = {}
    for account in accounts:
        if locked_account is not None and account.id != locked_account.id:
            continue
        account_checks[account.id] = ft.Checkbox(
            label=account.name,
            value=True,
        )
    accounts_box = ft.Column(
        spacing=2,
        tight=True,
        visible=mode == "global" and scope == "selected",
        controls=list(account_checks.values())
        or [
            ft.Text(
                tr("settings.export_need_account", lang),
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        ],
    )

    def _set_scope(next_scope: AccountScope) -> None:
        nonlocal scope
        changed = scope != next_scope
        scope = next_scope
        for item_key, chip in scope_chips.items():
            _tint_chip(chip, selected=item_key == next_scope, dark=dark)
            safe_update(chip)
        if not changed:
            return
        accounts_box.visible = next_scope == "selected"
        safe_update(accounts_box)

    if mode == "global":
        for key, label_key in (
            ("all", "settings.export_scope_all"),
            ("personal", "settings.export_scope_personal"),
            ("corporate", "settings.export_scope_corporate"),
            ("selected", "settings.export_scope_selected"),
        ):
            scope_chips[key] = _chip(
                tr(label_key, lang),
                selected=key == scope,
                on_click=lambda _e, k=key: _set_scope(k),
                dark=dark,
                page=page,
            )

    section_switches: dict[str, ft.Switch] = {
        "summary": ft.Switch(value=True),
        "accounts": ft.Switch(value=True),
        "transactions": ft.Switch(value=True),
        "categories": ft.Switch(value=True),
        "charts": ft.Switch(value=True),
        "goals": ft.Switch(value=True),
        "debts": ft.Switch(value=True),
        "subscriptions": ft.Switch(value=True),
    }
    if mode == "account":
        for name in ("accounts", "goals", "debts", "subscriptions"):
            section_switches[name].value = False

    def _section_row(key: str, label_key: str) -> ft.Control:
        return labeled_switch(tr(label_key, lang), section_switches[key])

    if mode == "account":
        section_controls = [
            _section_row("summary", "settings.export_section_summary"),
            _section_row("categories", "settings.export_section_categories"),
            _section_row("transactions", "settings.export_section_transactions"),
            _section_row("charts", "settings.export_section_charts"),
        ]
    else:
        section_controls = [
            _section_row("summary", "settings.export_section_summary"),
            _section_row("accounts", "settings.export_section_accounts"),
            _section_row("transactions", "settings.export_section_transactions"),
            _section_row("categories", "settings.export_section_categories"),
            _section_row("charts", "settings.export_section_charts"),
            _section_row("goals", "settings.export_section_goals"),
            _section_row("debts", "settings.export_section_debts"),
            _section_row("subscriptions", "settings.export_section_subscriptions"),
        ]

    body: list[ft.Control] = [
        form_section(
            tr("settings.export_period", lang),
            [
                ft.Row(
                    wrap=True,
                    spacing=8,
                    run_spacing=8,
                    controls=list(period_chips.values()),
                ),
                custom_box,
            ],
            icon=ft.Icons.DATE_RANGE_OUTLINED,
        ),
    ]
    if mode == "global":
        body.append(
            form_section(
                tr("settings.export_scope", lang),
                [
                    ft.Row(
                        wrap=True,
                        spacing=8,
                        run_spacing=8,
                        controls=list(scope_chips.values()),
                    ),
                    accounts_box,
                ],
                icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
            )
        )
    elif locked_account is not None:
        body.append(
            form_section(
                tr("settings.export_scope", lang),
                [
                    ft.Text(
                        locked_account.name,
                        size=15,
                        weight=ft.FontWeight.W_700,
                    )
                ],
                icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
            )
        )
    body.append(
        form_section(
            tr("settings.export_sections", lang),
            section_controls,
            icon=ft.Icons.TUNE,
        )
    )

    close_holder: dict[str, CloseFn] = {}
    busy = {"on": False}
    form_w = clamp_content_width(page, margin=28, max_width=560)
    status = ft.Text(
        "",
        size=12,
        color=ft.Colors.ON_SURFACE_VARIANT,
        text_align=ft.TextAlign.CENTER,
    )
    progress = ft.ProgressRing(width=18, height=18, stroke_width=2.5, visible=False)

    def _collect() -> PdfExportChoice | None:
        custom_from = date_from_field.value
        custom_to = date_to_field.value
        if period_key == "custom":
            if custom_from is None or custom_to is None:
                snack(page, tr("settings.export_need_period", lang), error=True)
                return None
            custom_to = _end_of_local_day(custom_to)
        try:
            cfg = resolve_export_period(
                period_key,
                datetime.now(timezone.utc),
                custom_from=custom_from,
                custom_to=custom_to,
            )
        except ValueError:
            snack(page, tr("settings.export_need_period", lang), error=True)
            return None

        chosen_scope = scope
        ids: set[str]
        if locked_account is not None:
            ids = {locked_account.id}
            chosen_scope = "selected"
        elif chosen_scope == "personal":
            ids = {a.id for a in accounts if not a.is_corporate}
        elif chosen_scope == "corporate":
            ids = {a.id for a in accounts if a.is_corporate}
        elif chosen_scope == "selected":
            ids = {aid for aid, box in account_checks.items() if box.value}
        else:
            ids = {a.id for a in accounts}
        if not ids:
            snack(page, tr("settings.export_need_account", lang), error=True)
            return None

        flags = PdfSectionFlags(
            summary=bool(section_switches["summary"].value),
            accounts=bool(section_switches["accounts"].value) and mode == "global",
            transactions=bool(section_switches["transactions"].value),
            categories=bool(section_switches["categories"].value),
            charts=bool(section_switches["charts"].value),
            goals=bool(section_switches["goals"].value) and mode == "global",
            debts=bool(section_switches["debts"].value) and mode == "global",
            subscriptions=bool(section_switches["subscriptions"].value)
            and mode == "global",
        )
        if not flags.any_body:
            snack(page, tr("settings.export_need_section", lang), error=True)
            return None

        date_to = cfg.date_to
        if period_key == "custom" and custom_to is not None:
            date_to = custom_to
        return PdfExportChoice(
            period_key=period_key,
            date_from=cfg.date_from,
            date_to=date_to,
            period_label=format_export_period_label(
                lang, period_key, cfg.date_from, date_to
            ),
            account_scope=chosen_scope,
            account_ids=frozenset(ids),
            sections=flags,
        )

    def _set_busy(on: bool) -> None:
        export_btn.disabled = on
        progress.visible = on
        status.value = tr("settings.export_pdf_working", lang) if on else ""
        safe_update(export_btn)
        safe_update(progress)
        safe_update(status)

    async def _save() -> None:
        if busy["on"]:
            return
        choice = _collect()
        if choice is None:
            return
        busy["on"] = True
        _set_busy(True)
        try:
            await on_export(choice)
        except Exception:  # noqa: BLE001
            busy["on"] = False
            _set_busy(False)
            return
        closer = close_holder.get("close")
        if closer is not None:
            closer()
        else:
            busy["on"] = False
            _set_busy(False)

    export_btn = form_save_button(
        tr("settings.export_pdf", lang),
        icon=ft.Icons.PICTURE_AS_PDF,
        on_click=lambda e: run_async(page, _save),
    )
    bind_press(export_btn, haptic_kind="light", page=page)
    try:
        export_btn.width = form_w
    except Exception:  # noqa: BLE001
        pass

    footer = ft.Container(
        padding=ft.Padding.only(left=14, right=14, top=10, bottom=14),
        border=ft.Border.only(
            top=ft.BorderSide(
                1, ft.Colors.with_opacity(0.35, ft.Colors.OUTLINE_VARIANT)
            )
        ),
        content=ft.Container(
            alignment=ft.Alignment.TOP_CENTER,
            content=ft.Container(
                width=form_w,
                content=ft.Column(
                    spacing=8,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Row(
                            spacing=8,
                            tight=True,
                            alignment=ft.MainAxisAlignment.CENTER,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[progress, status],
                        ),
                        export_btn,
                    ],
                ),
            ),
        ),
    )

    closer = open_fullscreen_form(
        page,
        title=tr(
            "account.export_pdf_title" if mode == "account" else "settings.export_pdf_title",
            lang,
        ),
        lang=lang,
        overlay_key="pdf_export_sheet",
        wrap_body=False,
        save_compact=True,
        save_icon=ft.Icons.PICTURE_AS_PDF,
        save_label=tr("settings.export_pdf", lang),
        footer=footer,
        body=body,
        on_save=_save,
    )
    close_holder["close"] = closer
    return closer
