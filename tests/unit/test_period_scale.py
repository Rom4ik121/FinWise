"""Unit tests for analytics period time scales."""

from __future__ import annotations

from datetime import date

from lib.presentation.widgets.period_scale import (
    budget_month_bounds,
    elapsed_period_ratio,
    period_progress_scale,
)


def test_elapsed_ratio_mid_period() -> None:
    start = date(2026, 1, 1)
    end = date(2026, 1, 31)
    # Inclusive: day 16 of 31 calendar days.
    assert elapsed_period_ratio(start, end, now=date(2026, 1, 16)) == 16 / 31


def test_elapsed_ratio_same_day() -> None:
    day = date(2026, 5, 1)
    assert elapsed_period_ratio(day, day, now=day) == 1.0
    assert elapsed_period_ratio(day, day, now=date(2026, 4, 30)) == 0.0


def test_elapsed_ratio_before_and_after() -> None:
    start = date(2026, 3, 1)
    end = date(2026, 3, 31)
    assert elapsed_period_ratio(start, end, now=date(2026, 2, 20)) == 0.0
    assert elapsed_period_ratio(start, end, now=date(2026, 4, 1)) == 1.0


def test_elapsed_ratio_missing_end() -> None:
    assert elapsed_period_ratio(date(2026, 1, 1), None) is None
    assert period_progress_scale(
        color="#fff",
        start=date(2026, 1, 1),
        end=None,
    ) is None


def test_budget_month_bounds() -> None:
    assert budget_month_bounds(9, 2026) == (date(2026, 9, 1), date(2026, 9, 30))
    start, end = budget_month_bounds(9, 2026)
    ratio = elapsed_period_ratio(start, end, now=date(2026, 9, 16))
    assert ratio == 16 / 30


def test_mark_progress_and_scroll_snapshot() -> None:
    import flet as ft

    from lib.presentation.count_up import mark_progress
    from lib.presentation.ui_motion import snapshot_scroll, ui_animation
    from lib.presentation.widgets.period_scale import period_progress_scale

    bar = ft.ProgressBar(value=0)
    mark_progress(bar, 0.4)
    assert bar.data["progress_anim"] is True
    assert bar.data["target"] == 0.4

    bar._fw_scroll = 120.0
    assert snapshot_scroll(bar) == 120.0

    with ui_animation(True):
        scale = period_progress_scale(
            color="#abc",
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            now=date(2026, 7, 2),
        )
    assert scale is not None
    inner = scale.controls[0]
    assert inner.value == 0.0
    assert inner.data["progress_anim"] is True
