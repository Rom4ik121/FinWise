"""Unit tests for OS push notifier helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from lib.infrastructure.services.push_notifier import (
    OS_PAYLOAD_PREFIX,
    _icon_path,
    dispatch_push,
    future_os_fire_at,
    notification_settings_url,
    os_notification_payload,
    push_disabled_by_env,
    reminder_fire_at,
    stable_notification_id,
)


def test_stable_notification_id_is_deterministic() -> None:
    a = stable_notification_id("debt_reminder", "abc")
    b = stable_notification_id("debt_reminder", "abc")
    c = stable_notification_id("debt_reminder", "xyz")
    assert a == b
    assert a != c
    assert 0 < a < 2_000_000_000


def test_dispatch_push_respects_disable_env(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_DISABLE_PUSH", "1")
    assert push_disabled_by_env()
    # Must not raise.
    dispatch_push("Title", "Body", kind="info")
    monkeypatch.delenv("FINANCE_DISABLE_PUSH", raising=False)
    assert not push_disabled_by_env()


def test_reminder_fire_at_still_fires_if_lead_window_passed() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    due = now + timedelta(hours=2)
    when = reminder_fire_at(due, reminder_time="09:00", lead_days=3, now=now)
    assert when is not None
    assert when == now + timedelta(seconds=20)


def test_reminder_fire_at_still_arms_overdue() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    due = now - timedelta(days=1)
    when = reminder_fire_at(due, reminder_time="09:00", lead_days=3, now=now)
    assert when == now + timedelta(seconds=20)


def test_reminder_fire_at_schedules_before_due() -> None:
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    due = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
    when = reminder_fire_at(due, reminder_time="09:00", lead_days=3, now=now)
    assert when is not None
    assert now < when < due


def test_icon_path_points_to_app_branding() -> None:
    path = _icon_path()
    assert path
    assert Path(path).is_file()
    assert Path(path).name in {"icon.png", "icon_android.png", "icon.ico"}


def test_request_push_permissions_false_without_service_on_ios(monkeypatch) -> None:
    from lib.infrastructure.services import push_notifier as pn

    monkeypatch.setattr(pn, "_mobile_service", None)
    monkeypatch.setattr(pn, "_looks_like_ios", lambda: True)
    monkeypatch.setattr(pn, "push_disabled_by_env", lambda: False)

    async def _run() -> None:
        assert await pn.request_push_permissions() is False

    import asyncio

    asyncio.run(_run())


def test_future_os_fire_at_keeps_twenty_second_arm() -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    when = now + timedelta(seconds=20)
    assert future_os_fire_at(when, now=now) == when


def test_future_os_fire_at_due_now_shows_immediately() -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    assert future_os_fire_at(now, now=now) is None


def test_notification_settings_url_ios(monkeypatch) -> None:
    from lib.infrastructure.services import push_notifier as pn

    monkeypatch.setattr(pn, "_looks_like_ios", lambda: True)
    assert pn.notification_settings_url() == "app-settings:"


def test_notification_settings_url_android(monkeypatch) -> None:
    from lib.infrastructure.services import push_notifier as pn

    monkeypatch.setattr(pn, "_looks_like_ios", lambda: False)
    monkeypatch.setattr("lib.core.config._is_android", lambda: True)
    url = pn.notification_settings_url()
    assert url is not None
    assert "APP_NOTIFICATION_SETTINGS" in url
    assert "com.finanse.app" in url


def test_open_system_settings_uses_native_then_launch(monkeypatch) -> None:
    from lib.infrastructure.services import push_notifier as pn

    class _Svc:
        async def open_system_settings(self) -> bool:
            return True

    monkeypatch.setattr(pn, "_mobile_service", _Svc())

    async def _run() -> None:
        assert await pn.open_system_notification_settings(page=None) is True

    import asyncio

    asyncio.run(_run())


def test_os_notification_payload_prefix() -> None:
    assert os_notification_payload("debt_reminder", "abc").startswith(OS_PAYLOAD_PREFIX)
    assert os_notification_payload("debt_reminder", "abc") == "finwise:debt_reminder:abc"


def test_cancel_os_prefixed_never_calls_cancel_all(monkeypatch) -> None:
    from lib.infrastructure.services import push_notifier as pn

    class _Svc:
        def __init__(self) -> None:
            self.all_calls = 0
            self.prefixes: list[str] = []

        async def cancel_all(self) -> bool:
            self.all_calls += 1
            return True

        async def cancel_prefixed(self, prefix: str = "finwise:") -> bool:
            self.prefixes.append(prefix)
            return True

    svc = _Svc()
    monkeypatch.setattr(pn, "_mobile_service", svc)
    monkeypatch.setattr(pn, "push_disabled_by_env", lambda: False)

    async def _run() -> None:
        assert await pn.cancel_os_prefixed() is True

    import asyncio

    asyncio.run(_run())
    assert svc.all_calls == 0
    assert svc.prefixes == ["finwise:"]
