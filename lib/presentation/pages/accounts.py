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
    crypto_icon_src,
    exchange_icon_key,
    exchange_icon_keys,
    exchange_icon_src,
    exchange_logo_fills_badge,
    is_valid_account_icon,
    parse_currency_icon_key,
    parse_exchange_icon_key,
    resolve_account_icon_key,
)
from lib.presentation.money_input import make_amount_field, parse_amount
from lib.presentation.styles import ICON_CATALOG_GLYPH, page_header
from lib.presentation.utils import (
    bind_dropdown_select,
    load_rate_book,
    run_async,
    safe_update,
    snack,
    tr,
)
from lib.presentation.widgets.account_card import AccountCard
from lib.presentation.widgets.appearance_picker import open_color_picker, open_icon_picker
from lib.presentation.widgets.confirm_dialog import confirm_dialog
from lib.presentation.widgets.currency_ticker_picker import CurrencyTickerPicker
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.fullscreen_form import dismiss_fullscreen
from lib.presentation.layout import make_v_scroll
from lib.presentation.widgets.loading import fill_loading, loading_indicator
from lib.presentation.widgets.transfer_sheet import open_transfer
if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


class AccountsPage(ft.Column):
    """List and manage accounts."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._token = -1
        self._links: dict[str, ExchangeConnection] = {}
        self._list = make_v_scroll(spacing=12)
        super().__init__(
            expand=True,
            controls=[
                page_header(
                    tr("nav.accounts", state.language),
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("action.refresh", state.language),
                            on_click=lambda _e: run_async(page, self.reload),
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
                ft.Container(
                    expand=True,
                    padding=ft.Padding.symmetric(horizontal=12),
                    content=self._list,
                ),
            ],
        )
        state.subscribe(self._on_state)
        run_async(page, self.reload)

    def _on_state(self, state: "AppState") -> None:
        if state.accounts_token != self._token:
            run_async(self._page, self.reload)

    async def reload(self) -> None:
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
            snack(self._page, str(exc), error=True)
            self._list.controls = [EmptyState(tr("error.generic", lang))]
            safe_update(self._list)
            return

        if not accounts:
            self._list.controls = [
                EmptyState(
                    tr("empty.accounts", lang),
                    action_label=tr("action.add", lang),
                    on_action=lambda _e: self._open_editor(),
                )
            ]
            safe_update(self._list)
            return

        base = self._state.base_currency
        book = await load_rate_book(self._state.container)
        cards: list[ft.Control] = []
        for account in accounts:
            converted = book.convert(
                account.balance,
                account.currency,
                base,
            )
            link = self._links.get(account.id)
            cards.append(
                AccountCard(
                    account,
                    base_currency=base,
                    base_balance=converted,
                    language=self._state.language,
                    exchange_title=exchange_title(link.provider) if link else "",
                    exchange_id=link.provider if link else "",
                    on_click=self._open_stats,
                    on_edit=self._open_editor,
                    on_delete=self._confirm_delete,
                    on_sync=self._sync_exchange if link else None,
                )
            )
        self._list.controls = cards
        safe_update(self._list)

    def _open_stats(self, account: Account) -> None:
        self._state.open_secondary(f"account:{account.id}")

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
                snack(
                    self._page,
                    tr("error.sync_failed", lang, detail=str(exc)[:240]),
                    error=True,
                )
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
            await self._state.container.delete_account.execute(account.id)
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
        )
        currency_picker = CurrencyTickerPicker(
            self._page,
            lang=lang,
            label=tr("field.currency", lang),
            value=normalize_currency_code(
                account.currency if account else self._state.base_currency
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
            can_reveal_password=True,
        )
        secret_tf = ft.TextField(
            label=tr("field.api_secret", lang),
            value="",
            password=True,
            can_reveal_password=True,
        )
        passphrase_tf = ft.TextField(
            label=tr("field.api_passphrase", lang),
            value="",
            password=True,
            can_reveal_password=True,
            visible=False,
        )
        exchange_hint = ft.Text(
            tr("account.exchange.hint", lang),
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        keys_hint = ft.Text(
            tr("account.exchange.keys_hint", lang),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        provider_dd = ft.Dropdown(
            label=tr("field.exchange", lang),
            value=provider_id["value"],
            disabled=linked,
            options=[
                ft.DropdownOption(key=spec.id, text=spec.title) for spec in EXCHANGES
            ],
            expand=True,
        )

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
            exchange_id = parse_exchange_icon_key(key)
            fills = bool(
                exchange_id
                and exchange_icon_src(exchange_id)
                and exchange_logo_fills_badge(exchange_id)
            )
            icon_preview.content = account_icon_control(
                key,
                size=48 if fills else 24,
                color=ICON_CATALOG_GLYPH,
            )
            icon_preview.bgcolor = None if fills else selected_color["value"]
            color_preview.bgcolor = selected_color["value"]
            try:
                icon_preview.update()
                color_preview.update()
            except Exception:  # noqa: BLE001
                pass

        def _select_icon(key: str) -> None:
            selected_icon["value"] = key
            _refresh_previews()

        def _select_color(color: str) -> None:
            selected_color["value"] = color
            _refresh_previews()

        def _picker_icon(key: str) -> ft.Control:
            code = parse_currency_icon_key(key)
            logo = bool(
                parse_exchange_icon_key(key)
                or (code and crypto_icon_src(code))
            )
            return account_icon_control(
                key,
                size=36 if logo else 22,
                color=ICON_CATALOG_GLYPH,
            )

        def _open_icons(_e: ft.ControlEvent | None = None) -> None:
            groups = (
                (("icon_group.exchanges", exchange_icon_keys()),)
                if is_exchange["value"]
                else account_icon_groups()
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
            return get_exchange(str(provider_dd.value or provider_id["value"]))

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
                api_key_tf.update()
                secret_tf.update()
                passphrase_tf.update()
            except Exception:  # noqa: BLE001
                pass

        def _apply_type_ui() -> None:
            exchange = is_exchange["value"]
            exchange_block.visible = exchange
            name_tf.visible = not exchange
            currency_picker.visible = not exchange
            balance_tf.visible = not exchange
            color_toggle.visible = not exchange
            try:
                exchange_block.update()
                name_tf.update()
                currency_picker.update()
                balance_tf.update()
                color_toggle.update()
                type_row.update()
            except Exception:  # noqa: BLE001
                pass

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
                    name_tf.update()
                except Exception:  # noqa: BLE001
                    pass
            _rebuild_type_row()
            _refresh_credential_fields()
            _apply_type_ui()

        def _on_provider(_e: ft.ControlEvent | None = None) -> None:
            spec = _current_spec()
            provider_id["value"] = spec.id if spec else "binance"
            if spec is not None and not linked:
                current_name = (name_tf.value or "").strip()
                known_titles = {item.title for item in EXCHANGES}
                if not current_name or current_name in known_titles:
                    name_tf.value = spec.title
                    try:
                        name_tf.update()
                    except Exception:  # noqa: BLE001
                        pass
                selected_color["value"] = spec.color
                current_icon = selected_icon["value"]
                if current_icon in {"wallet", "token"} or parse_exchange_icon_key(
                    current_icon
                ):
                    selected_icon["value"] = exchange_icon_key(spec.id)
                _refresh_previews()
            _refresh_credential_fields()

        bind_dropdown_select(provider_dd, _on_provider)
        type_row = ft.Row(spacing=8, controls=[])
        _rebuild_type_row()
        exchange_block = ft.Column(
            spacing=10,
            tight=True,
            visible=is_exchange["value"],
            controls=[
                exchange_hint,
                provider_dd,
                api_key_tf,
                secret_tf,
                passphrase_tf,
                keys_hint,
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

        save_label = ft.Text(tr("action.save", lang))
        save_btn = ft.FilledButton(
            content=save_label,
            icon=ft.Icons.CHECK,
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
            provider_dd.disabled = active or linked
            api_key_tf.disabled = active
            secret_tf.disabled = active
            passphrase_tf.disabled = active
            save_label.value = tr("action.saving" if active else "action.save", lang)
            try:
                save_label.update()
                save_btn.update()
                close_btn.update()
                provider_dd.update()
                api_key_tf.update()
                secret_tf.update()
                passphrase_tf.update()
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
            provider = str(provider_dd.value or provider_id["value"])
            if is_exchange["value"]:
                spec = get_exchange(provider)
                name = spec.title if spec else (name_tf.value or "").strip()
                if account is not None:
                    name = (account.name or "").strip() or name
                if not name:
                    _fail(tr("field.exchange", lang))
                    return
                currency = normalize_currency_code(
                    account.currency if account else "USDT"
                )
                if selected_icon["value"] in {"wallet", "token"}:
                    selected_icon["value"] = exchange_icon_key(provider)
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
            except Exception as exc:  # noqa: BLE001
                _fail(str(exc))
                return
            _close_editor(force=True)
            self._state.bump_refresh("dashboard", "accounts", "transactions", "budgets")
            snack(self._page, tr("action.saved", lang))

        title = tr("action.edit", lang) if account else tr("action.add", lang)
        overlay = ft.Container(
            left=0,
            top=0,
            right=0,
            bottom=0,
            bgcolor=ft.Colors.SURFACE,
            content=ft.SafeArea(
                expand=True,
                content=ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        page_header(
                            title,
                            leading=close_btn,
                            actions=[save_btn],
                        ),
                        ft.Container(
                            expand=True,
                            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                            content=ft.Column(
                                expand=True,
                                spacing=12,
                                scroll=ft.ScrollMode.HIDDEN,
                                controls=[
                                    type_row,
                                    name_tf,
                                    currency_picker,
                                    balance_tf,
                                    exchange_block,
                                    icon_toggle,
                                    color_toggle,
                                    ft.Container(height=24),
                                ],
                            ),
                        ),
                    ],
                ),
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
            try:
                if overlay in self._page.overlay:
                    self._page.overlay.remove(overlay)
                self._page.update()
            except Exception:  # noqa: BLE001
                pass

        # Drop any previous fullscreen account editor.
        for item in list(self._page.overlay):
            if getattr(item, "data", None) == "account_editor":
                try:
                    self._page.overlay.remove(item)
                except Exception:  # noqa: BLE001
                    pass
        overlay.data = "account_editor"
        self._page.overlay.append(overlay)
        self._page.update()

