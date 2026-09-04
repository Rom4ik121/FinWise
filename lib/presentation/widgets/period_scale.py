"""Period progress scale with start/end date labels for analytics tiles."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone

import flet as ft


def _as_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().date()
    return value


def _fmt_short(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d.%m.%y")


def elapsed_period_ratio(
    start: datetime | date | None,
    end: datetime | date | None,
    *,
    now: datetime | date | None = None,
) -> float | None:
    """Share of the calendar period already elapsed (0..1), or ``None`` if unbound."""
    start_d = _as_date(start)
    end_d = _as_date(end)
    if start_d is None or end_d is None:
        return None
    if end_d < start_d:
        return None
    today = _as_date(now) if now is not None else date.today()
    assert today is not None
    span = (end_d - start_d).days + 1
    if today < start_d:
        return 0.0
    if today > end_d:
        return 1.0
    done = (today - start_d).days + 1
    return max(0.0, min(1.0, done / float(span)))


def period_progress_scale(
    *,
    color: str,
    start: datetime | date | None,
    end: datetime | date | None,
    ratio: float | None = None,
    bar_height: int = 6,
    now: datetime | date | None = None,
) -> ft.Control | None:
    """Progress bar filled by **elapsed time** through ``start``→``end``.

    Pass ``ratio`` only to override (tests). Missing either bound → ``None``.
    """
    start_d = _as_date(start)
    end_d = _as_date(end)
    if start_d is None or end_d is None:
        return None
    if end_d < start_d:
        return None
    if ratio is None:
        computed = elapsed_period_ratio(start_d, end_d, now=now)
        if computed is None:
            return None
        clamped = computed
    else:
        clamped = max(0.0, min(float(ratio), 1.0))
    from lib.presentation.count_up import mark_progress
    from lib.presentation.ui_motion import is_ui_animating

    animate = is_ui_animating()
    bar = ft.ProgressBar(
        value=0.0 if animate else clamped,
        color=color,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        bar_height=bar_height,
        border_radius=999,
    )
    if animate:
        mark_progress(bar, clamped)
    return ft.Column(
        spacing=4,
        tight=True,
        controls=[
            bar,
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        _fmt_short(start_d),
                        size=10,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        _fmt_short(end_d),
                        size=10,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
            ),
        ],
    )


def budget_month_bounds(month: int, year: int) -> tuple[date, date]:
    """First and last calendar day of a budget month."""
    last = monthrange(int(year), int(month))[1]
    return date(int(year), int(month), 1), date(int(year), int(month), last)


def plain_progress_bar(
    *,
    ratio: float,
    color: str,
    bar_height: int = 6,
) -> ft.Control:
    """Fallback bar when no period dates exist."""
    from lib.presentation.count_up import mark_progress
    from lib.presentation.ui_motion import is_ui_animating

    clamped = max(0.0, min(float(ratio), 1.0))
    animate = is_ui_animating()
    bar = ft.ProgressBar(
        value=0.0 if animate else clamped,
        color=color,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        bar_height=bar_height,
        border_radius=999,
    )
    if animate:
        mark_progress(bar, clamped)
    return bar


def progress_or_period_scale(
    *,
    color: str,
    start: datetime | date | None,
    end: datetime | date | None,
    ratio: float = 0.0,
    bar_height: int = 6,
) -> ft.Control:
    """Elapsed-time period scale when dates exist; otherwise a plain bar."""
    scaled = period_progress_scale(
        color=color,
        start=start,
        end=end,
        bar_height=bar_height,
    )
    if scaled is not None:
        return scaled
    return plain_progress_bar(ratio=ratio, color=color, bar_height=bar_height)
