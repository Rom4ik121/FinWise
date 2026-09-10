"""Finanse Flet application shell and navigation."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import flet as ft

from lib.infrastructure.services.encryption_service import EncryptionService
from lib.presentation.views import (
    AccountDetailPage,
    AccountsPage,
    AnalyticsPage,
    BudgetsPage,
    CurrenciesPage,
    DashboardPage,
    DebtsPage,
    GoalsPage,
    SettingsPage,
    SubscriptionsPage,
    TransactionsPage,
)
from lib.presentation.skins import get_active_skin
from lib.presentation.state.app_state import AppState
from lib.presentation.styles import glass_layer
from lib.presentation.theme import apply_theme_from_settings, is_dark_mode
from lib.presentation.utils import snack, tr
from lib.presentation.widgets.lock_screen import LockScreen

logger = logging.getLogger("finanse.presentation.app")

_NAV_RADIUS = 22
_NAV_MARGIN = ft.Margin.only(left=10, right=10, bottom=6, top=4)
_NAV_PILL_W = 46.0
_NAV_PILL_H = 30.0
_NAV_BAR_H = 54.0
_NAV_SLIDE = ft.Animation(380, ft.AnimationCurve.EASE_IN_OUT_CUBIC)
_BACKGROUND_LOCK_SECONDS = 15.0

# iOS sends ``inactive`` for Face ID, Control Center, and app-switch
# transitions. That is NOT backgrounding — treating it as hide locked the
# app immediately and also started the 15s timer at the wrong moment.
_BACKGROUND_LIFECYCLE = frozenset(
    {"pause", "paused", "hide", "hidden", "detach", "detached"}
)
_FOREGROUND_LIFECYCLE = frozenset(
    {"resume", "resumed", "show", "shown", "restart", "restarted"}
)


def lifecycle_token(event: Any) -> str:
    """Normalize Flet/Flutter lifecycle payload to a short token."""
    state = getattr(event, "data", None) or getattr(event, "state", None)
    raw = str(getattr(state, "value", state) or "").strip().lower()
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    return raw



class FinanseApp:
    """Root UI controller: floating NavigationBar shell + secondary routes."""

    def __init__(self, page: ft.Page, container: Any) -> None:
        self.page = page
        self.state = AppState(container)
        self._content = ft.AnimatedSwitcher(
            content=ft.Container(expand=True),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=420,
            reverse_duration=260,
            switch_in_curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            switch_out_curve=ft.AnimationCurve.EASE_IN,
            expand=True,
        )
        self._nav = ft.Row(
            spacing=0,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[],
        )
        # Sliding selection pill: flex spacers keep it centered in the active slot
        # (no pixel math — that broke when host width was unknown).
        self._nav_indicator = ft.Container(
            width=_NAV_PILL_W,
            height=_NAV_PILL_H,
            border_radius=14,
            bgcolor=ft.Colors.TRANSPARENT,
            animate=_NAV_SLIDE,
        )
        self._nav_slide_lead = ft.Container(expand=0, animate=_NAV_SLIDE)
        self._nav_slide_trail = ft.Container(expand=3, animate=_NAV_SLIDE)
        self._nav_slide_slot = ft.Container(
            expand=1,
            alignment=ft.Alignment.CENTER,
            content=self._nav_indicator,
            animate=_NAV_SLIDE,
        )
        self._nav_stack = ft.Stack(
            height=_NAV_BAR_H,
            clip_behavior=ft.ClipBehavior.NONE,
            controls=[
                ft.Container(
                    left=0,
                    right=0,
                    top=6,
                    height=_NAV_PILL_H,
                    content=ft.Row(
                        spacing=0,
                        controls=[
                            self._nav_slide_lead,
                            self._nav_slide_slot,
                            self._nav_slide_trail,
                        ],
                    ),
                ),
                ft.Container(
                    left=0,
                    right=0,
                    top=0,
                    bottom=0,
                    content=self._nav,
                ),
            ],
        )
        self._nav_host = ft.Container(
            margin=_NAV_MARGIN,
            border_radius=_NAV_RADIUS,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            animate=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=22,
                color="#00000033",
                offset=ft.Offset(0, 6),
            ),
            content=ft.Container(
                padding=ft.Padding.only(top=4, bottom=4),
                content=self._nav_stack,
            ),
        )
        self._shell = ft.SafeArea(
            expand=True,
            avoid_intrusions_top=True,
            avoid_intrusions_left=True,
            avoid_intrusions_right=True,
            avoid_intrusions_bottom=True,
            minimum_padding=ft.Padding.only(top=8, bottom=4, left=0, right=0),
            maintain_bottom_view_padding=True,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[self._content, self._nav_host],
            ),
        )
        self._stage = ft.Container(expand=True, content=self._shell)
        self._nav_pills: list[ft.Container] = []
        self._nav_icons: list[ft.Icon] = []
        self._nav_labels: list[ft.Text] = []
        self._rendered_tab: Optional[int] = None
        self._rendered_secondary: Optional[str] = None
        self._rendered_lang: Optional[str] = None
        self._rendered_unlocked: Optional[bool] = None
        self._rendered_rebuild_token: int = -1
        self._primary_cache: dict[int, ft.Control] = {}
        self._secondary_cache: dict[str, ft.Control] = {}
        self._active_view: Optional[ft.Control] = None
        self._backgrounded_at: float | None = None
        self._push_prompted: bool = False

    async def start(self) -> None:
        """Load settings, apply theme, and mount the shell."""
        page = self.page
        page.title = "FinWise"
        page.padding = 0
        # Custom floating nav — do not use scaffold NavigationBar.
        page.navigation_bar = None
        try:
            from pathlib import Path

            icon_ico = Path(__file__).resolve().parents[2] / "assets" / "icon.ico"
            if icon_ico.is_file():
                page.window.icon = str(icon_ico)
            page.window.min_width = 320
            page.window.min_height = 560
            # Comfortable default desktop size (still mobile-friendly layout).
            if getattr(page.window, "width", None) in (None, 0):
                page.window.width = 420
                page.window.height = 780
        except Exception:  # noqa: BLE001
            pass

        try:
            settings = await self.state.container.get_settings.execute()
            self.state.set_settings(settings, notify=False)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load settings; using defaults")

        apply_theme_from_settings(page, self.state.settings)
        await self._load_pin_gate()
        self._build_navigation_bar()
        self.state.subscribe(self._on_state_changed)

        from lib.infrastructure.services.biometric import register_local_auth_service
        from lib.infrastructure.services.push_notifier import register_android_notifications

        # Platform is reliable after the first frame; retry native plugins.
        register_local_auth_service(page)
        register_android_notifications(page)

        # Swap splash → shell in one step so Flutter never paints a blank frame.
        if len(page.controls) == 1:
            page.controls[0] = self._stage
        else:
            page.controls.clear()
            page.add(self._stage)
        from lib.presentation.ui_feedback import bind_ui_feedback

        bind_ui_feedback(page)
        self._render(force=True)
        self._flush_notifications()
        self._install_session_lock()

    def _install_session_lock(self) -> None:
        """Lock after the app stays backgrounded for ``_BACKGROUND_LOCK_SECONDS``."""
        from lib.infrastructure.services.biometric import is_mobile_platform

        if not is_mobile_platform(self.page):
            return
        previous = self.page.on_app_lifecycle_state_change

        def _on_lifecycle(e: Any) -> None:
            if callable(previous):
                try:
                    previous(e)
                except Exception:  # noqa: BLE001
                    logger.exception("Previous lifecycle handler failed")
            state_token = lifecycle_token(e)
            if state_token in _BACKGROUND_LIFECYCLE:
                if self._backgrounded_at is None:
                    self._backgrounded_at = time.monotonic()
                return
            if state_token in _FOREGROUND_LIFECYCLE:
                if not self._push_prompted:
                    self._push_prompted = True
                    self._ask_notification_permission()
                started = self._backgrounded_at
                self._backgrounded_at = None
                if started is None:
                    return
                elapsed = time.monotonic() - started
                if elapsed < _BACKGROUND_LOCK_SECONDS:
                    return
                self.lock_session()

        self.page.on_app_lifecycle_state_change = _on_lifecycle

    def _ask_notification_permission(self) -> None:
        """Ask iOS/Android for alerts after the window is active."""
        try:
            from lib.infrastructure.services.push_notifier import request_push_permissions
            from lib.presentation.utils import run_async

            run_async(self.page, request_push_permissions)
        except Exception:  # noqa: BLE001
            logger.exception("Notification permission prompt failed")

    def lock_session(self) -> None:
        """Show the PIN / Face ID gate when credentials exist."""
        if not (self.state.pin_hash and self.state.pin_salt):
            return
        if not self.state.is_unlocked:
            return
        self.state.set_unlocked(False)

    async def _load_pin_gate(self) -> None:
        """Decide whether the session starts locked."""
        await self.state.reload_pin_gate(
            lock_if_present=True,
            unlock_if_absent=True,
            notify=False,
        )

    def _nav_specs(self) -> tuple[tuple[int, ft.IconData, ft.IconData, str], ...]:
        lang = self.state.language
        return (
            (
                AppState.TAB_HOME,
                ft.Icons.HOME_OUTLINED,
                ft.Icons.HOME,
                tr("nav.home", lang),
            ),
            (
                AppState.TAB_TRANSACTIONS,
                ft.Icons.RECEIPT_LONG_OUTLINED,
                ft.Icons.RECEIPT_LONG,
                tr("nav.transactions", lang),
            ),
            (
                AppState.TAB_ACCOUNTS,
                ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                ft.Icons.ACCOUNT_BALANCE_WALLET,
                tr("nav.accounts", lang),
            ),
            (
                AppState.TAB_SETTINGS,
                ft.Icons.SETTINGS_OUTLINED,
                ft.Icons.SETTINGS,
                tr("nav.settings", lang),
            ),
        )

    def _ensure_nav_items(self) -> None:
        if self._nav.controls:
            return
        skin = get_active_skin()
        for index, icon, selected_icon, label in self._nav_specs():
            glyph = ft.Icon(icon, size=22, color=ft.Colors.ON_SURFACE_VARIANT)
            pill = ft.Container(
                width=_NAV_PILL_W,
                height=_NAV_PILL_H,
                alignment=ft.Alignment.CENTER,
                border_radius=skin.chip_radius,
                scale=1,
                animate_scale=ft.Animation(280, ft.AnimationCurve.EASE_OUT_BACK),
                content=glyph,
            )
            caption = ft.Text(
                label,
                size=11,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                no_wrap=True,
                animate_opacity=ft.Animation(220, ft.AnimationCurve.EASE_OUT),
            )
            item = ft.Container(
                expand=True,
                ink=False,
                on_click=lambda _e, i=index: self.state.set_tab(i),
                padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                content=ft.Column(
                    spacing=2,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[pill, caption],
                ),
            )
            self._nav.controls.append(item)
            self._nav_pills.append(pill)
            self._nav_icons.append(glyph)
            self._nav_labels.append(caption)

    def _sync_nav_indicator(self, *, dark: bool) -> None:
        """Move the selection pill into the active tab slot via flex spacers."""
        skin = get_active_skin()
        specs = self._nav_specs()
        n = max(len(specs), 1)
        selected_i = 0
        for i, (index, *_rest) in enumerate(specs):
            if self.state.selected_tab == index:
                selected_i = i
                break
        self._nav_slide_lead.expand = selected_i
        self._nav_slide_trail.expand = max(n - 1 - selected_i, 0)
        self._nav_indicator.border_radius = skin.chip_radius
        self._nav_indicator.bgcolor = skin.nav_selected_bg(dark=dark)

    def _sync_chrome(self) -> None:
        skin = get_active_skin()
        dark = is_dark_mode(self.page, self.state.theme_mode)
        self._stage.gradient = skin.page_gradient(dark=dark)
        self._stage.bgcolor = skin.dark_bg if dark else skin.light_bg
        layer = glass_layer(opacity=0.38)
        self._nav_host.bgcolor = layer.get("bgcolor")
        self._nav_host.blur = layer.get("blur")
        self._nav_host.border = ft.Border.all(
            1,
            ft.Colors.with_opacity(0.28, ft.Colors.ON_SURFACE)
            if skin.glass
            else ft.Colors.OUTLINE_VARIANT,
        )
        self._nav_host.border_radius = skin.card_radius
        self._nav_host.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=22,
            color=skin.glow,
            offset=ft.Offset(0, 6),
        )

    def _build_navigation_bar(self) -> None:
        lang = self.state.language
        self._ensure_nav_items()
        self._sync_chrome()
        skin = get_active_skin()
        dark = is_dark_mode(self.page, self.state.theme_mode)
        specs = self._nav_specs()
        for i, (index, icon, selected_icon, label) in enumerate(specs):
            selected = self.state.selected_tab == index
            pill = self._nav_pills[i]
            glyph = self._nav_icons[i]
            caption = self._nav_labels[i]
            pill.border_radius = skin.chip_radius
            pill.bgcolor = None
            pill.scale = 1.06 if selected else 1.0
            glyph.icon = selected_icon if selected else icon
            glyph.color = (
                skin.nav_selected_fg(dark=dark)
                if selected
                else ft.Colors.ON_SURFACE_VARIANT
            )
            caption.value = label
            caption.weight = ft.FontWeight.W_700 if selected else ft.FontWeight.W_500
            caption.color = (
                ft.Colors.ON_SURFACE if selected else ft.Colors.ON_SURFACE_VARIANT
            )
        self._sync_nav_indicator(dark=dark)
        self._rendered_lang = lang

    def _on_state_changed(self, _state: AppState) -> None:
        if self._rendered_rebuild_token != self.state.view_rebuild_token:
            self._forget_cached_views()
            self._rendered_rebuild_token = self.state.view_rebuild_token
            self._render(force=True)
            self._flush_notifications()
            self._pulse_data_flash()
            return
        needs_nav = (
            self._rendered_tab != self.state.selected_tab
            or self._rendered_secondary != self.state.secondary_route
            or self._rendered_lang != self.state.language
            or self._rendered_unlocked != self.state.is_unlocked
            or (
                not self.state.is_unlocked
                and bool(self.state.pin_hash)
            )
        )
        if self._rendered_lang != self.state.language:
            # Nav labels update immediately; force remount so page strings
            # switch language too (plain _render early-returns on same tab).
            self._build_navigation_bar()
            self._forget_cached_views()
            self._render(force=True)
            self._flush_notifications()
            self._pulse_data_flash()
            return
        if needs_nav:
            self._render()
        self._flush_notifications()
        self._pulse_data_flash()

    def _pulse_data_flash(self) -> None:
        if not self.state.consume_data_flash():
            return
        try:
            from lib.presentation.ui_feedback import flash_refresh

            flash_refresh(self.page)
        except Exception:  # noqa: BLE001
            pass

    def _flush_notifications(self) -> None:
        for message in self.state.pop_notifications():
            snack(self.page, message)

    def _forget_view(self, view: ft.Control | None) -> None:
        """Stop background reloads and drop AppState listeners for a cached page."""
        if view is None:
            return
        gate = getattr(view, "_reload_gate", None)
        if gate is not None:
            gate.mark_hidden()
        listener = getattr(view, "_on_state", None)
        if callable(listener):
            self.state.unsubscribe(listener)

    def _forget_cached_views(self) -> None:
        for view in list(self._primary_cache.values()):
            self._forget_view(view)
        for view in list(self._secondary_cache.values()):
            self._forget_view(view)
        self._primary_cache.clear()
        self._secondary_cache.clear()
        self._active_view = None

    def _deactivate_view(self, view: ft.Control | None) -> None:
        if view is None:
            return
        gate = getattr(view, "_reload_gate", None)
        if gate is not None:
            gate.mark_hidden()

    def _activate_view(self, view: ft.Control) -> None:
        gate = getattr(view, "_reload_gate", None)
        if gate is not None:
            gate.mark_shown()
            gate.on_mounted()

    def _primary_page(self, tab: int) -> ft.Control:
        cached = self._primary_cache.get(tab)
        if cached is not None:
            return cached
        if tab == AppState.TAB_TRANSACTIONS:
            view: ft.Control = TransactionsPage(self.page, self.state)
        elif tab == AppState.TAB_ACCOUNTS:
            view = AccountsPage(self.page, self.state)
        elif tab == AppState.TAB_SETTINGS:
            view = SettingsPage(self.page, self.state)
        else:
            view = DashboardPage(self.page, self.state)
        self._primary_cache[tab] = view
        return view

    def _secondary_page(self, route: str) -> ft.Control:
        # Account detail is heavy (charts + ledger). Keep only the current one
        # so opening many cards does not stack listeners and reloads.
        if route.startswith("account:"):
            for key in list(self._secondary_cache):
                if key.startswith("account:") and key != route:
                    self._forget_view(self._secondary_cache.pop(key))
        cached = self._secondary_cache.get(route)
        if cached is not None:
            return cached
        if route == "analytics":
            view: ft.Control = AnalyticsPage(self.page, self.state)
        elif route.startswith("account:"):
            account_id = route.split(":", 1)[1]
            view = AccountDetailPage(self.page, self.state, account_id)
        elif route == "goals":
            view = GoalsPage(self.page, self.state)
        elif route == "debts":
            view = DebtsPage(self.page, self.state)
        elif route == "subscriptions":
            view = SubscriptionsPage(self.page, self.state)
        elif route == "currencies":
            view = CurrenciesPage(self.page, self.state)
        elif route == "budgets":
            view = BudgetsPage(self.page, self.state)
        else:
            return self._primary_page(self.state.selected_tab)
        self._secondary_cache[route] = view
        return view

    async def _unlock(self) -> None:
        self.state.set_unlocked(True)

    def _render(self, *, force: bool = False) -> None:
        """Swap primary / secondary content based on AppState."""
        if not self.state.is_unlocked and self.state.pin_gate_failed:
            from lib.presentation.utils import tr

            self._deactivate_view(self._active_view)
            self._active_view = None
            self._nav_host.visible = False
            lang = self.state.language
            self._content.content = ft.Container(
                expand=True,
                key="lock-failed",
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.LOCK, size=40, color=ft.Colors.ERROR),
                        ft.Text(
                            tr("lock.pin_load_failed", lang),
                            text_align=ft.TextAlign.CENTER,
                            expand=True,
                        ),
                    ],
                ),
            )
            self._rendered_unlocked = False
            self.page.update()
            return
        if not self.state.is_unlocked and self.state.pin_hash and self.state.pin_salt:
            self._deactivate_view(self._active_view)
            self._active_view = None
            self._nav_host.visible = False
            self._content.content = ft.Container(
                expand=True,
                key="lock",
                content=LockScreen(
                    self.page,
                    language=self.state.language,
                    pin_hash=self.state.pin_hash,
                    pin_salt=self.state.pin_salt,
                    biometric_enabled=bool(self.state.settings.biometric_enabled),
                    on_unlocked=self._unlock,
                    encryption=self.state.container.encryption_service
                    or EncryptionService(),
                    # Windows Hello is local to the PC; skip auto-prompt for remote web/mobile sessions.
                    auto_biometric=os.environ.get("FLET_FORCE_WEB_SERVER", "").lower()
                    not in {"1", "true", "yes"},
                ),
            )
            self._rendered_unlocked = False
            self.page.update()
            return

        route = self.state.secondary_route
        tab = self.state.selected_tab
        if (
            not force
            and self._rendered_tab == tab
            and self._rendered_secondary == route
            and self._rendered_unlocked is True
        ):
            return

        if route:
            view = self._secondary_page(route)
        else:
            view = self._primary_page(tab)
            # Leaving a secondary route: drop the last account-detail tree.
            for key in list(self._secondary_cache):
                if key.startswith("account:"):
                    self._forget_view(self._secondary_cache.pop(key))

        previous = self._active_view
        if previous is not None and previous is not view:
            self._deactivate_view(previous)

        self._nav_host.visible = route is None
        self._build_navigation_bar()

        if self._rendered_tab is not None or self._rendered_secondary is not None:
            from lib.presentation.haptics import haptic

            haptic("medium")

        self._content.content = ft.Container(
            expand=True,
            key=route or f"tab-{tab}",
            content=view,
        )
        self._active_view = view
        self._activate_view(view)
        self._rendered_tab = tab
        self._rendered_secondary = route
        self._rendered_unlocked = True
        self.page.update()
