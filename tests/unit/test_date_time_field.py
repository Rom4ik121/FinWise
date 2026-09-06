"""DateTimeField helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from lib.presentation.widgets.date_time_field import (
    _as_utc,
    _display_text,
    _from_local_calendar,
    _local_now,
    picker_locale,
)


def test_as_utc_naive() -> None:
    dt = datetime(2024, 5, 1, 12, 30)
    assert _as_utc(dt).tzinfo == timezone.utc


def test_display_text_formats() -> None:
    dt = datetime(2024, 5, 1, 14, 30, tzinfo=timezone.utc)
    assert _display_text(None, with_time=False, empty_label="—") == "—"
    assert "01.05.2024" in _display_text(dt, with_time=False, empty_label="—")
    local_hm = dt.astimezone().strftime("%H:%M")
    assert local_hm in _display_text(dt, with_time=True, empty_label="—")


def test_picker_locale_follows_app_lang() -> None:
    assert picker_locale("ru") == "ru_RU"
    assert picker_locale("en") == "en_US"
    assert picker_locale("uz-UZ") == "uz_UZ"


def test_from_local_calendar_matches_phone_wall_clock() -> None:
    """Picked Y-M-D H:M is local; stored UTC round-trips to the same local fields."""
    local = _local_now()
    stored = _from_local_calendar(
        local.year, local.month, local.day, local.hour, local.minute
    )
    assert stored.tzinfo == timezone.utc
    back = stored.astimezone()
    assert back.year == local.year
    assert back.month == local.month
    assert back.day == local.day
    assert back.hour == local.hour
    assert back.minute == local.minute
