"""Settings page: theme, language, currency, export, backup, PIN."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable, Optional, Sequence

import flet as ft

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.settings import AppSettings
from lib.domain.use_cases.align_currencies import align_sole_account_currency
from lib.infrastructure.services.backup_service import BackupService
from lib.infrastructure.services.biometric import BiometricResult, BiometricStatus
from lib.infrastructure.services.data_reset_service import DataResetService
from lib.infrastructure.services.encryption_service import EncryptionService
from lib.infrastructure.services.reminder_scheduler import schedule_reminders
from lib.infrastructure.services.localization import normalize_lang
from lib.infrastructure.services.push_notifier import (
    open_system_notification_settings,
    request_push_permissions,
)
from lib.presentation.dropdown_options import icon_dropdown_option
from lib.presentation.styles import (
    card_surface,
    form_hint,
    labeled_field,
    labeled_switch,
    polish_form_control,
    section_title,
)
from lib.presentation.theme import apply_theme_from_settings
from lib.presentation.skins import list_skins, normalize_skin_id, get_active_skin
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.utils import dropdown_select_kwargs, run_async, safe_update, snack, snack_exception, tr
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.currency_ticker_picker import CurrencyTickerPicker
if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


def _settings_section(
    title: str,
    icon: ft.IconData,
    controls: Sequence[ft.Control],
    *,
    expanded: bool = False,
    on_toggle: Optional[Callable[[ft.Container, bool], None]] = None,
) -> ft.Container:
    """Expandable card block with icon title (accordion-friendly)."""
    body = ft.Column(
        spacing=12,
        tight=True,
        visible=expanded,
        controls=list(controls),
    )
    chevron = ft.Icon(
        ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE,
        size=22,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    def _apply(open_: bool) -> None:
        body.visible = open_
        chevron.icon = ft.Icons.EXPAND_LESS if open_ else ft.Icons.EXPAND_MORE
        try:
            safe_update(body)
            safe_update(chevron)
        except Exception:  # noqa: BLE001
            pass

    def _toggle(_e: ft.ControlEvent | None = None) -> None:
        will_open = not body.visible
        if on_toggle is not None:
            on_toggle(section, will_open)
        else:
            _apply(will_open)

    header = ft.Container(
        ink=True,
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=2, vertical=2),
        on_click=_toggle,
        content=ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=34,
                    height=34,
                    border_radius=10,
                    bgcolor=get_active_skin().badge_bg(dark=True),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(
                        icon,
                        size=18,
                        color=get_active_skin().badge_fg(dark=True),
                    ),
                ),
                ft.Container(expand=True, content=section_title(title)),
                chevron,
            ],
        ),
    )
    section = card_surface(
        ft.Column(
            spacing=12,
            tight=True,
            controls=[header, body],
        ),
        padding=16,
    )
    section.data = {"apply": _apply, "body": body}
    return section


def _settings_divider() -> ft.Control:
    return ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT)


def _settings_subsection(title: str) -> ft.Control:
    return ft.Text(
        title,
        size=12,
        weight=ft.FontWeight.W_700,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


def _settings_nav_tile(
    label: str,
    icon: ft.IconData,
    on_click: Callable[[ft.ControlEvent], None],
) -> ft.Container:
    """Compact shortcut tile for secondary app screens."""
    skin = get_active_skin()
    return ft.Container(
        expand=True,
        ink=True,
        on_click=on_click,
        border_radius=14,
        padding=ft.Padding.symmetric(horizontal=10, vertical=14),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            tight=True,
            controls=[
                ft.Container(
                    width=40,
                    height=40,
                    border_radius=12,
                    bgcolor=skin.badge_bg(dark=True),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon, size=20, color=skin.badge_fg(dark=True)),
                ),
                ft.Text(
                    label,
                    size=12,
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        ),
    )


def _settings_nav_grid(pairs: Sequence[tuple[str, ft.IconData, Callable]]) -> ft.Control:
    """Two-column grid of navigation shortcuts."""
    rows: list[ft.Control] = []
    items = list(pairs)
    for i in range(0, len(items), 2):
        chunk = items[i : i + 2]
        row_controls: list[ft.Control] = []
        for label, icon, handler in chunk:
            row_controls.append(_settings_nav_tile(label, icon, handler))
        if len(chunk) == 1:
            row_controls.append(ft.Container(expand=True))
        rows.append(
            ft.Row(
                spacing=10,
                expand=True,
                controls=row_controls,
            )
        )
    return ft.Column(spacing=10, tight=True, controls=rows)


class SettingsPage(ft.Column):
    """Application preferences and data tools, grouped by section."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._sections: list[ft.Container] = []
        self._save_gen = 0

        s = state.settings
        lang = state.language

        def _accordion(section: ft.Container, will_open: bool) -> None:
            for item in self._sections:
                apply = (getattr(item, "data", None) or {}).get("apply")
                if callable(apply):
                    apply(item is section and will_open)

        def section(
            title: str,
            icon: ft.IconData,
            controls: Sequence[ft.Control],
            *,
            expanded: bool = False,
        ) -> ft.Container:
            block = _settings_section(
                title,
                icon,
                controls,
                expanded=expanded,
                on_toggle=_accordion,
            )
            self._sections.append(block)
            return block

        self._currency = CurrencyTickerPicker(
            page,
            lang=lang,
            label=tr("settings.default_currency", lang),
            value=normalize_currency_code(s.default_currency),
            include_crypto=True,
            expand=True,
            on_changed=lambda _code: self._autosave(),
        )
        self._theme = ft.Dropdown(
            label=tr("settings.theme", lang),
            value=s.theme,
            options=[
                icon_dropdown_option(
                    "light",
                    tr("settings.theme.light", lang),
                    ft.Icons.LIGHT_MODE,
                ),
                icon_dropdown_option(
                    "dark",
                    tr("settings.theme.dark", lang),
                    ft.Icons.DARK_MODE,
                ),
                icon_dropdown_option(
                    "system",
                    tr("settings.theme.system", lang),
                    ft.Icons.BRIGHTNESS_AUTO,
                ),
            ],
            expand=True,
            dense=True,
            **dropdown_select_kwargs(lambda _e: self._autosave()),
        )
        polish_form_control(self._theme)
        self._ui_style = normalize_skin_id(getattr(s, "ui_style", None))
        self._style_host = ft.Row(
            spacing=8,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[],
        )
        self._rebuild_style_cards(lang)
        self._language = ft.Dropdown(
            label=tr("settings.language", lang),
            value=normalize_lang(s.language),
            options=[
                icon_dropdown_option("ru", tr("lang.ru", lang), ft.Icons.LANGUAGE),
                icon_dropdown_option("en", tr("lang.en", lang), ft.Icons.LANGUAGE),
                icon_dropdown_option("uz", tr("lang.uz", lang), ft.Icons.LANGUAGE),
            ],
            expand=True,
            dense=True,
            **dropdown_select_kwargs(lambda _e: self._autosave()),
        )
        polish_form_control(self._language)
        self._interval = ft.TextField(
            value=str(s.exchange_update_interval_minutes),
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
            on_change=lambda _e: self._autosave_debounced(),
            on_blur=lambda _e: self._autosave(),
            on_submit=lambda _e: self._autosave(),
        )
        self._reminder_time = ft.TextField(
            value=s.reminder_time or "09:00",
            hint_text="09:00",
            expand=True,
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
            on_change=lambda _e: self._autosave_debounced(),
            on_blur=lambda _e: self._autosave(),
            on_submit=lambda _e: self._autosave(),
        )
        self._reminder_days = ft.TextField(
            value=str(getattr(s, "reminder_days", 3) or 3),
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
            on_change=lambda _e: self._autosave_debounced(),
            on_blur=lambda _e: self._autosave(),
            on_submit=lambda _e: self._autosave(),
        )
        from lib.presentation.form_keyboard import (
            configure_field,
            configure_pin_field,
            wire_field_chain,
        )

        configure_field(self._interval, "number")
        configure_field(self._reminder_time, "text")
        configure_field(self._reminder_days, "number")
        wire_field_chain(
            page, [self._interval, self._reminder_time, self._reminder_days]
        )
        self._notifications = ft.Switch(
            value=s.notifications_enabled,
            on_change=lambda e: self._on_notifications_toggle(e),
        )
        self._debt_reminders = ft.Switch(
            value=s.debt_reminders,
            on_change=lambda _e: self._autosave(),
        )
        self._sub_reminders = ft.Switch(
            value=s.subscription_reminders,
            on_change=lambda _e: self._autosave(),
        )
        self._check_balance_sub = ft.Switch(
            value=bool(getattr(s, "check_balance_before_subscription", True)),
            on_change=lambda _e: self._autosave(),
        )
        self._goal_milestones = ft.Switch(
            value=s.goal_milestones,
            on_change=lambda _e: self._autosave(),
        )
        self._budget_alerts = ft.Switch(
            value=bool(getattr(s, "budget_alerts", True)),
            on_change=lambda _e: self._autosave(),
        )
        self._biometric = ft.Switch(
            value=s.biometric_enabled,
            on_change=lambda e: run_async(page, self._on_biometric_toggle, e),
        )
        self._biometric_hint = ft.Text(
            "",
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        from lib.infrastructure.services.biometric import feature_biometrics_available

        if not feature_biometrics_available():
            self._biometric.disabled = True
            self._biometric.value = False
            self._biometric_hint.value = tr("settings.biometric_unsupported", lang)

        self._pin_tf = ft.TextField(
            password=True,
            can_reveal_password=False,
            expand=True,
            max_length=8,
            keyboard_type=ft.KeyboardType.NUMBER,
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
        )
        configure_pin_field(self._pin_tf)
        wire_field_chain(page, [self._pin_tf])

        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=12),
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        )

        def _open_secondary(route: str) -> Callable[[ft.ControlEvent], None]:
            return lambda _e: state.open_secondary(route)

        scroll_body = ft.ListView(
            expand=True,
            spacing=14,
            padding=ft.Padding.only(bottom=104),
            auto_scroll=False,
            controls=[
                section(
                    tr("settings.basics", lang),
                    ft.Icons.TUNE_OUTLINED,
                    [
                        self._language,
                        self._currency,
                        form_hint(tr("settings.currency_hint", lang)),
                        labeled_field(
                            tr("settings.exchange_interval", lang), self._interval
                        ),
                    ],
                    expanded=True,
                ),
                section(
                    tr("settings.appearance", lang),
                    ft.Icons.PALETTE_OUTLINED,
                    [
                        ft.Text(
                            tr("settings.style", lang),
                            size=13,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        self._style_host,
                        form_hint(tr("settings.style.hint", lang)),
                        self._theme,
                    ],
                ),
                section(
                    tr("settings.notifications", lang),
                    ft.Icons.NOTIFICATIONS_OUTLINED,
                    [
                        labeled_switch(
                            tr("settings.notifications_enable", lang),
                            self._notifications,
                        ),
                        _settings_divider(),
                        _settings_subsection(tr("settings.notifications_reminders", lang)),
                        labeled_switch(
                            tr("settings.debt_reminders", lang), self._debt_reminders
                        ),
                        labeled_switch(
                            tr("settings.subscription_reminders", lang),
                            self._sub_reminders,
                        ),
                        _settings_divider(),
                        _settings_subsection(tr("settings.notifications_alerts", lang)),
                        labeled_switch(
                            tr("settings.goal_milestones", lang), self._goal_milestones
                        ),
                        labeled_switch(
                            tr("settings.budget_alerts", lang), self._budget_alerts
                        ),
                        labeled_switch(
                            tr("settings.check_balance_before_subscription", lang),
                            self._check_balance_sub,
                        ),
                        _settings_divider(),
                        _settings_subsection(tr("settings.notifications_schedule", lang)),
                        labeled_field(
                            tr("settings.reminder_time", lang), self._reminder_time
                        ),
                        labeled_field(
                            tr("settings.reminder_days", lang), self._reminder_days
                        ),
                        ft.TextButton(
                            tr("settings.notifications_open_settings", lang),
                            icon=ft.Icons.SETTINGS_OUTLINED,
                            on_click=lambda _e: run_async(
                                page, self._open_notification_settings
                            ),
                        ),
                    ],
                ),
                section(
                    tr("settings.security", lang),
                    ft.Icons.SECURITY,
                    [
                        _settings_subsection(tr("settings.security_pin", lang)),
                        form_hint(tr("settings.pin_hint", lang)),
                        labeled_field(tr("settings.pin", lang), self._pin_tf),
                        ft.Row(
                            spacing=8,
                            wrap=True,
                            controls=[
                                ft.FilledTonalButton(
                                    tr("settings.set_pin", lang),
                                    icon=ft.Icons.LOCK_OUTLINE,
                                    style=btn_style,
                                    on_click=lambda _e: self.set_pin(),
                                ),
                                ft.TextButton(
                                    tr("settings.clear_pin", lang),
                                    icon=ft.Icons.LOCK_OPEN,
                                    on_click=lambda _e: run_async(
                                        page, self.clear_pin
                                    ),
                                ),
                            ],
                        ),
                        _settings_divider(),
                        _settings_subsection(tr("settings.security_biometric", lang)),
                        labeled_switch(tr("settings.biometric", lang), self._biometric),
                        self._biometric_hint,
                    ],
                ),
                section(
                    tr("settings.sections", lang),
                    ft.Icons.APPS_OUTLINED,
                    [
                        form_hint(tr("settings.sections_hint", lang)),
                        _settings_nav_grid(
                            [
                                (tr("nav.goals", lang), ft.Icons.FLAG_OUTLINED, _open_secondary("goals")),
                                (tr("nav.debts", lang), ft.Icons.CREDIT_SCORE, _open_secondary("debts")),
                                (
                                    tr("nav.subscriptions", lang),
                                    ft.Icons.EVENT_REPEAT,
                                    _open_secondary("subscriptions"),
                                ),
                                (
                                    tr("nav.currencies", lang),
                                    ft.Icons.CURRENCY_EXCHANGE,
                                    _open_secondary("currencies"),
                                ),
                                (
                                    tr("nav.budgets", lang),
                                    ft.Icons.PIE_CHART,
                                    _open_secondary("budgets"),
                                ),
                            ]
                        ),
                    ],
                ),
                section(
                    tr("settings.data", lang),
                    ft.Icons.STORAGE_OUTLINED,
                    [
                        _settings_subsection(tr("settings.export", lang)),
                        form_hint(tr("settings.export_hint", lang)),
                        ft.FilledButton(
                            tr("settings.export_pdf_open", lang),
                            icon=ft.Icons.PICTURE_AS_PDF,
                            style=btn_style,
                            on_click=lambda _e: run_async(
                                page, self.open_pdf_export
                            ),
                        ),
                        _settings_divider(),
                        _settings_subsection(tr("settings.backup_restore", lang)),
                        form_hint(tr("settings.daily_backup_hint", lang)),
                        form_hint(tr("settings.share_backup_hint", lang)),
                        ft.Row(
                            wrap=True,
                            spacing=8,
                            run_spacing=8,
                            controls=[
                                ft.OutlinedButton(
                                    tr("action.backup", lang),
                                    icon=ft.Icons.BACKUP,
                                    style=btn_style,
                                    on_click=lambda _e: run_async(
                                        page, self.backup
                                    ),
                                ),
                                ft.OutlinedButton(
                                    tr("action.restore", lang),
                                    icon=ft.Icons.SETTINGS_BACKUP_RESTORE,
                                    style=btn_style,
                                    on_click=lambda _e: run_async(
                                        page, self.restore_latest
                                    ),
                                ),
                            ],
                        ),
                    ],
                ),
                section(
                    tr("settings.danger", lang),
                    ft.Icons.WARNING_AMBER_OUTLINED,
                    [
                        ft.Container(
                            padding=12,
                            border_radius=12,
                            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ERROR),
                            border=ft.Border.all(
                                1, ft.Colors.with_opacity(0.25, ft.Colors.ERROR)
                            ),
                            content=ft.Column(
                                spacing=12,
                                tight=True,
                                controls=[
                                    ft.Text(
                                        tr("settings.delete_all_confirm", lang),
                                        size=12,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    ft.FilledButton(
                                        tr("settings.delete_all_data", lang),
                                        icon=ft.Icons.DELETE_FOREVER,
                                        style=ft.ButtonStyle(
                                            bgcolor=ft.Colors.ERROR,
                                            color=ft.Colors.ON_ERROR,
                                            shape=ft.RoundedRectangleBorder(radius=12),
                                            padding=ft.Padding.symmetric(
                                                horizontal=16, vertical=12
                                            ),
                                        ),
                                        on_click=lambda _e: self._confirm_wipe(),
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ],
        )

        super().__init__(
            **page_column(
                page_frame(
                    title=tr("nav.settings", lang),
                    body=scroll_body,
                    page=page,
                ),
                page=page,
            )
        )
        self._sync_notification_controls()
        run_async(page, self._refresh_biometric_hint)

    def _rebuild_style_cards(self, lang: str) -> None:
        """Refresh compact style chips after a selection change."""
        self._style_host.controls = [
            self._style_preview_card(skin, skin.id == self._ui_style, lang)
            for skin in list_skins()
        ]

    def _style_preview_card(self, skin, selected: bool, lang: str) -> ft.Container:
        """One-line style chip: color dots + name (matches dropdown density)."""

        def _select(_e: ft.ControlEvent, skin_id: str = skin.id) -> None:
            self._ui_style = skin_id
            self._rebuild_style_cards(self._state.language)
            try:
                safe_update(self._style_host)
            except Exception:  # noqa: BLE001
                pass
            self._autosave()

        border = skin.dark_primary if selected else skin.dark_border
        return ft.Container(
            expand=True,
            height=44,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            bgcolor=skin.dark_surface,
            border=ft.Border.all(1.5 if selected else 1, border),
            ink=True,
            on_click=_select,
            content=ft.Row(
                spacing=8,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=10,
                        height=10,
                        border_radius=3,
                        bgcolor=skin.dark_primary,
                    ),
                    ft.Container(
                        width=10,
                        height=10,
                        border_radius=3,
                        bgcolor=skin.dark_expense,
                    ),
                    ft.Text(
                        tr(f"settings.style.{skin.id}", lang),
                        size=13,
                        weight=ft.FontWeight.W_700 if selected else ft.FontWeight.W_500,
                        color=skin.dark_text,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                    *(
                        [
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE,
                                size=16,
                                color=skin.dark_primary,
                            )
                        ]
                        if selected
                        else []
                    ),
                ],
            ),
        )

    def _notification_sub_controls(self) -> list[ft.Control]:
        return [
            self._debt_reminders,
            self._sub_reminders,
            self._check_balance_sub,
            self._goal_milestones,
            self._budget_alerts,
            self._reminder_time,
            self._reminder_days,
        ]

    def _sync_notification_controls(self) -> None:
        """Disable sub-options when the master notifications switch is off."""
        enabled = bool(self._notifications.value)
        for ctrl in self._notification_sub_controls():
            ctrl.disabled = not enabled
            try:
                safe_update(ctrl)
            except Exception:  # noqa: BLE001
                pass

    def _on_notifications_toggle(self, e: ft.ControlEvent) -> None:
        if bool(getattr(e.control, "value", False)):
            if not any(
                bool(getattr(ctrl, "value", False))
                for ctrl in (
                    self._debt_reminders,
                    self._sub_reminders,
                    self._goal_milestones,
                    self._budget_alerts,
                )
            ):
                self._debt_reminders.value = True
                self._sub_reminders.value = True
                self._goal_milestones.value = True
                self._budget_alerts.value = True
            run_async(self._page, request_push_permissions)
        self._sync_notification_controls()
        self._autosave()

    def _hint_for_status(self, status: BiometricStatus) -> str:
        lang = self._state.language
        if status is BiometricStatus.AVAILABLE:
            return tr("settings.biometric_hint_ok", lang)
        if status is BiometricStatus.DEVICE_NOT_PRESENT:
            return tr("settings.biometric_hint_missing", lang)
        if status is BiometricStatus.NOT_CONFIGURED:
            return tr("settings.biometric_hint_unconfigured", lang)
        if status is BiometricStatus.UNSUPPORTED:
            return tr("settings.biometric_unsupported", lang)
        if status is BiometricStatus.DISABLED_BY_POLICY:
            return tr("lock.biometric_policy", lang)
        if status is BiometricStatus.DEVICE_BUSY:
            return tr("lock.biometric_busy", lang)
        return tr("settings.biometric_unsupported", lang)

    async def _refresh_biometric_hint(self) -> None:
        crypto = self._state.container.encryption_service or EncryptionService()
        status = await crypto.refresh_biometric_status()
        self._biometric_hint.value = self._hint_for_status(status)
        try:
            safe_update(self._biometric_hint)
        except Exception:  # noqa: BLE001
            pass

    async def _on_biometric_toggle(self, e: ft.ControlEvent) -> None:
        lang = self._state.language
        enabled = bool(getattr(e.control, "value", False))
        if not enabled:
            await self.save(silent=True)
            return
        if getattr(self, "_bio_toggle_busy", False):
            return
        self._bio_toggle_busy = True
        try:
            await self._enable_biometric(lang)
        finally:
            self._bio_toggle_busy = False

    async def _enable_biometric(self, lang: str) -> None:
        get_pin = getattr(self._state.container, "get_pin_credentials", None)
        has_pin = False
        if get_pin is not None:
            pin_hash, pin_salt, _ = await get_pin.execute()
            has_pin = bool(pin_hash and pin_salt)
        if not has_pin:
            self._biometric.value = False
            try:
                safe_update(self._biometric)
            except Exception:  # noqa: BLE001
                pass
            snack(self._page, tr("settings.biometric_need_pin", lang), error=True)
            return
        crypto = self._state.container.encryption_service or EncryptionService()
        status = await crypto.refresh_biometric_status()
        self._biometric_hint.value = self._hint_for_status(status)
        try:
            safe_update(self._biometric_hint)
        except Exception:  # noqa: BLE001
            pass
        if status is not BiometricStatus.AVAILABLE:
            self._biometric.value = False
            try:
                safe_update(self._biometric)
            except Exception:  # noqa: BLE001
                pass
            snack(self._page, self._hint_for_status(status), error=True)
            return
        result = await crypto.authenticate_biometric(
            message=tr("lock.biometric_prompt", lang),
        )
        if result is not BiometricResult.VERIFIED:
            self._biometric.value = False
            try:
                safe_update(self._biometric)
            except Exception:  # noqa: BLE001
                pass
            if result is BiometricResult.CANCELED:
                snack(self._page, tr("lock.biometric_canceled", lang), error=True)
            else:
                snack(self._page, tr("lock.biometric_failed", lang), error=True)
            return
        snack(self._page, tr("settings.biometric_confirmed", lang))
        await self.save(silent=True)

    def _autosave(self, _e: ft.ControlEvent | None = None) -> None:
        self._save_gen += 1
        run_async(self._page, self.save, True)

    def _autosave_debounced(self, _e: ft.ControlEvent | None = None) -> None:
        self._save_gen += 1
        gen = self._save_gen

        async def _wait() -> None:
            await asyncio.sleep(0.5)
            if gen != self._save_gen:
                return
            await self.save(silent=True)

        run_async(self._page, _wait)

    async def save(self, silent: bool = False) -> None:
        """Persist settings via use case and apply theme/language."""
        lang = self._state.language
        try:
            interval = int(self._interval.value or 60)
        except ValueError:
            interval = 60
        new_currency = normalize_currency_code(self._currency.value or "RUB")
        previous_currency = normalize_currency_code(
            self._state.settings.default_currency
        )
        previous_language = normalize_lang(self._state.settings.language)
        previous_theme = self._state.theme_mode
        previous_style = normalize_skin_id(getattr(self._state.settings, "ui_style", None))
        previous_notifications = bool(self._state.settings.notifications_enabled)
        try:
            reminder_days = int(self._reminder_days.value or 3)
        except ValueError:
            reminder_days = 3
        try:
            settings = AppSettings(
                id=self._state.settings.id,
                default_currency=new_currency,
                theme=self._theme.value or "system",
                ui_style=self._ui_style,
                language=normalize_lang(self._language.value or "ru"),
                exchange_update_interval_minutes=max(5, interval),
                notifications_enabled=bool(self._notifications.value),
                subscription_reminders=bool(self._sub_reminders.value),
                debt_reminders=bool(self._debt_reminders.value),
                goal_milestones=bool(self._goal_milestones.value),
                budget_alerts=bool(self._budget_alerts.value),
                low_balance_threshold=self._state.settings.low_balance_threshold,
                reminder_time=(self._reminder_time.value or "09:00").strip(),
                reminder_days=max(0, min(365, reminder_days)),
                check_balance_before_subscription=bool(self._check_balance_sub.value),
                biometric_enabled=bool(self._biometric.value),
                dashboard_hide_chart=bool(
                    getattr(self._state.settings, "dashboard_hide_chart", False)
                ),
                dashboard_chart_days=int(
                    getattr(self._state.settings, "dashboard_chart_days", 30) or 30
                ),
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return
        try:
            saved = await self._state.container.update_settings.execute(settings)
            get_pin = getattr(self._state.container, "get_pin_credentials", None)
            set_pin = getattr(self._state.container, "set_pin_credentials", None)
            if get_pin is not None and set_pin is not None:
                pin_hash, pin_salt, _ = await get_pin.execute()
                if bool(self._biometric.value) and not (pin_hash and pin_salt):
                    snack(
                        self._page,
                        tr("settings.biometric_need_pin", lang),
                        error=True,
                    )
                    self._biometric.value = False
                    try:
                        safe_update(self._biometric)
                    except Exception:  # noqa: BLE001
                        pass
                    saved = await self._state.container.update_settings.execute(
                        saved.model_copy(update={"biometric_enabled": False})
                    )
                elif pin_hash and pin_salt:
                    await set_pin.execute(
                        pin_hash,
                        pin_salt,
                        biometric_enabled=saved.biometric_enabled,
                    )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return

        # Keep the sole cash account in sync with the display currency.
        try:
            if new_currency != previous_currency:
                await self._migrate_account_currencies(previous_currency, new_currency)
            await align_sole_account_currency(self._state.container)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
        if new_currency != previous_currency:
            uc = self._state.container.update_exchange_rates
            if uc is not None:
                try:
                    await uc.execute(base=new_currency)
                except Exception:  # noqa: BLE001
                    pass

        self._state.set_settings(saved)
        apply_theme_from_settings(self._page, saved)
        if saved.notifications_enabled:
            try:
                granted = await request_push_permissions()
                if granted and not previous_notifications:
                    from lib.infrastructure.services.push_notifier import notify_push_ready

                    await notify_push_ready(normalize_lang(saved.language))
                elif not granted:
                    snack(
                        self._page,
                        tr("settings.notifications_denied", lang),
                        error=True,
                    )
            except Exception:  # noqa: BLE001
                pass
        created = await schedule_reminders(
            self._state.container,
            saved,
            language=normalize_lang(saved.language),
        )
        if created:
            # OS push is emitted from NotificationService.push; refresh home banners.
            self._state.bump_refresh("dashboard")
        if (
            previous_theme != saved.theme
            or previous_language != saved.language
            or previous_style != saved.ui_style
        ):
            self._state.request_view_rebuild()
        elif new_currency != previous_currency:
            self._state.bump_refresh()
        if not silent:
            self._page.update()
            snack(self._page, tr("action.saved", saved.language))
        else:
            from lib.presentation.haptics import haptic

            haptic("selection")

    async def _migrate_account_currencies(self, old: str, new: str) -> None:
        """Retarget accounts/txs still on the previous default currency.

        Typical case: user created a RUB cash account, then switched the app
        display currency to UZS — keep labels consistent without FX conversion
        of amounts (amounts stay as entered).
        """
        c = self._state.container
        if c.list_accounts is None or c.update_account is None:
            return
        accounts = await c.list_accounts.execute(active_only=False)
        for account in accounts:
            if normalize_currency_code(account.currency) != old:
                continue
            updated = account.model_copy(update={"currency": new})
            await c.update_account.execute(updated)
            if c.list_transactions is None or c.update_transaction is None:
                continue
            from lib.presentation.tx_query import fetch_transactions_paged

            txs = await fetch_transactions_paged(
                c.list_transactions, account_id=account.id
            )
            for tx in txs:
                if normalize_currency_code(tx.currency) != old:
                    continue
                await c.update_transaction.execute(
                    tx.model_copy(update={"currency": new})
                )

    def _io_error_snack(self, exc: Exception) -> None:
        lang = self._state.language
        snack_exception(self._page, exc, lang=lang)

    async def open_pdf_export(self) -> None:
        """Open the configured PDF report sheet."""
        lang = self._state.language
        try:
            accounts = await self._state.container.list_accounts.execute()
        except Exception as exc:  # noqa: BLE001
            self._io_error_snack(exc)
            return
        from lib.presentation.widgets.pdf_export_sheet import open_pdf_export_sheet

        try:
            open_pdf_export_sheet(
                self._page,
                lang=lang,
                accounts=accounts,
                mode="global",
                on_export=self._run_pdf_export,
            )
        except Exception as exc:  # noqa: BLE001
            self._io_error_snack(exc)

    async def _run_pdf_export(self, choice) -> None:
        from lib.presentation.pdf_export import export_configured_pdf

        try:
            path = await export_configured_pdf(
                self._state.container,
                choice,
                language=self._state.language,
            )
            await self._offer_file(path, kind="PDF")
        except Exception as exc:  # noqa: BLE001
            self._io_error_snack(exc)
            raise

    async def _open_notification_settings(self) -> None:
        lang = self._state.language
        ok = await open_system_notification_settings(self._page)
        if not ok:
            snack(
                self._page,
                tr("settings.notifications_settings_failed", lang),
                error=True,
            )

    async def backup(self) -> None:
        try:
            path = BackupService(self._state.container.config).backup(bundle=True)
            await self._offer_file(path, kind="Backup")
        except Exception as exc:  # noqa: BLE001
            self._io_error_snack(exc)

    async def _offer_file(self, path, *, kind: str, extra=None) -> None:
        from lib.presentation.file_transfer import offer_saved_file

        lang = self._state.language
        try:
            location = await offer_saved_file(
                self._page, path, title=f"FinWise {kind}", extra=extra
            )
        except OSError:
            snack(self._page, tr("settings.file_denied", lang), error=True)
            return
        if not location:
            snack(self._page, tr("settings.file_cancelled", lang), error=True)
            return
        from lib.infrastructure.services.biometric import is_mobile_platform

        if is_mobile_platform(self._page):
            snack(self._page, tr("settings.file_shared", lang).format(kind=kind))
            return
        snack(self._page, tr("settings.file_ready", lang).format(kind=kind, path=location))

    async def restore_latest(self) -> None:
        lang = self._state.language
        from lib.infrastructure.services.biometric import is_mobile_platform
        from lib.presentation.file_transfer import pick_restore_bytes

        service = BackupService(self._state.container.config)
        if is_mobile_platform(self._page):
            from lib.presentation.file_transfer import classify_restore_payload

            picked = await pick_restore_bytes(
                self._page,
                title=tr("action.restore", lang),
                extensions=[
                    "fwbackup",
                    "db",
                    "sqlite",
                    "sqlite3",
                    "json",
                    "fwexport",
                ],
            )
            if not picked:
                backups = service.list_backups()
                if not backups:
                    snack(self._page, tr("settings.no_backups", lang), error=True)
                    return
                await self._confirm_restore(backups[0])
                return
            name, payload = picked
            kind = classify_restore_payload(name, payload)
            if kind == "enc":
                await self._decrypt_export_payload(name, payload)
                return
            if kind == "json":
                snack(self._page, tr("settings.restore_need_db", lang), error=True)
                return
            if kind == "fwbackup":
                if not name.lower().endswith(".fwbackup"):
                    name = f"{name}.fwbackup"
                target = service.backup_dir / name
                service.backup_dir.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                await self._confirm_restore(target, payload=payload)
                return
            if kind != "db":
                snack(self._page, tr("settings.restore_bad_file", lang), error=True)
                return
            if not name.lower().endswith((".db", ".sqlite", ".sqlite3")):
                name = f"{name}.db"
            target = service.backup_dir / name
            service.backup_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            await self._confirm_restore(target)
            return
        backups = service.list_backups()
        if not backups:
            snack(self._page, tr("settings.no_backups", lang), error=True)
            return
        await self._confirm_restore(backups[0])

    async def _confirm_restore(self, backup_path, *, payload: bytes | None = None) -> None:
        lang = self._state.language
        from lib.infrastructure.services.backup_service import bundle_needs_password

        password = ""
        needs_pw = False
        try:
            needs_pw = bundle_needs_password(payload if payload is not None else backup_path)
        except Exception:  # noqa: BLE001
            needs_pw = False
        if needs_pw:
            entered = await self._prompt_secret(
                title=tr("settings.restore_bundle_password", lang),
                label=tr("settings.export_password", lang),
            )
            if entered is None:
                return
            password = entered
        confirm_dialog(
            self._page,
            title=tr("action.restore", lang),
            message=tr("settings.restore_confirm", lang),
            confirm_text=tr("action.restore", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=lambda: self._do_restore(backup_path, password=password),
        )

    async def _prompt_secret(self, *, title: str, label: str) -> str | None:
        pwd = ft.TextField(
            label=label,
            password=True,
            can_reveal_password=False,
            autofocus=True,
        )
        done: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()

        def _close(password: str | None) -> None:
            dlg.open = False
            safe_update(self._page)
            if not done.done():
                done.set_result(password)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=pwd,
            actions=[
                ft.TextButton(
                    tr("action.cancel", self._state.language),
                    on_click=lambda _e: _close(None),
                ),
                ft.FilledButton(
                    tr("action.restore", self._state.language),
                    on_click=lambda _e: _close((pwd.value or "").strip()),
                ),
            ],
        )
        self._page.overlay.append(dlg)
        dlg.open = True
        safe_update(self._page)
        password = await done
        try:
            self._page.overlay.remove(dlg)
        except ValueError:
            pass
        safe_update(self._page)
        return password

    async def _decrypt_export_payload(self, name: str, payload: bytes) -> None:
        """Decrypt a ``.fwexport`` blob to a JSON file in the export dir."""
        from pathlib import Path

        from lib.domain.use_cases.export_data import decrypt_export_blob
        from lib.presentation.file_transfer import safe_filename

        lang = self._state.language
        password = await self._prompt_secret(
            title=tr("settings.export_json_encrypted", lang),
            label=tr("settings.export_password", lang),
        )
        if password is None:
            return
        try:
            raw = decrypt_export_blob(payload, password)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        export_dir = Path(self._state.container.config.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        base = safe_filename(name, default="export.fwexport")
        if base.lower().endswith(".fwexport"):
            base = base[: -len(".fwexport")] + ".json"
        elif not base.lower().endswith(".json"):
            base = f"{base}.json"
        out = export_dir / base
        out.write_bytes(raw)
        await self._offer_file(out, kind="JSON")

    async def _do_restore(self, backup_path, *, password: str = "") -> None:
        """Replace the live DB, rebind sessions, and reload settings."""
        import asyncio
        from pathlib import Path

        from lib.core.database import get_session_factory, reset_engine

        c = self._state.container
        path = Path(backup_path)
        secret = password
        try:
            # Release SQLite file locks before overwriting on Windows.
            await asyncio.to_thread(reset_engine)
            await asyncio.to_thread(
                lambda: BackupService(c.config).restore(
                    path, make_safety_copy=False, password=secret
                )
            )
            factory = get_session_factory(c.config)
            c.rebind_session_factory(factory)
            if c.get_settings is not None:
                settings = await c.get_settings.execute()
                self._state.set_settings(settings, notify=False)
                apply_theme_from_settings(self._page, settings)
            await self._state.reload_pin_gate(
                lock_if_present=True,
                unlock_if_absent=True,
                notify=False,
            )
            self._state.request_view_rebuild()
            self._state.bump_refresh()
            self._page.update()
            if self._state.pin_hash and not self._state.is_unlocked:
                snack(self._page, tr("settings.restore_locked", self._state.language))
            else:
                snack(self._page, tr("settings.restore_done", self._state.language))
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)

    def set_pin(self) -> None:
        """Hash PIN and persist credentials via use case."""
        lang = self._state.language
        pin = (self._pin_tf.value or "").strip()
        if len(pin) < 4 or not pin.isdigit():
            snack(self._page, tr("settings.pin_digits", lang), error=True)
            return
        try:
            creds = EncryptionService().hash_pin(pin)
        except ValueError:
            snack(self._page, tr("settings.pin_digits", lang), error=True)
            return
        self._pin_tf.value = ""
        safe_update(self._pin_tf)

        async def _persist() -> None:
            set_pin = getattr(self._state.container, "set_pin_credentials", None)
            if set_pin is None:
                snack(self._page, tr("error.generic", lang), error=True)
                return
            try:
                await set_pin.execute(
                    creds.pin_hash,
                    creds.pin_salt,
                    biometric_enabled=bool(self._biometric.value),
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            snack(self._page, tr("settings.pin_saved_detail", lang))
            await self._state.reload_pin_gate(notify=False)

        run_async(self._page, _persist)

    async def clear_pin(self) -> None:
        """Remove PIN lock credentials and disable biometric unlock."""
        lang = self._state.language
        clear_pin = getattr(self._state.container, "clear_pin_credentials", None)
        if clear_pin is None:
            snack(self._page, tr("error.generic", lang), error=True)
            return
        try:
            settings = await clear_pin.execute()
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return
        self._biometric.value = False
        try:
            safe_update(self._biometric)
        except Exception:  # noqa: BLE001
            pass
        self._state.set_settings(settings, notify=False)
        await self._state.reload_pin_gate(unlock_if_absent=True, notify=False)
        snack(self._page, tr("settings.pin_cleared", lang))

    def _confirm_wipe(self) -> None:
        lang = self._state.language
        confirm_dialog(
            self._page,
            title=tr("settings.delete_all_data", lang),
            message=tr("settings.delete_all_confirm", lang),
            confirm_text=tr("action.delete", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=self.wipe_all_data,
        )

    async def wipe_all_data(self) -> None:
        """Erase every table, then recreate defaults (settings / currencies / cash)."""
        import asyncio
        from pathlib import Path

        from lib.core.database import get_session_factory

        lang = self._state.language
        c = self._state.container
        try:
            await asyncio.to_thread(
                DataResetService(c.config).wipe_all,
                get_session_factory(c.config),
            )
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=lang)
            return

        # Recreate defaults so the app stays usable.
        try:
            currencies_path = (
                Path(__file__).resolve().parents[3]
                / "assets"
                / "data"
                / "currencies.json"
            )
            seed = getattr(c, "seed_currencies", None)
            if seed is not None and currencies_path.exists():
                await seed.execute(currencies_path)
            if c.get_settings is not None:
                settings = await c.get_settings.execute()
                self._state.set_settings(settings, notify=False)
                apply_theme_from_settings(self._page, settings)
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            return

        self._state.request_view_rebuild()
        self._state.bump_refresh()
        await self._state.reload_pin_gate(unlock_if_absent=True, notify=False)
        self._page.update()
        snack(self._page, tr("settings.delete_all_done", lang))
