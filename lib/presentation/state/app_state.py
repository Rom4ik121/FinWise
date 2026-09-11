"""Observable application state for the presentation layer."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.settings import AppSettings
from lib.infrastructure.services.localization import normalize_lang

logger = logging.getLogger("finanse.presentation.state")

Listener = Callable[["AppState"], None]


class AppState:
    """Central UI state with a simple Observer (subscribe / notify) pattern.

    Holds the DI container, settings snapshot, selected navigation tab,
    secondary route, and refresh tokens so pages can re-render when data
    changes.
    """

    TAB_HOME = 0
    TAB_TRANSACTIONS = 1
    TAB_ACCOUNTS = 2
    TAB_SETTINGS = 3

    def __init__(self, container: Any) -> None:
        self.container = container
        self.settings: AppSettings = AppSettings()
        self.selected_tab: int = self.TAB_HOME
        self.secondary_route: Optional[str] = None
        self.refresh_token: int = 0
        self.dashboard_token: int = 0
        self.transactions_token: int = 0
        self.accounts_token: int = 0
        self.goals_token: int = 0
        self.debts_token: int = 0
        self.subscriptions_token: int = 0
        self.analytics_token: int = 0
        self.budgets_token: int = 0
        self.is_loading: bool = False
        self.is_unlocked: bool = True
        self.pin_hash: Optional[str] = None
        self.pin_salt: Optional[str] = None
        self.pin_gate_failed: bool = False
        self.pending_open_account_create: bool = False
        self.pending_edit_transaction_id: Optional[str] = None
        self.pending_tx_query: Optional[str] = None
        self.pending_budget_id: Optional[str] = None
        self.pending_edit_subscription_id: Optional[str] = None
        self.tx_filter_state: Optional[dict] = None
        self.pending_notifications: list[str] = []
        self.view_rebuild_token: int = 0
        self._listeners: list[Listener] = []
        self._notify_scheduled: bool = False
        self._data_flash_pending: bool = False

    # ------------------------------------------------------------------
    # Observer
    # ------------------------------------------------------------------

    def subscribe(self, listener: Listener) -> None:
        """Register a listener invoked on every :meth:`notify`."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """Remove a previously registered listener."""
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def notify(self, *, coalesce: bool = False) -> None:
        """Notify all subscribers that state has changed.

        When ``coalesce`` is True, multiple rapid bumps collapse into one notify
        on the next event-loop turn (reduces cascading UI reloads on phones).
        """
        if coalesce:
            if self._notify_scheduled:
                return
            self._notify_scheduled = True
            try:
                import asyncio

                loop = asyncio.get_running_loop()

                def _flush() -> None:
                    self._notify_scheduled = False
                    self.notify(coalesce=False)

                loop.call_soon(_flush)
                return
            except RuntimeError:
                self._notify_scheduled = False
        for listener in list(self._listeners):
            try:
                listener(self)
            except Exception:  # noqa: BLE001 — UI must stay alive
                logger.exception("AppState listener failed")

    def bump_refresh(self, *scopes: str) -> None:
        """Increment refresh tokens so listening pages reload data.

        Args:
            scopes: Optional scopes such as ``dashboard``, ``transactions``,
                ``accounts``, ``goals``, ``debts``, ``subscriptions``,
                ``analytics``, ``budgets``. Empty means global refresh of primary tabs.
        """
        self.refresh_token += 1
        if not scopes:
            self.dashboard_token += 1
            self.transactions_token += 1
            self.accounts_token += 1
            self.goals_token += 1
            self.debts_token += 1
            self.subscriptions_token += 1
            self.analytics_token += 1
            self.budgets_token += 1
        else:
            if "dashboard" in scopes:
                self.dashboard_token += 1
            if "transactions" in scopes:
                self.transactions_token += 1
            if "accounts" in scopes:
                self.accounts_token += 1
            if "goals" in scopes:
                self.goals_token += 1
            if "debts" in scopes:
                self.debts_token += 1
            if "subscriptions" in scopes:
                self.subscriptions_token += 1
            if "analytics" in scopes:
                self.analytics_token += 1
            if "budgets" in scopes:
                self.budgets_token += 1
        self._data_flash_pending = True
        self.notify(coalesce=True)

    def consume_data_flash(self) -> bool:
        """Return True once after :meth:`bump_refresh` (for UI rim pulse)."""
        if not self._data_flash_pending:
            return False
        self._data_flash_pending = False
        return True

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    @property
    def language(self) -> str:
        """Current UI language code."""
        return normalize_lang(self.settings.language)

    @property
    def base_currency(self) -> str:
        """User-selected base / display currency (normalized ISO code)."""
        return normalize_currency_code(self.settings.default_currency or "RUB")

    @property
    def theme_mode(self) -> str:
        """Theme preference: light / dark / system."""
        return self.settings.theme or "system"

    @property
    def ui_style(self) -> str:
        """Visual style id: classic / neon."""
        return self.settings.ui_style or "neon"

    def set_settings(self, settings: AppSettings, *, notify: bool = True) -> None:
        """Replace settings snapshot and optionally notify listeners."""
        self.settings = settings
        if notify:
            self.notify()

    def set_tab(self, index: int, *, clear_secondary: bool = True) -> None:
        """Select a primary NavigationBar tab."""
        self.selected_tab = index
        if clear_secondary:
            self.secondary_route = None
        self.notify()

    def open_secondary(self, route: str) -> None:
        """Open a secondary screen (goals, debts, subscriptions, currencies)."""
        self.secondary_route = route
        self.notify()

    def close_secondary(self) -> None:
        """Return from a secondary screen to the primary tab content."""
        self.secondary_route = None
        self.notify()

    def set_loading(self, value: bool) -> None:
        """Toggle a global loading flag."""
        self.is_loading = value
        self.notify()

    def set_unlocked(self, value: bool, *, notify: bool = True) -> None:
        """Mark the session as unlocked (PIN gate passed)."""
        self.is_unlocked = value
        if notify:
            self.notify()

    async def reload_pin_gate(
        self,
        *,
        lock_if_present: bool = False,
        unlock_if_absent: bool = False,
        notify: bool = True,
    ) -> None:
        """Reload PIN hash/salt from the settings store.

        Call after set-PIN, clear-PIN, restore, or wipe so background lock and
        the lock screen use the live credentials instead of launch-time copies.
        """
        get_pin = getattr(self.container, "get_pin_credentials", None)
        if get_pin is None:
            self.pin_hash = None
            self.pin_salt = None
            self.pin_gate_failed = False
            if unlock_if_absent:
                self.is_unlocked = True
            if notify:
                self.notify()
            return
        try:
            pin_hash, pin_salt, biometric = await get_pin.execute()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load PIN credentials")
            self.pin_gate_failed = True
            self.pin_hash = None
            self.pin_salt = None
            self.is_unlocked = False
            if notify:
                self.notify()
            return
        self.pin_gate_failed = False
        self.pin_hash = pin_hash
        self.pin_salt = pin_salt
        if pin_hash and pin_salt:
            self.settings.biometric_enabled = biometric
            if lock_if_present:
                self.is_unlocked = False
        elif unlock_if_absent:
            self.is_unlocked = True
        if notify:
            self.notify()

    def push_notification(self, message: str, *, notify: bool = True) -> None:
        """Queue an in-app notification banner message."""
        self.pending_notifications.append(message)
        if notify:
            self.notify()

    def pop_notifications(self) -> list[str]:
        """Drain queued notification messages."""
        items = list(self.pending_notifications)
        self.pending_notifications.clear()
        return items

    def request_view_rebuild(self) -> None:
        """Ask the shell to drop cached views (e.g. after theme change)."""
        self.view_rebuild_token += 1
        self.notify()
