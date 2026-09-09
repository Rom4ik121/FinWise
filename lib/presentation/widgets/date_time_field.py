"""Date / date-time field: month strip + full-screen calendar.

The calendar opens as its own overlay (not an AlertDialog). Stacking a second
``show_dialog`` on an open form greys out the UI; ``push_overlay`` does not.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Callable, Optional

import flet as ft

from lib.infrastructure.services.localization import normalize_lang
from lib.presentation.haptics import haptic
from lib.presentation.layout import _hidden_scrollbar, _prevent_h_scroll_reset
from lib.presentation.responsive import (
    calendar_cell_size,
    calendar_day_width,
    clamp_content_width,
    tap_button_style,
)
from lib.presentation.styles import form_save_button
from lib.presentation.utils import format_date, run_async, safe_update, tr
from lib.presentation.widgets.fullscreen_form import open_fullscreen_form

_STRIP_CHIP = 44
_STRIP_GAP = 6
_STRIP_HEIGHT = 52
_STRIP_SPAN = _STRIP_CHIP + _STRIP_GAP


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _local_now() -> datetime:
    """Device-local 'now' (phone timezone)."""
    return datetime.now().astimezone()


def _from_local_calendar(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
) -> datetime:
    """Interpret picker fields as local wall time, store as UTC."""
    local_tz = _local_now().tzinfo or timezone.utc
    local_dt = datetime(year, month, day, hour, minute, tzinfo=local_tz)
    return local_dt.astimezone(timezone.utc)


def _display_text(
    value: Optional[datetime],
    *,
    with_time: bool,
    empty_label: str,
) -> str:
    if value is None:
        return empty_label
    return format_date(value, with_time=with_time)


def picker_locale(lang: str | None) -> str:
    """Map app language code to a locale tag (kept for tests / callers)."""
    code = normalize_lang(lang)
    return {
        "ru": "ru_RU",
        "en": "en_US",
        "uz": "uz_UZ",
    }.get(code, "ru_RU")


def month_days(year: int, month: int) -> list[date]:
    """Every calendar day in ``year-month`` (1..last)."""
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, last + 1)]


def calendar_weeks(year: int, month: int) -> list[list[date]]:
    """Monday-first weeks covering ``year-month``, including adjacent days."""
    return calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)


def strip_scroll_offset(day: int, *, chip_span: int = _STRIP_SPAN, lead: int = 36) -> int:
    """Pixel offset so ``day`` sits near the left of a horizontal month strip."""
    return max(0, (max(1, day) - 1) * chip_span - lead)


_MONTHS: dict[str, tuple[str, ...]] = {
    "ru": (
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ),
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "uz": (
        "Yanvar",
        "Fevral",
        "Mart",
        "Aprel",
        "May",
        "Iyun",
        "Iyul",
        "Avgust",
        "Sentabr",
        "Oktabr",
        "Noyabr",
        "Dekabr",
    ),
}

_WEEKDAYS: dict[str, tuple[str, ...]] = {
    "ru": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"),
    "en": ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"),
    "uz": ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"),
}


class DateTimeField(ft.Column):
    """Date control: horizontal month strip + full-screen calendar overlay."""

    def __init__(
        self,
        page: ft.Page,
        *,
        lang: str,
        label: str | None = None,
        value: Optional[datetime] = None,
        with_time: bool = False,
        allow_clear: bool = False,
        first_date: Optional[date] = None,
        last_date: Optional[date] = None,
        on_changed: Optional[Callable[[Optional[datetime]], None]] = None,
        expand: bool = False,
        quick_strip: bool = True,
    ) -> None:
        self._page = page
        self._lang = normalize_lang(lang)
        self._label = label or tr("field.date", lang)
        self._with_time = with_time
        self._allow_clear = allow_clear
        self._quick_strip = quick_strip
        self._on_changed = on_changed
        self._first_date = first_date or date(2000, 1, 1)
        self._last_date = last_date or date(2100, 12, 31)
        self._value: Optional[datetime] = _as_utc(value) if value else None
        self._picker_open = False
        self._pick_state: dict[str, int] | None = None
        self._overlay_key = f"datetime_picker_{id(self)}"
        self._overlay_close: Callable[[], None] | None = None

        self._title = ft.Text(
            self._label,
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self._value_text = ft.Text(
            "",
            size=14,
            weight=ft.FontWeight.W_600,
            expand=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
        )
        self._set_btn = ft.OutlinedButton(
            tr("date.set_with_time", lang) if with_time else tr("date.set", lang),
            icon=ft.Icons.CALENDAR_MONTH_ROUNDED,
            on_click=lambda _e: self.open_picker(),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            ),
        )
        self._change_btn = ft.TextButton(
            tr("date.change", lang),
            icon=ft.Icons.EDIT_CALENDAR_OUTLINED,
            on_click=lambda _e: self.open_picker(),
        )
        self._clear_btn = ft.IconButton(
            icon=ft.Icons.CLOSE_ROUNDED,
            icon_size=18,
            icon_color=ft.Colors.ON_SURFACE_VARIANT,
            tooltip=tr("date.clear", lang),
            visible=allow_clear,
            on_click=lambda _e: self.clear(),
            style=tap_button_style(horizontal=8, vertical=8),
        )
        self._selected_row = ft.Container(
            visible=False,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
                controls=[
                    ft.Icon(
                        ft.Icons.EVENT_AVAILABLE_ROUNDED,
                        size=18,
                        color=ft.Colors.PRIMARY,
                    ),
                    self._value_text,
                    self._change_btn,
                    self._clear_btn,
                ],
            ),
        )

        self._month_title = ft.Text("", size=16, weight=ft.FontWeight.W_700)
        self._grid = ft.Column(spacing=4, tight=True)
        self._hour_dd = ft.Dropdown(
            label=tr("date.hour", lang),
            dense=True,
            expand=True,
            visible=with_time,
            options=[
                ft.DropdownOption(key=f"{h:02d}", text=f"{h:02d}") for h in range(24)
            ],
        )
        self._minute_dd = ft.Dropdown(
            label=tr("date.minute", lang),
            dense=True,
            expand=True,
            visible=with_time,
            options=[
                ft.DropdownOption(key=f"{m:02d}", text=f"{m:02d}")
                for m in range(0, 60, 5)
            ],
        )
        self._time_row = ft.Row(
            spacing=8,
            visible=with_time,
            controls=[self._hour_dd, self._minute_dd],
        )
        self._strip_label = ft.Text(
            tr("date.month_days", lang),
            size=11,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=quick_strip,
        )
        self._strip_list = ft.ListView(
            horizontal=True,
            spacing=_STRIP_GAP,
            padding=ft.Padding.only(right=12),
            auto_scroll=False,
            height=_STRIP_HEIGHT,
            adaptive=False,
            build_controls_on_demand=False,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            scroll=_hidden_scrollbar(),
        )
        _prevent_h_scroll_reset(self._strip_list)
        self._strip = ft.Container(
            visible=quick_strip,
            height=_STRIP_HEIGHT,
            content=self._strip_list,
        )

        super().__init__(
            spacing=6,
            tight=True,
            expand=expand,
            controls=[
                self._title,
                self._set_btn,
                self._selected_row,
                self._strip_label,
                self._strip,
            ],
        )
        self._sync_ui()
        if quick_strip:
            self._render_strip()

    @property
    def value(self) -> Optional[datetime]:
        """Selected UTC datetime (date-only at 00:00 when without time)."""
        return self._value

    @value.setter
    def value(self, dt: Optional[datetime]) -> None:
        self.set_value(dt, notify=False)

    @property
    def date_text(self) -> str:
        """``YYYY-MM-DD`` for filters, or empty when unset."""
        if self._value is None:
            return ""
        return self._value.date().isoformat()

    def set_value(
        self,
        dt: Optional[datetime],
        *,
        notify: bool = True,
    ) -> None:
        self._value = _as_utc(dt) if dt is not None else None
        self._sync_ui()
        if self._quick_strip:
            self._render_strip()
        if notify and self._on_changed is not None:
            self._on_changed(self._value)

    def clear(self) -> None:
        if not self._allow_clear:
            return
        self._close_picker()
        self.set_value(None, notify=True)

    def _sync_ui(self) -> None:
        has_value = self._value is not None
        self._set_btn.visible = not has_value and not self._picker_open
        self._selected_row.visible = has_value and not self._picker_open
        self._clear_btn.visible = has_value and self._allow_clear
        show_strip = self._quick_strip and not self._picker_open
        self._strip.visible = show_strip
        self._strip_label.visible = show_strip
        if has_value:
            self._value_text.value = format_date(
                self._value, with_time=self._with_time
            )
        else:
            self._value_text.value = ""
        for control in (
            self._set_btn,
            self._selected_row,
            self._clear_btn,
            self._value_text,
            self._strip,
            self._strip_label,
        ):
            safe_update(control)

    def open_picker(self) -> None:
        """Open the full-screen calendar overlay."""
        local_now = _local_now()
        if self._value is not None:
            local_value = self._value.astimezone()
            initial = local_value.date()
            hour = local_value.hour
            minute = local_value.minute
        else:
            initial = local_now.date()
            hour = local_now.hour
            minute = local_now.minute
        if initial < self._first_date:
            initial = self._first_date
        if initial > self._last_date:
            initial = self._last_date
        self._pick_state = {
            "year": initial.year,
            "month": initial.month,
            "day": initial.day,
            "hour": hour,
            "minute": minute,
        }
        self._hour_dd.value = f"{hour:02d}"
        minute_q = minute - (minute % 5) if minute % 5 else minute
        if self._with_time and minute % 5 != 0:
            key = f"{minute:02d}"
            if not any(opt.key == key for opt in self._minute_dd.options or []):
                self._minute_dd.options = list(self._minute_dd.options or []) + [
                    ft.DropdownOption(key=key, text=key)
                ]
            self._minute_dd.value = key
        else:
            self._minute_dd.value = f"{minute_q:02d}"
        self._picker_open = True
        self._render_grid()
        form_w = clamp_content_width(self._page, margin=28, max_width=560)
        apply_btn = form_save_button(
            tr("action.apply", self._lang),
            icon=ft.Icons.CHECK,
            on_click=lambda e: run_async(self._page, self._overlay_save),
        )
        try:
            apply_btn.width = form_w
        except Exception:  # noqa: BLE001
            pass
        footer = ft.Container(
            padding=ft.Padding.only(left=14, right=14, top=10, bottom=14),
            content=ft.Container(
                alignment=ft.Alignment.TOP_CENTER,
                content=ft.Container(width=form_w, content=apply_btn),
            ),
        )
        body = [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_LEFT,
                        icon_size=22,
                        icon_color=ft.Colors.PRIMARY,
                        on_click=lambda _e: self._shift_month(-1),
                        style=tap_button_style(horizontal=10, vertical=10),
                    ),
                    self._month_title,
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_RIGHT,
                        icon_size=22,
                        icon_color=ft.Colors.PRIMARY,
                        on_click=lambda _e: self._shift_month(1),
                        style=tap_button_style(horizontal=10, vertical=10),
                    ),
                ],
            ),
            ft.TextButton(
                tr("date.today", self._lang),
                icon=ft.Icons.TODAY,
                on_click=lambda _e: self._jump_today(),
            ),
            self._grid,
            self._time_row,
        ]
        self._overlay_close = open_fullscreen_form(
            self._page,
            title=self._label,
            lang=self._lang,
            overlay_key=self._overlay_key,
            wrap_body=False,
            save_compact=True,
            save_icon=ft.Icons.CHECK,
            save_label=tr("action.apply", self._lang),
            footer=footer,
            body=body,
            on_save=self._overlay_save,
            on_close=self._on_overlay_dismissed,
        )
        self._sync_ui()

    def _on_overlay_dismissed(self) -> None:
        self._picker_open = False
        self._pick_state = None
        self._overlay_close = None
        self._sync_ui()
        if self._quick_strip:
            self._render_strip()

    def _close_picker(self) -> None:
        closer = self._overlay_close
        if closer is not None:
            closer()
            return
        self._on_overlay_dismissed()

    async def _overlay_save(self) -> None:
        if not self._commit_pick():
            return
        closer = self._overlay_close
        if closer is not None:
            closer()

    def _commit_pick(self) -> bool:
        state = self._pick_state
        if state is None:
            return False
        hour = int(self._hour_dd.value or state["hour"]) if self._with_time else 0
        minute = (
            int(self._minute_dd.value or state["minute"]) if self._with_time else 0
        )
        chosen = _from_local_calendar(
            state["year"],
            state["month"],
            state["day"],
            hour,
            minute,
        )
        self.set_value(chosen, notify=True)
        return True

    def _clamp_day(self) -> None:
        state = self._pick_state
        if state is None:
            return
        last = calendar.monthrange(state["year"], state["month"])[1]
        if state["day"] > last:
            state["day"] = last

    def _shift_month(self, delta: int) -> None:
        state = self._pick_state
        if state is None:
            return
        month = state["month"] + delta
        year = state["year"]
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        state["month"] = month
        state["year"] = year
        self._clamp_day()
        self._render_grid()

    def _jump_today(self) -> None:
        state = self._pick_state
        if state is None:
            return
        local = _local_now()
        state["year"] = local.year
        state["month"] = local.month
        state["day"] = local.day
        self._render_grid()

    def _pick_day(self, chosen: date) -> None:
        state = self._pick_state
        if state is None:
            return
        if chosen < self._first_date or chosen > self._last_date:
            return
        state["year"] = chosen.year
        state["month"] = chosen.month
        state["day"] = chosen.day
        haptic("light")
        self._render_grid()

    def _render_grid(self) -> None:
        state = self._pick_state
        if state is None:
            return
        lang = self._lang
        months = _MONTHS.get(lang, _MONTHS["en"])
        weekdays = _WEEKDAYS.get(lang, _WEEKDAYS["en"])
        self._month_title.value = f"{months[state['month'] - 1]} {state['year']}"
        weeks = calendar_weeks(state["year"], state["month"])
        cell_h = max(44, calendar_cell_size(self._page))
        cell_w = calendar_day_width(self._page)
        header = ft.Row(
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=cell_w,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        name,
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
                for name in weekdays
            ],
        )
        rows: list[ft.Control] = [header]
        today = date.today()
        selected = date(state["year"], state["month"], state["day"])
        for week in weeks:
            cells: list[ft.Control] = []
            for current in week:
                in_month = current.month == state["month"]
                disabled = current < self._first_date or current > self._last_date
                is_selected = current == selected
                is_today = current == today

                bg = None
                fg = ft.Colors.ON_SURFACE if in_month else ft.Colors.ON_SURFACE_VARIANT
                if is_selected:
                    bg = ft.Colors.PRIMARY
                    fg = ft.Colors.ON_PRIMARY
                elif is_today:
                    bg = ft.Colors.PRIMARY_CONTAINER
                    fg = ft.Colors.ON_PRIMARY_CONTAINER

                cells.append(
                    ft.Container(
                        width=cell_w,
                        height=cell_h,
                        border_radius=max(12, cell_h // 2),
                        bgcolor=bg,
                        alignment=ft.Alignment.CENTER,
                        ink=not disabled,
                        opacity=0.38 if disabled else (1.0 if in_month else 0.55),
                        on_click=(
                            None
                            if disabled
                            else lambda _e, d=current: self._pick_day(d)
                        ),
                        content=ft.Text(
                            str(current.day),
                            size=13,
                            weight=ft.FontWeight.W_700
                            if is_selected or is_today
                            else ft.FontWeight.W_500,
                            color=fg,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    )
                )
            rows.append(ft.Row(spacing=4, alignment=ft.MainAxisAlignment.CENTER, controls=cells))
        self._grid.controls = rows
        safe_update(self._month_title)
        safe_update(self._grid)
        safe_update(self._hour_dd)
        safe_update(self._minute_dd)

    def _strip_month(self) -> tuple[int, int]:
        """Quick strip always shows the current local month (past + future days)."""
        local = _local_now()
        return local.year, local.month

    def _pick_strip_day(self, chosen: date) -> None:
        if chosen < self._first_date or chosen > self._last_date:
            return
        if self._value is not None:
            local = self._value.astimezone()
            hour, minute = local.hour, local.minute
        else:
            local = _local_now()
            hour, minute = (local.hour, local.minute) if self._with_time else (0, 0)
        if not self._with_time:
            hour, minute = 0, 0
        haptic("light")
        self.set_value(
            _from_local_calendar(chosen.year, chosen.month, chosen.day, hour, minute),
            notify=True,
        )

    def _render_strip(self) -> None:
        if not self._quick_strip:
            return
        year, month = self._strip_month()
        today = date.today()
        selected: date | None = None
        if self._value is not None:
            selected = self._value.astimezone().date()
        weekdays = _WEEKDAYS.get(self._lang, _WEEKDAYS["en"])
        chips: list[ft.Control] = []
        if selected is not None and selected.year == year and selected.month == month:
            focus_day = selected.day
        elif today.year == year and today.month == month:
            focus_day = today.day
        else:
            focus_day = 1
        for current in month_days(year, month):
            disabled = current < self._first_date or current > self._last_date
            is_selected = selected == current
            is_today = current == today
            is_past = current < today
            bg = None
            fg = ft.Colors.ON_SURFACE
            shadow = None
            if is_selected:
                bg = ft.Colors.PRIMARY
                fg = ft.Colors.ON_PRIMARY
                shadow = ft.BoxShadow(
                    blur_radius=12,
                    color="#00000030",
                    offset=ft.Offset(0, 3),
                )
            elif is_today:
                bg = ft.Colors.PRIMARY_CONTAINER
                fg = ft.Colors.ON_PRIMARY_CONTAINER
                shadow = ft.BoxShadow(
                    blur_radius=8,
                    color="#0000001f",
                    offset=ft.Offset(0, 2),
                )
            chips.append(
                ft.Container(
                    key=f"d{current.day}",
                    width=_STRIP_CHIP,
                    height=_STRIP_HEIGHT - 4,
                    border_radius=12,
                    bgcolor=bg,
                    shadow=shadow,
                    alignment=ft.Alignment.CENTER,
                    ink=not disabled,
                    opacity=0.35 if disabled else (0.72 if is_past and not is_selected else 1.0),
                    on_click=(
                        None
                        if disabled
                        else lambda _e, d=current: self._pick_strip_day(d)
                    ),
                    content=ft.Column(
                        spacing=0,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                weekdays[current.weekday()],
                                size=9,
                                weight=ft.FontWeight.W_600,
                                color=fg,
                            ),
                            ft.Text(
                                str(current.day),
                                size=14,
                                weight=ft.FontWeight.W_700,
                                color=fg,
                            ),
                        ],
                    ),
                )
            )
        self._strip_list.controls = chips
        safe_update(self._strip_list)
        try:
            self._strip_list.scroll_to(
                offset=strip_scroll_offset(focus_day),
                duration=220,
            )
        except Exception:  # noqa: BLE001
            pass
