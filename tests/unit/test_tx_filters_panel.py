"""Transaction filter panel helpers (Tune → Apply/Clear, not auto-wipe)."""

from __future__ import annotations

from datetime import date

from lib.presentation.pages.transactions import period_preset_range


def test_period_preset_fills_range_without_all_time_wipe_on_7d() -> None:
    today = date(2026, 9, 11)
    start, end = period_preset_range(7, today=today)
    assert end == today
    assert start == date(2026, 9, 4)
    start_all, end_all = period_preset_range(None, today=today)
    assert end_all == today
    assert (end_all - start_all).days == 365 * 5
