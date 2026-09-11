"""CSV / bank statement import: map columns, preview, commit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.services.csv_statement import (
    PRESET_CUSTOM,
    PRESET_EN_BANK,
    PRESET_FINWISE,
    PRESET_RU_BANK,
    PRESET_SIMPLE,
    CsvMappedRow,
    mapping_from_headers,
)
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.file_transfer import pick_restore_bytes
from lib.presentation.layout import make_v_scroll
from lib.presentation.styles import card_surface, form_hint, muted_text
from lib.presentation.utils import format_date, format_money, run_async, safe_update, snack, snack_exception, tr
from lib.presentation.widgets.account_strip_picker import AccountStripPicker
from lib.presentation.widgets.empty_state import EmptyState

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState

_OPTIONAL = "__none__"
_FIELDS = ("date", "amount", "currency", "description", "account", "type")


class CsvImportPage(ft.Column):
    """Pick a CSV file, map columns, preview, then commit transactions."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._body = make_v_scroll(spacing=10)
        self._payload: bytes | None = None
        self._filename = ""
        self._headers: list[str] = []
        self._mapping: dict[str, str] = {}
        self._preset = PRESET_CUSTOM
        self._rows: list[CsvMappedRow] = []
        self._accounts: list = []
        self._account_id: Optional[str] = None
        lang = state.language
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("csv.import.title", lang),
                    body=self._body,
                    page=page,
                    extra=[form_hint(tr("csv.import.hint", lang), size=12)],
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.UPLOAD_FILE,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("csv.import.pick", lang),
                            on_click=lambda _e: run_async(page, self._pick),
                        ),
                    ],
                ),
                page=page,
            )
        )
        run_async(page, self._boot)

    async def _boot(self) -> None:
        try:
            self._accounts = await self._state.container.list_accounts.execute(
                active_only=True, corporate=False
            )
        except Exception:  # noqa: BLE001
            self._accounts = []
        if self._accounts:
            self._account_id = self._accounts[0].id
        self._render_idle()

    def _render_idle(self) -> None:
        lang = self._state.language
        self._body.controls = [
            EmptyState(
                tr("csv.import.pick", lang),
                icon=ft.Icons.TABLE_CHART_OUTLINED,
                hint=tr("csv.import.hint", lang),
                action_label=tr("csv.import.pick", lang),
                on_action=lambda _e: run_async(self._page, self._pick),
                page=self._page,
            )
        ]
        safe_update(self._body)

    async def _pick(self) -> None:
        lang = self._state.language
        try:
            picked = await pick_restore_bytes(
                self._page,
                title=tr("csv.import.pick", lang),
                extensions=["csv", "txt"],
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        if picked is None:
            return
        name, payload = picked
        if not payload:
            snack(self._page, tr("csv.import.none_valid", lang), error=True)
            return
        self._payload = payload
        self._filename = name
        preview = getattr(self._state.container, "preview_csv_import", None)
        if preview is None:
            snack(self._page, tr("error.generic", lang), error=True)
            return
        try:
            info, rows = await preview.execute(
                payload,
                default_currency=self._state.settings.default_currency,
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        self._headers = list(info.headers)
        self._preset = info.preset
        self._mapping = dict(info.mapping)
        self._rows = list(rows)
        self._render_mapped()

    def _header_options(self, *, optional: bool = False) -> list[ft.DropdownOption]:
        lang = self._state.language
        opts = []
        if optional:
            opts.append(
                ft.DropdownOption(key=_OPTIONAL, text=tr("csv.import.col.none", lang))
            )
        for header in self._headers:
            opts.append(ft.DropdownOption(key=header, text=header))
        return opts

    def _apply_preset(self, key: str) -> None:
        self._preset = key
        if key != PRESET_CUSTOM:
            self._mapping = mapping_from_headers(self._headers, preset=key)
        self._remap()

    def _remap(self) -> None:
        run_async(self._page, self._remap_async)

    async def _remap_async(self) -> None:
        if not self._payload:
            return
        preview = getattr(self._state.container, "preview_csv_import", None)
        if preview is None:
            return
        try:
            _info, rows = await preview.execute(
                self._payload,
                self._mapping,
                default_currency=self._state.settings.default_currency,
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        self._rows = list(rows)
        self._render_mapped()

    def _col_dropdown(self, field: str, *, optional: bool) -> ft.Dropdown:
        lang = self._state.language
        current = self._mapping.get(field) or (_OPTIONAL if optional else "")
        dd = ft.Dropdown(
            label=tr(f"csv.import.col.{field}", lang),
            value=current if current in {*_headers_or_none(self._headers, optional)} else (
                _OPTIONAL if optional else (self._headers[0] if self._headers else None)
            ),
            options=self._header_options(optional=optional),
            dense=True,
            expand=True,
        )

        def _on_change(_e: ft.ControlEvent) -> None:
            raw = dd.value or ""
            if raw == _OPTIONAL or not raw:
                self._mapping.pop(field, None)
            else:
                self._mapping[field] = raw
            self._preset = PRESET_CUSTOM
            self._remap()

        dd.on_change = _on_change
        return dd

    def _render_mapped(self) -> None:
        lang = self._state.language
        valid = [row for row in self._rows if row.ok]
        invalid = [row for row in self._rows if not row.ok]
        preset_dd = ft.Dropdown(
            label=tr("csv.import.preset", lang),
            value=self._preset,
            options=[
                ft.DropdownOption(key=PRESET_FINWISE, text=tr("csv.import.preset.finwise", lang)),
                ft.DropdownOption(key=PRESET_SIMPLE, text=tr("csv.import.preset.simple", lang)),
                ft.DropdownOption(key=PRESET_RU_BANK, text=tr("csv.import.preset.ru_bank", lang)),
                ft.DropdownOption(key=PRESET_EN_BANK, text=tr("csv.import.preset.en_bank", lang)),
                ft.DropdownOption(key=PRESET_CUSTOM, text=tr("csv.import.preset.custom", lang)),
            ],
            dense=True,
            on_change=lambda e: self._apply_preset(str(getattr(e.control, "value", "") or PRESET_CUSTOM)),
        )
        account_picker = None
        if self._accounts:
            account_picker = AccountStripPicker(
                self._page,
                self._accounts,
                lang=lang,
                value=self._account_id or self._accounts[0].id,
                on_changed=lambda aid: setattr(self, "_account_id", aid),
            )
        preview_rows: list[ft.Control] = []
        for row in self._rows[:20]:
            if row.ok:
                label = f"{format_date(row.date)} · {format_money(row.amount, row.currency)} · {row.description or '—'}"
                color = ft.Colors.ON_SURFACE
            else:
                label = tr("csv.import.invalid_row", lang, n=str(row.index))
                color = ft.Colors.ERROR
            preview_rows.append(ft.Text(label, size=12, color=color, max_lines=2))
        commit_btn = ft.FilledButton(
            tr("csv.import.commit", lang, count=str(len(valid))),
            icon=ft.Icons.DOWNLOAD_DONE,
            disabled=not valid or not self._accounts,
            on_click=lambda _e: run_async(self._page, self._commit),
        )
        controls: list[ft.Control] = [
            muted_text(self._filename, size=12),
            preset_dd,
            self._col_dropdown("date", optional=False),
            self._col_dropdown("amount", optional=False),
            self._col_dropdown("description", optional=True),
            self._col_dropdown("currency", optional=True),
            self._col_dropdown("account", optional=True),
            self._col_dropdown("type", optional=True),
        ]
        if account_picker is not None:
            controls.append(ft.Text(tr("csv.import.account", lang), size=12, weight=ft.FontWeight.W_600))
            controls.append(account_picker)
        controls.append(muted_text(tr("csv.import.preview", lang), size=13))
        if invalid:
            controls.append(
                muted_text(
                    f"{len(invalid)} / {len(self._rows)}",
                    size=11,
                )
            )
        controls.append(
            card_surface(
                ft.Column(spacing=4, tight=True, controls=preview_rows or [muted_text("—")]),
                padding=12,
            )
        )
        controls.append(commit_btn)
        self._body.controls = controls
        safe_update(self._body)

    async def _commit(self) -> None:
        lang = self._state.language
        uc = getattr(self._state.container, "commit_csv_import", None)
        if uc is None or not self._account_id:
            snack(self._page, tr("error.no_accounts", lang), error=True)
            return
        valid = [row for row in self._rows if row.ok]
        if not valid:
            snack(self._page, tr("csv.import.none_valid", lang), error=True)
            return
        try:
            created = await uc.execute(
                valid,
                account_id=self._account_id,
                default_currency=self._state.settings.default_currency,
                accounts=self._accounts,
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        self._state.bump_refresh("dashboard", "transactions", "accounts", "analytics", "budgets")
        snack(self._page, tr("csv.import.done", lang, count=str(len(created))))
        self._state.close_secondary()


def _headers_or_none(headers: list[str], optional: bool) -> set[str]:
    keys = set(headers)
    if optional:
        keys.add(_OPTIONAL)
    return keys
