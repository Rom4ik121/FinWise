"""AppState observer and refresh tokens."""

from __future__ import annotations

from lib.domain.entities.settings import AppSettings
from lib.presentation.state.app_state import AppState


class _FakeContainer:
    pass


def test_subscribe_notify() -> None:
    state = AppState(_FakeContainer())
    seen: list[int] = []

    def listener(s: AppState) -> None:
        seen.append(s.refresh_token)

    state.subscribe(listener)
    state.bump_refresh("dashboard")
    assert seen
    state.unsubscribe(listener)
    prev = len(seen)
    state.bump_refresh("accounts")
    assert len(seen) == prev


def test_language_and_currency_normalized() -> None:
    state = AppState(_FakeContainer())
    state.set_settings(
        AppSettings(language="uz-UZ", default_currency="usd"),
        notify=False,
    )
    assert state.language == "uz"
    assert state.base_currency == "USD"


def test_secondary_route_and_notifications() -> None:
    state = AppState(_FakeContainer())
    state.open_secondary("goals")
    assert state.secondary_route == "goals"
    state.close_secondary()
    assert state.secondary_route is None
    state.push_notification("hello")
    assert state.pop_notifications() == ["hello"]
    assert state.pop_notifications() == []


def test_budget_threshold_clamps() -> None:
    settings = AppSettings(budget_warn_pct=0, budget_limit_pct=999)
    assert settings.budget_warn_pct == 1
    assert settings.budget_limit_pct == 200
    settings = AppSettings(budget_warn_pct=80, budget_limit_pct=100)
    assert settings.budget_warn_pct == 80
    assert settings.budget_limit_pct == 100


def test_tabs_and_rebuild() -> None:
    state = AppState(_FakeContainer())
    state.set_tab(AppState.TAB_SETTINGS)
    assert state.selected_tab == AppState.TAB_SETTINGS
    before = state.view_rebuild_token
    state.request_view_rebuild()
    assert state.view_rebuild_token == before + 1


def test_reload_pin_gate_lock_and_unlock() -> None:
    from tests.conftest import run_async

    class _Pin:
        def __init__(self) -> None:
            self.payload = ("hash", "salt", True)

        async def execute(self):
            return self.payload

    container = _FakeContainer()
    container.get_pin_credentials = _Pin()
    state = AppState(container)
    state.is_unlocked = True

    async def _run() -> None:
        await state.reload_pin_gate(lock_if_present=True, notify=False)
        assert state.pin_hash == "hash"
        assert state.pin_salt == "salt"
        assert state.is_unlocked is False
        container.get_pin_credentials.payload = (None, None, False)
        await state.reload_pin_gate(unlock_if_absent=True, notify=False)
        assert state.pin_hash is None
        assert state.is_unlocked is True

    run_async(_run())
