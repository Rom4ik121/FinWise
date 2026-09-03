"""Lifecycle tokens for the 15s background lock."""

from __future__ import annotations

from types import SimpleNamespace

from lib.presentation.app import (
    _BACKGROUND_LIFECYCLE,
    _FOREGROUND_LIFECYCLE,
    lifecycle_token,
)


def test_inactive_is_not_background() -> None:
    assert lifecycle_token(SimpleNamespace(data="inactive")) not in _BACKGROUND_LIFECYCLE
    assert lifecycle_token(SimpleNamespace(data="AppLifecycleState.inactive")) not in (
        _BACKGROUND_LIFECYCLE
    )


def test_paused_is_background() -> None:
    assert lifecycle_token(SimpleNamespace(data="paused")) in _BACKGROUND_LIFECYCLE
    assert lifecycle_token(SimpleNamespace(data="AppLifecycleState.hidden")) in (
        _BACKGROUND_LIFECYCLE
    )


def test_resumed_is_foreground() -> None:
    assert lifecycle_token(SimpleNamespace(data="resumed")) in _FOREGROUND_LIFECYCLE
    assert lifecycle_token(SimpleNamespace(state="show")) in _FOREGROUND_LIFECYCLE
