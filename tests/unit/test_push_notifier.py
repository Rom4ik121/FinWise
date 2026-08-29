"""Unit tests for OS push notifier helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lib.infrastructure.services.push_notifier import (
    dispatch_push,
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


def test_reminder_fire_at_skips_already_past_due() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    due = now - timedelta(days=1)
    assert reminder_fire_at(due, reminder_time="09:00", lead_days=3, now=now) is None


def test_reminder_fire_at_schedules_before_due() -> None:
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    due = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
    when = reminder_fire_at(due, reminder_time="09:00", lead_days=3, now=now)
    assert when is not None
    assert now < when < due
