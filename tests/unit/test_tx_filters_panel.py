"""Transaction filter panel helpers (Tune → Apply/Clear, not auto-wipe)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from lib.presentation.pages.transactions import period_preset_range, visible_list_rows


def test_period_preset_fills_range_without_all_time_wipe_on_7d() -> None:
    today = date(2026, 9, 11)
    start, end = period_preset_range(7, today=today)
    assert end == today
    assert start == date(2026, 9, 4)
    start_all, end_all = period_preset_range(None, today=today)
    assert end_all == today
    assert (end_all - start_all).days == 365 * 5


def test_visible_list_rows_drops_corporate_and_out_of_range() -> None:
    tz = ZoneInfo("Europe/Moscow")
    in_day = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
    out_day = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    personal = SimpleNamespace(account_id="cash", date=in_day)
    corporate = SimpleNamespace(account_id="llc", date=in_day)
    old = SimpleNamespace(account_id="cash", date=out_day)

    def in_range(tx: object) -> bool:
        when = getattr(tx, "date")
        return when.astimezone(tz).date() == date(2026, 9, 11)

    rows = visible_list_rows(
        [personal, corporate, old],  # type: ignore[list-item]
        corporate_ids={"llc"},
        in_range=in_range,
    )
    assert rows == [personal]

