"""DateTimeField helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone

from lib.presentation.widgets.date_time_field import (
    _as_utc,
    _display_text,
    _from_local_calendar,
    _local_now,
    calendar_weeks,
    month_days,
    picker_locale,
    strip_scroll_offset,
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
    assert picker_locale("uk-UA") == "uk_UA"
    assert picker_locale("pt-BR") == "pt_BR"
    assert picker_locale("de") == "de_DE"
    assert picker_locale("zh-Hans") == "zh_CN"


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


def test_month_days_covers_whole_month() -> None:
    days = month_days(2026, 9)
    assert len(days) == 30
    assert days[0] == date(2026, 9, 1)
    assert days[-1] == date(2026, 9, 30)


def test_calendar_weeks_keep_seven_columns_and_all_month_days() -> None:
    weeks = calendar_weeks(2026, 9)
    assert weeks
    assert all(len(week) == 7 for week in weeks)
    in_month = [d for week in weeks for d in week if d.month == 9]
    assert [d.day for d in in_month] == list(range(1, 31))
    # Adjacent-month days fill leading/trailing slots instead of blanks.
    assert weeks[0][0].month == 8
    assert weeks[-1][-1].month == 10


def test_strip_scroll_offset_moves_later_days_into_view() -> None:
    assert strip_scroll_offset(1) == 0
    assert strip_scroll_offset(9) > strip_scroll_offset(2)
