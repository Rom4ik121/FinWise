"""Accounts CRUD page with multi-currency display and icon/color pickers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.core.config import ACCOUNT_COLORS
from lib.domain.entities.account import Account
from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.exchange_connection import ExchangeConnection
from lib.domain.exchanges import EXCHANGES, exchange_title, get_exchange
from lib.presentation.account_icons import (
    account_icon_control,
    account_icon_groups,
    catalog_icon_control,
    exchange_icon_key,
    exchange_icon_keys,
    exchange_icon_src,
    icon_is_logo,
    is_valid_account_icon,
    resolve_account_icon_key,
)
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.count_up import play_count_ups
from lib.presentation.reload_gate import ReloadGate
from lib.presentation.ui_motion import replace_controls
from lib.presentation.money_input import make_amount_field, parse_amount
from lib.presentation.styles import (
    ICON_CATALOG_GLYPH,
    form_save_button,
    form_section,
    labeled_switch,
    section_title,
)
from lib.presentation.utils import (
    bind_dropdown_select,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    snack_exception,
    tr,
    user_facing_error,
)
from lib.presentation.widgets.account_card import AccountCard
from lib.presentation.widgets.appearance_picker import open_color_picker, open_icon_picker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.currency_ticker_picker import CurrencyTickerPicker
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import (
    build_form_shell,
    dismiss_fullscreen,
    open_fullscreen_form,
    push_overlay,
)
from lib.presentation.layout import make_v_scroll
from lib.presentation.widgets.loading import fill_loading, loading_indicator
from lib.presentation.widgets.transfer_sheet import open_transfer
if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


def _exchange_leading(spec) -> ft.Control:
    """Logo or fallback icon for an exchange row."""
    src = exchange_icon_src(spec.id)
    if src:
        return ft.Image(
            src=src,
            width=28,
            height=28,
            fit=ft.BoxFit.CONTAIN,
        )
    return ft.Icon(ft.Icons.TOKEN, size=24)

class AccountsPage(ft.Column):
    """List and manage accounts."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._token = -1
        self._links: dict[str, ExchangeConnection] = {}
        self._account_count = 0
        self._list = make_v_scroll(spacing=12)
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("nav.accounts", state.language),
                    body=self._list,
                    page=page,
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.refresh", state.language),
                            on_click=lambda _e: self._reload_gate.request(True),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.SWAP_HORIZ_ROUNDED,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("transaction.transfer", state.language),
                            on_click=lambda _e: open_transfer(page, state),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.add", state.language),
                            on_click=lambda _e: self._open_editor(),
                        ),
                    ],
                ),
                page=page,
            )
        )
        state.subscribe(self._on_state)
        self._reload_gate = ReloadGate(page, self, self.reload)
        self._reload_gate.request()

    def did_mount(self) -> None:
        super().did_mount()
        self._reload_gate.on_mounted()
        if self._state.pending_open_account_create:
            self._state.pending_open_account_create = False
            self._open_editor()

    def _on_state(self, state: "AppState") -> None:
        if state.accounts_token != self._token:
            self._reload_gate.request()

    async def reload(self, animate: bool = False) -> None:
        """Reload accounts and convert balances to base currency."""
        self._token = self._state.accounts_token
        lang = self._state.language
        fill_loading(self._list)
        safe_update(self._list)

        try:
            accounts = await self._state.container.list_accounts.execute()
            repo = getattr(self._state.container, "exchange_connection_repository", None)
            if repo is not None:
                links = await repo.list()
                self._links = {link.account_id: link for link in links}
            else:
                self._links = {}
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            self._list.controls = [EmptyState(tr("error.generic", lang))]
            safe_update(self._list)
            return

        if not accounts:
            self._account_count = 0
            self._list.controls = [
                EmptyState(
                    tr("empty.accounts", lang),
                    action_label=tr("action.add", lang),
                    on_action=lambda _e: self._open_editor(),
                )
            ]
            safe_update(self._list)
            return

        self._account_count = len(accounts)
        base = self._state.base_currency
        book = await load_rate_book(self._state.container)
        personal = [a for a in accounts if not a.is_corporate]
        corporate = [a for a in accounts if a.is_corporate]
        personal_cards: list[ft.Control] = []
        corporate_cards: list[ft.Control] = []
        fx_ok = True

        def _make_card(account: Account) -> AccountCard:
            nonlocal fx_ok
            converted = book.convert(
                account.balance,
                account.currency,
                base,
            )
            if converted is None and normalize_currency_code(
                account.currency
            ) != normalize_currency_code(base):
                fx_ok = False
            link = self._links.get(account.id)
            return AccountCard(
                account,
                base_currency=base,
                base_balance=converted,
                language=self._state.language,
                exchange_title=exchange_title(link.provider) if link else "",
                exchange_id=link.provider if link else "",
                page=self._page,
                on_click=self._open_stats,
                on_edit=self._open_editor,
                on_delete=self._confirm_delete,
                on_sync=self._sync_exchange if link else None,
                on_include_in_total=(
                    None if account.is_corporate else self._set_include_in_total
                ),
            )

        for account in personal:
            personal_cards.append(_make_card(account))
        for account in corporate:
            corporate_cards.append(_make_card(account))

        from lib.presentation.components.layout.grid import card_grid

        cards: list[ft.Control] = []
        cards.extend(card_grid(personal_cards, self._page))
        if corporate_cards:
            if personal_cards:
                cards.append(ft.Container(height=8, content=ft.Container()))
            cards.append(section_title(tr("account.corporate_section", lang)))
            cards.extend(card_grid(corporate_cards, self._page))

        if not personal and not corporate:
            self._list.controls = [
                EmptyState(
                    tr("empty.accounts", lang),
                    action_label=tr("action.add", lang),
                    on_action=lambda _e: self._open_editor(),
                )
            ]
            safe_update(self._list)
            return

        replace_controls(self._list, cards, self._page)
        if animate:
            await play_count_ups(self._list, self._page)
        if not fx_ok:
            snack(self._page, tr("fx.missing_rates", lang), error=True)

    def _open_stats(self, account: Account) -> None:
        self._state.open_secondary(f"account:{account.id}")

    def _set_include_in_total(self, account: Account, include: bool) -> None:
        """Persist home-total visibility without opening the editor."""

        async def _do() -> None:
            try:
                await self._state.container.update_account.execute(
                    account.model_copy(update={"include_in_total": include})
                )
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=self._state.language)
                await self.reload()
                return
            self._state.bump_refresh("dashboard", "accounts")

        run_async(self._page, _do)

    def _sync_exchange(self, account: Account) -> None:
        lang = self._state.language
        sync = getattr(self._state.container, "sync_exchange_account", None)
        if sync is None:
            snack(self._page, tr("error.exchange_unavailable", lang), error=True)
            return

        async def _do() -> None:
            try:
                result = await sync.execute(account.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh("dashboard", "accounts", "transactions", "budgets")
            snack(
                self._page,
                tr("account.sync.ok", lang, count=result.imported),
            )

        run_async(self._page, _do)

    def _confirm_delete(self, account: Account) -> None:
        lang = self._state.language

        async def _do() -> None:
            try:
                await self._state.container.delete_account.execute(account.id)
            except Exception as exc:  # noqa: BLE001
                snack_exception(self._page, exc, lang=lang)
                return
            self._state.bump_refresh("dashboard", "accounts", "transactions", "budgets")
            snack(self._page, tr("action.saved", lang))

        confirm_dialog(
            self._page,
            title=tr("action.confirm_delete", lang),
            message=account.name,
            confirm_text=tr("action.delete", lang),
            cancel_text=tr("action.cancel", lang),
            on_confirm=_do,
        )

    def _default_new_account_currency(self) -> str:
        """Device-suggested ticker when creating the very first account."""
        if self._account_count > 0:
            return normalize_currency_code(self._state.base_currency)
        try:
            from lib.infrastructure.services.locale_prefs import (
                suggested_currency_for_device,
            )

            return normalize_currency_code(
                suggested_currency_for_device(page=self._page)
            )
        except Exception:  # noqa: BLE001
            return normalize_currency_code(self._state.base_currency)

    def _open_editor(self, account: Optional[Account] = None) -> None:
        lang = self._state.language
        link = self._links.get(account.id) if account else None
        linked = link is not None
        is_exchange = {"value": linked}
        provider_id = {"value": link.provider if link else "binance"}
        initial_icon = account.icon if account else "wallet"
        if link is not None:
            initial_icon = resolve_account_icon_key(initial_icon, link.provider)
        if not is_valid_account_icon(initial_icon):
            initial_icon = "wallet"
        selected_icon = {"value": initial_icon}
        selected_color = {"value": account.color if account else ACCOUNT_COLORS[0]}

        busy = {"value": False}
        name_tf = ft.TextField(
            label=tr("field.name", lang),
            value=account.name if account else "",
            visible=not is_exchange["value"],
            border_radius=14,
            filled=True,
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(name_tf, "name")
        currency_picker = CurrencyTickerPicker(
            self._page,
            lang=lang,
            label=tr("field.currency", lang),
            value=normalize_currency_code(
                account.currency
                if account
                else self._default_new_account_currency()
            ),
            include_crypto=True,
            expand=True,
        )
        currency_picker.visible = not is_exchange["value"]
        balance_tf = make_amount_field(
            lang,
            label=tr("account.balance", lang),
            value=account.initial_balance if account else "0",
            disabled=account is not None,
        )
        api_key_tf = ft.TextField(
            label=tr("field.api_key", lang),
            value="",
            password=True,
            can_reveal_password=False,
            border_radius=14,
            filled=True,
        )
        secret_tf = ft.TextField(
            label=tr("field.api_secret", lang),
            value="",
            password=True,
            can_reveal_password=False,
            border_radius=14,
            filled=True,
        )
        passphrase_tf = ft.TextField(
            label=tr("field.api_passphrase", lang),
            value="",
            password=True,
            can_reveal_password=False,
            visible=False,
            border_radius=14,
            filled=True,
        )
        configure_field(api_key_tf, "password")
        configure_field(secret_tf, "password")
        configure_field(passphrase_tf, "password")
        wire_field_chain(
            self._page,
            [name_tf, balance_tf, api_key_tf, secret_tf, passphrase_tf],
        )
        exchange_hint = ft.Text(
            tr("account.exchange.hint", lang),
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=False,
        )
        keys_hint = ft.Text(
            tr("account.exchange.keys_hint", lang),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=False,
        )
        provider_title = ft.Text(
            (get_exchange(provider_id["value"]) or EXCHANGES[0]).title,
            size=14,
            weight=ft.FontWeight.W_600,
            expand=True,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        provider_leading = ft.Container(
            width=32,
            height=32,
            alignment=ft.Alignment.CENTER,
            content=_exchange_leading(
                get_exchange(provider_id["value"]) or EXCHANGES[0]
            ),
        )
        provider_pick = ft.Container(
            expand=True,
            border_radius=14,
            bgcolor=ft.Colors.SURFACE,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            ink=not linked,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    provider_leading,
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                tr("field.exchange", lang),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            provider_title,
                        ],
                    ),
                    ft.Icon(
                        ft.Icons.CHEVRON_RIGHT,
                        size=22,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
            ),
        )

        include_sw = ft.Switch(
            value=bool(account.include_in_total) if account else True,
        )
        corporate_sw = ft.Switch(
            value=bool(account.is_corporate) if account else False,
        )
        include_block = ft.Column(
            spacing=4,
            tight=True,
            controls=[
                labeled_switch(tr("account.include_in_total", lang), include_sw),
            ],
        )
        corporate_block = ft.Column(
            spacing=4,
            tight=True,
            controls=[
                labeled_switch(tr("account.corporate", lang), corporate_sw),
            ],
        )

        def _sync_corporate_ui(_e: ft.ControlEvent | None = None) -> None:
            is_corp = bool(corporate_sw.value)
            if is_corp:
                include_sw.value = False
            include_block.visible = not is_corp
            include_sw.disabled = is_corp
            safe_update(include_sw)
            safe_update(include_block)

        corporate_sw.on_change = _sync_corporate_ui
        _sync_corporate_ui()

        icon_preview = ft.Container(
            width=48,
            height=48,
            border_radius=24,
            alignment=ft.Alignment.CENTER,
            bgcolor=selected_color["value"],
            content=account_icon_control(
                selected_icon["value"],
                size=24,
                color=ICON_CATALOG_GLYPH,
            ),
        )
        color_preview = ft.Container(
            width=48,
            height=48,
            border_radius=24,
            bgcolor=selected_color["value"],
            border=ft.Border.all(2, ft.Colors.OUTLINE_VARIANT),
        )
        color_toggle_label = ft.Text(
            tr("picker.choose_color", lang),
            size=13,
            weight=ft.FontWeight.W_600,
            expand=True,
        )
        icon_toggle_label = ft.Text(
            tr("picker.choose_icon", lang),
            size=13,
            weight=ft.FontWeight.W_600,
            expand=True,
        )
        color_chevron = ft.Icon(ft.Icons.CHEVRON_RIGHT, size=22)
        icon_chevron = ft.Icon(ft.Icons.CHEVRON_RIGHT, size=22)

        def _refresh_previews() -> None:
            key = selected_icon["value"]
            logo = icon_is_logo(key)
            if logo:
                icon_preview.content = catalog_icon_control(
                    key,
                    tile_size=48,
                    glyph_size=24,
                    glyph_color=ICON_CATALOG_GLYPH,
                )
                icon_preview.bgcolor = None
                icon_preview.border_radius = 999
            else:
                icon_preview.content = account_icon_control(
                    key,
                    size=24,
                    color=ICON_CATALOG_GLYPH,
                )
                icon_preview.bgcolor = selected_color["value"]
                icon_preview.border_radius = 24
            color_preview.bgcolor = selected_color["value"]
            try:
                safe_update(icon_preview)
                safe_update(color_preview)
            except Exception:  # noqa: BLE001
                pass

        def _select_icon(key: str) -> None:
            selected_icon["value"] = key
            _refresh_previews()

        def _select_color(color: str) -> None:
            selected_color["value"] = color
            _refresh_previews()

        def _picker_icon(key: str) -> ft.Control:
            return catalog_icon_control(
                key,
                tile_size=48,
                glyph_size=22,
                glyph_color=ICON_CATALOG_GLYPH,
            )

        def _open_icons(_e: ft.ControlEvent | None = None) -> None:
            groups = (
                (("icon_group.exchanges", exchange_icon_keys()),)
                if is_exchange["value"]
                else account_icon_groups(include_exchanges=False)
            )
            open_icon_picker(
                self._page,
                lang=lang,
                groups=groups,
                selected=selected_icon["value"],
                on_select=_select_icon,
                render_icon=_picker_icon,
                overlay_key="account_icon_picker",
            )

        def _open_colors(_e: ft.ControlEvent | None = None) -> None:
            open_color_picker(
                self._page,
                lang=lang,
                colors=ACCOUNT_COLORS,
                selected=selected_color["value"],
                on_select=_select_color,
                overlay_key="account_color_picker",
            )

        _refresh_previews()

        def _current_spec():
            return get_exchange(str(provider_id["value"]))

        def _apply_provider(spec_id: str) -> None:
            spec = get_exchange(spec_id)
            if spec is None:
                return
            provider_id["value"] = spec.id
            provider_title.value = spec.title
            provider_leading.content = _exchange_leading(spec)
            if not linked:
                current_name = (name_tf.value or "").strip()
                known_titles = {item.title for item in EXCHANGES}
                if not current_name or current_name in known_titles:
                    name_tf.value = spec.title
                    try:
                        safe_update(name_tf)
                    except Exception:  # noqa: BLE001
                        pass
                selected_color["value"] = spec.color
                selected_icon["value"] = exchange_icon_key(spec.id)
                _refresh_previews()
            _refresh_credential_fields()
            try:
                safe_update(provider_title)
                safe_update(provider_leading)
                safe_update(provider_pick)
            except Exception:  # noqa: BLE001
                pass

        def _open_exchange_picker(_e: ft.ControlEvent | None = None) -> None:
            if linked or busy["value"]:
                return
            rows: list[ft.Control] = []
            for spec in EXCHANGES:
                selected = spec.id == provider_id["value"]
                rows.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=12),
                        border_radius=14,
                        bgcolor=(
                            ft.Colors.PRIMARY_CONTAINER
                            if selected
                            else ft.Colors.SURFACE_CONTAINER
                        ),
                        border=ft.Border.all(
                            1,
                            ft.Colors.PRIMARY
                            if selected
                            else ft.Colors.OUTLINE_VARIANT,
                        ),
                        ink=True,
                        on_click=lambda _ev, sid=spec.id: (
                            _apply_provider(sid),
                            dismiss_fullscreen(
                                self._page, key="exchange_picker"
                            ),
                        ),
                        content=ft.Row(
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                _exchange_leading(spec),
                                ft.Text(
                                    spec.title,
                                    expand=True,
                                    size=15,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Icon(
                                    ft.Icons.CHECK_CIRCLE,
                                    size=20,
                                    color=ft.Colors.PRIMARY,
                                    visible=selected,
                                ),
                            ],
                        ),
                    )
                )
            open_fullscreen_form(
                self._page,
                title=tr("field.exchange.pick", lang),
                lang=lang,
                overlay_key="exchange_picker",
                wrap_body=False,
                body=[
                    ft.Column(spacing=8, tight=True, controls=rows),
                ],
            )

        provider_pick.on_click = None if linked else _open_exchange_picker

        def _refresh_credential_fields() -> None:
            spec = _current_spec()
            if spec is not None and spec.uses_wallet:
                api_key_tf.label = tr("field.wallet_address", lang)
                secret_tf.label = tr("field.private_key", lang)
            else:
                api_key_tf.label = tr("field.api_key", lang)
                secret_tf.label = tr("field.api_secret", lang)
            passphrase_tf.visible = bool(spec is not None and spec.needs_passphrase)
            try:
                safe_update(api_key_tf)
                safe_update(secret_tf)
                safe_update(passphrase_tf)
            except Exception:  # noqa: BLE001
                pass

        def _apply_type_ui() -> None:
            exchange = is_exchange["value"]
            exchange_block.visible = exchange
            name_tf.visible = not exchange
            currency_picker.visible = not exchange
            balance_tf.visible = not exchange
            color_toggle.visible = not exchange
            icon_toggle.visible = not exchange
            try:
                safe_update(exchange_block)
                safe_update(name_tf)
                safe_update(currency_picker)
                safe_update(balance_tf)
                safe_update(color_toggle)
                safe_update(icon_toggle)
                safe_update(type_row)
            except Exception:  # noqa: BLE001
                pass
            sync = section_vis.get("fn")
            if sync is not None:
                sync()

        section_vis: dict = {"fn": None}

        def _type_chip(key: str, label: str) -> ft.Container:
            selected = is_exchange["value"] == (key == "exchange")
            locked = linked and key == "manual"
            return ft.Container(
                expand=True,
                height=36,
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                border_radius=12,
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else ft.Colors.SURFACE_CONTAINER,
                border=ft.Border.all(
                    1,
                    ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT,
                ),
                ink=not locked,
                on_click=None if locked else (lambda _e, k=key: _set_type(k)),
                content=ft.Text(
                    label,
                    size=12,
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.ON_PRIMARY_CONTAINER if selected else ft.Colors.ON_SURFACE,
                ),
            )

        def _rebuild_type_row() -> None:
            type_row.controls = [
                _type_chip("manual", tr("account.type.manual", lang)),
                _type_chip("exchange", tr("account.type.exchange", lang)),
            ]

        def _set_type(key: str) -> None:
            if linked or busy["value"]:
                return
            want_exchange = key == "exchange"
            if is_exchange["value"] == want_exchange:
                return
            is_exchange["value"] = want_exchange
            if want_exchange:
                spec = _current_spec()
                if spec is not None:
                    if not (name_tf.value or "").strip():
                        name_tf.value = spec.title
                    selected_color["value"] = spec.color
                    selected_icon["value"] = exchange_icon_key(spec.id)
                    _refresh_previews()
                if account is None:
                    currency_picker.set_value("USDT")
                try:
                    safe_update(name_tf)
                except Exception:  # noqa: BLE001
                    pass
            _rebuild_type_row()
            _refresh_credential_fields()
            _apply_type_ui()

        type_row = ft.Row(spacing=8, controls=[])
        _rebuild_type_row()
        exchange_block = ft.Column(
            spacing=10,
            tight=True,
            visible=is_exchange["value"],
            controls=[
                provider_pick,
                api_key_tf,
                secret_tf,
                passphrase_tf,
            ],
        )
        balance_tf.visible = not is_exchange["value"]
        _refresh_credential_fields()

        icon_toggle = ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            on_click=_open_icons,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    icon_preview,
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                tr("field.icon", lang),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            icon_toggle_label,
                        ],
                    ),
                    icon_chevron,
                ],
            ),
        )
        color_toggle = ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            on_click=_open_colors,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    color_preview,
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                tr("field.color", lang),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            color_toggle_label,
                        ],
                    ),
                    color_chevron,
                ],
            ),
        )
        color_toggle.visible = not is_exchange["value"]
        icon_toggle.visible = not is_exchange["value"]
        if is_exchange["value"]:
            spec = _current_spec()
            if spec is not None:
                selected_icon["value"] = exchange_icon_key(spec.id)
                _refresh_previews()

        save_label = ft.Text(tr("action.save", lang))
        save_btn = form_save_button(
            tr("action.save", lang),
            content=save_label,
            on_click=lambda e: _on_save_click(e),
        )
        close_btn = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_color=ft.Colors.ON_SURFACE,
            tooltip=tr("action.cancel", lang),
            on_click=lambda _e: _close_editor(),
        )

        def _set_busy(active: bool) -> None:
            busy["value"] = active
            save_btn.disabled = active
            close_btn.disabled = active
            provider_pick.ink = not (active or linked)
            provider_pick.on_click = (
                None if (active or linked) else _open_exchange_picker
            )
            api_key_tf.disabled = active
            secret_tf.disabled = active
            passphrase_tf.disabled = active
            save_label.value = tr("action.saving" if active else "action.save", lang)
            try:
                safe_update(save_label)
                safe_update(save_btn)
                safe_update(close_btn)
                safe_update(provider_pick)
                safe_update(api_key_tf)
                safe_update(secret_tf)
                safe_update(passphrase_tf)
            except Exception:  # noqa: BLE001
                pass

        def _on_save_click(_e: ft.ControlEvent | None = None) -> None:
            if busy["value"]:
                return
            _set_busy(True)
            run_async(self._page, _save, _e)

        async def _save(_e: ft.ControlEvent | None = None) -> None:
            def _fail(message: str) -> None:
                snack(self._page, message, error=True)
                _set_busy(False)

            try:
                initial = parse_amount(balance_tf.value or "0")
            except (InvalidOperation, ValueError):
                _fail(tr("invalid_amount", lang))
                return
            provider = str(provider_id["value"])
            if is_exchange["value"]:
                spec = get_exchange(provider)
                name = spec.title if spec else (name_tf.value or "").strip()
                if account is not None:
                    name = (account.name or "").strip() or name
                if not name:
                    _fail(tr("field.exchange", lang))
                    return
                if is_exchange["value"]:
                    selected_icon["value"] = exchange_icon_key(provider)
                currency = normalize_currency_code(
                    account.currency if account else "USDT"
                )
            else:
                name = (name_tf.value or "").strip()
                if not name:
                    _fail(tr("field.name", lang))
                    return
                currency = normalize_currency_code(currency_picker.value or "RUB")
            entity = Account(
                id=account.id if account else Account(name="tmp").id,
                name=name,
                currency=currency,
                balance=account.balance if account else initial,
                initial_balance=account.initial_balance if account else initial,
                icon=selected_icon["value"],
                color=selected_color["value"],
                is_active=account.is_active if account else True,
                include_in_total=(
                    False
                    if (bool(corporate_sw.value) and not is_exchange["value"])
                    else bool(include_sw.value)
                ),
                is_corporate=bool(corporate_sw.value) and not is_exchange["value"],
                created_at=account.created_at if account else Account(name="tmp").created_at,
            )
            try:
                if is_exchange["value"]:
                    connect = getattr(
                        self._state.container, "connect_exchange_account", None
                    )
                    sync = getattr(self._state.container, "sync_exchange_account", None)
                    if connect is None:
                        _fail(tr("error.exchange_unavailable", lang))
                        return
                    api_key = (api_key_tf.value or "").strip()
                    secret = (secret_tf.value or "").strip()
                    passphrase = (passphrase_tf.value or "").strip()
                    if account is None or api_key or secret:
                        if not api_key or not secret:
                            _fail(tr("field.api_key", lang))
                            return
                        if account is None:
                            entity.initial_balance = parse_amount("0")
                            entity.balance = parse_amount("0")
                        snack(self._page, tr("account.exchange.connecting", lang))
                        will_sync = sync is not None
                        saved = await connect.execute(
                            account=entity,
                            provider=provider,
                            api_key=api_key,
                            secret=secret,
                            passphrase=passphrase,
                            existing=account,
                            verify=not will_sync,
                        )
                        if will_sync:
                            await sync.execute(saved.id)
                    else:
                        await self._state.container.update_account.execute(entity)
                elif account:
                    await self._state.container.update_account.execute(entity)
                else:
                    await self._state.container.create_account.execute(entity)
                    get_settings = getattr(self._state.container, "get_settings", None)
                    if get_settings is not None:
                        try:
                            refreshed = await get_settings.execute()
                            self._state.set_settings(refreshed, notify=False)
                        except Exception:  # noqa: BLE001
                            pass
            except Exception as exc:  # noqa: BLE001
                detail = str(exc).strip()
                if detail.startswith("error.") or detail == "error.exchange_unavailable":
                    _fail(tr(detail, lang))
                else:
                    _fail(user_facing_error(exc, lang))
                return
            _close_editor(force=True)
            self._state.bump_refresh("dashboard", "accounts", "transactions", "budgets")
            snack(self._page, tr("action.saved", lang))

        title = tr("action.edit", lang) if account else tr("action.add", lang)
        page_w = getattr(self._page, "width", None) or None
        page_h = getattr(self._page, "height", None) or None
        type_section = form_section(
            tr("form.section.type", lang),
            [type_row],
            icon=ft.Icons.ACCOUNT_BALANCE_WALLET,
        )
        main_section = form_section(
            tr("form.section.main", lang),
            [name_tf, currency_picker, balance_tf],
            icon=ft.Icons.EDIT_NOTE,
        )
        exchange_section = form_section(
            tr("form.section.exchange", lang),
            [exchange_block],
            icon=ft.Icons.TOKEN,
        )
        appearance_section = form_section(
            tr("form.section.appearance", lang),
            [icon_toggle, color_toggle],
            icon=ft.Icons.PALETTE,
        )
        options_section = form_section(
            tr("form.section.options", lang),
            [corporate_block, include_block],
            icon=ft.Icons.TUNE,
        )

        def _sync_section_visibility() -> None:
            exchange = is_exchange["value"]
            main_section.visible = not exchange
            exchange_section.visible = exchange
            appearance_section.visible = not exchange
            # Corporate workspaces are manual-only (not exchange-linked).
            corporate_block.visible = not exchange
            if exchange:
                corporate_sw.value = False
                include_block.visible = True
                include_sw.disabled = False
            else:
                _sync_corporate_ui()
            try:
                safe_update(main_section)
                safe_update(exchange_section)
                safe_update(appearance_section)
                safe_update(corporate_block)
                safe_update(include_block)
            except Exception:  # noqa: BLE001
                pass

        _sync_section_visibility()
        section_vis["fn"] = _sync_section_visibility

        overlay = ft.Container(
            left=0,
            top=0,
            right=0,
            bottom=0,
            width=page_w,
            height=page_h,
            expand=True,
            bgcolor=ft.Colors.SURFACE,
            alignment=ft.Alignment.TOP_CENTER,
            content=build_form_shell(
                self._page,
                title=title,
                lang=lang,
                leading=close_btn,
                actions=[save_btn],
                wrap_body=False,
                body=[
                    type_section,
                    main_section,
                    exchange_section,
                    appearance_section,
                    options_section,
                ],
            ),
        )

        def _close_editor(
            _e: ft.ControlEvent | None = None, *, force: bool = False
        ) -> None:
            if busy["value"] and not force:
                return
            dismiss_fullscreen(self._page, key="account_icon_picker")
            dismiss_fullscreen(self._page, key="account_color_picker")
            currency_picker.close_overlay()
            dismiss_fullscreen(self._page, key="account_editor")

        dismiss_fullscreen(self._page, key="account_editor")
        overlay.data = "account_editor"
        push_overlay(self._page, overlay)

