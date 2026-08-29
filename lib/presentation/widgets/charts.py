"""Responsive Flet charts — line plots with axes, readable on any screen."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Sequence

import flet as ft
import flet.canvas as cv

from lib.presentation.skins import get_active_skin

_CHART_COLORS = [
    "#2DD4BF",
    "#38BDF8",
    "#4ADE80",
    "#FBBF24",
    "#F87171",
    "#A78BFA",
    "#FB7185",
    "#34D399",
]


def _chart_palette() -> Sequence[str]:
    colors = get_active_skin().chart_colors
    return colors if colors else _CHART_COLORS


def _prefer_native_charts() -> bool:
    """Always native so every platform renders the same widgets."""
    return True


def chart_layout(page: ft.Page | None = None) -> tuple[int, int]:
    """Width and plot height that fill the current window."""
    raw_w = getattr(page, "width", None) if page is not None else None
    if not raw_w and page is not None:
        raw_w = getattr(getattr(page, "window", None), "width", None)
    raw_h = getattr(page, "height", None) if page is not None else None
    if not raw_h and page is not None:
        raw_h = getattr(getattr(page, "window", None), "height", None)
    try:
        width = int(raw_w) if raw_w else 390
    except (TypeError, ValueError):
        width = 390
    try:
        height = int(raw_h) if raw_h else 720
    except (TypeError, ValueError):
        height = 720
    inset = 28 if width < 420 else 40
    chart_w = max(260, min(width - inset, 860))
    chart_h = max(200, min(340, int(height * 0.32)))
    if width < 400:
        chart_h = max(chart_h, 220)
    return chart_w, chart_h


def _money_formatter(value: float, _pos: int = 0) -> str:
    """Human-readable axis labels (1.2K / 1.5M)."""
    abs_v = abs(value)
    if abs_v >= 1_000_000:
        body = f"{value / 1_000_000:.1f}M"
    elif abs_v >= 1_000:
        body = f"{value / 1_000:.1f}K"
    elif abs_v >= 10:
        body = f"{value:.0f}"
    else:
        body = f"{value:.1f}"
    return body.replace(".0M", "M").replace(".0K", "K")


def _nice_ceiling(value: float) -> float:
    if value <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(value))
    n = value / exp
    if n <= 1:
        nice = 1
    elif n <= 2:
        nice = 2
    elif n <= 5:
        nice = 5
    else:
        nice = 10
    return nice * exp


def _empty_chart(message: str, hint: str, *, width: int, height: int) -> ft.Container:
    from lib.presentation.styles import glass_layer

    skin = get_active_skin()
    return ft.Container(
        expand=True,
        width=width,
        height=max(height, 160),
        border_radius=skin.card_radius,
        alignment=ft.Alignment.CENTER,
        **glass_layer(elevated=True),
        content=ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
            controls=[
                ft.Icon(
                    ft.Icons.SHOW_CHART,
                    size=28,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    message,
                    size=13,
                    color=ft.Colors.ON_SURFACE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    hint,
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        ),
    )


def _legend_dot(color: str, label: str) -> ft.Control:
    return ft.Row(
        spacing=6,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(width=8, height=8, border_radius=4, bgcolor=color),
            ft.Text(
                label,
                size=11,
                color=ft.Colors.ON_SURFACE_VARIANT,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ],
    )


def _stroke(color: str, width: float, *, glow: bool = False) -> ft.Paint:
    return ft.Paint(
        color=ft.Colors.with_opacity(0.22, color) if glow else color,
        stroke_width=width,
        style=ft.PaintingStyle.STROKE,
        stroke_cap=ft.StrokeCap.ROUND,
        stroke_join=ft.StrokeJoin.ROUND,
        anti_alias=True,
    )


def _polyline(points: Sequence[tuple[float, float]]) -> list[cv.Path.PathElement]:
    if not points:
        return []
    elements: list[cv.Path.PathElement] = [cv.Path.MoveTo(points[0][0], points[0][1])]
    for x, y in points[1:]:
        elements.append(cv.Path.LineTo(x, y))
    return elements


def _area(points: Sequence[tuple[float, float]], baseline: float) -> list[cv.Path.PathElement]:
    if len(points) < 2:
        return []
    elements = _polyline(points)
    elements.append(cv.Path.LineTo(points[-1][0], baseline))
    elements.append(cv.Path.LineTo(points[0][0], baseline))
    elements.append(cv.Path.Close())
    return elements


def _living_wrap(control: ft.Control) -> ft.Container:
    return ft.Container(
        expand=True,
        content=ft.AnimatedSwitcher(
            content=control,
            duration=520,
            reverse_duration=180,
            transition=ft.AnimatedSwitcherTransition.SCALE,
            switch_in_curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            switch_out_curve=ft.AnimationCurve.EASE_IN,
        ),
        animate_opacity=ft.Animation(480, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(560, ft.AnimationCurve.EASE_OUT_CUBIC),
    )


def _x_keep(n: int, width: int) -> set[int]:
    if n <= 1:
        return {0}
    budget = 4 if width < 340 else (5 if width < 520 else 7)
    budget = min(budget, n)
    if budget >= n:
        return set(range(n))
    step = max(1, (n - 1) / (budget - 1))
    keep = {int(round(i * step)) for i in range(budget)}
    keep.add(0)
    keep.add(n - 1)
    return keep


def _info_line_chart(
    periods: Sequence[str],
    income: Sequence[Decimal | float | int],
    expense: Sequence[Decimal | float | int],
    *,
    width: int,
    height: int,
    language: str,
    dark: bool,
    show_income: bool,
    show_expense: bool,
) -> ft.Control:
    from lib.infrastructure.services.localization import t
    from lib.presentation.styles import glass_layer

    if not periods:
        return _empty_chart(
            t("chart.no_data", language),
            t("chart.dynamics_empty", language),
            width=width,
            height=height,
        )

    skin = get_active_skin()
    inc = [max(0.0, float(v)) for v in income]
    exp = [max(0.0, float(v)) for v in expense]
    while len(inc) < len(periods):
        inc.append(0.0)
    while len(exp) < len(periods):
        exp.append(0.0)
    values: list[float] = []
    if show_income:
        values.extend(inc)
    if show_expense:
        values.extend(exp)
    raw_max = max([0.0, *values])
    max_val = _nice_ceiling(raw_max if raw_max > 0 else 1.0)
    income_color = skin.income_hex(dark=dark)
    expense_color = skin.expense_hex(dark=dark)
    line_color = skin.text_hex(dark=dark)
    muted = skin.muted_hex(dark=dark)
    warn = skin.warn_hex(dark=dark)
    glow = skin.chart_kind == "glow"
    n = len(periods)
    dual = show_income and show_expense
    plot_h = max(height - 40, 168)

    def _shapes(plot_w: float, plot_h_px: float) -> list[cv.Shape]:
        left = 42.0 if plot_w < 360 else 48.0
        right = 12.0
        top = 10.0
        bottom = 22.0
        inner_w = max(plot_w - left - right, 80.0)
        inner_h = max(plot_h_px - top - bottom, 96.0)
        shapes: list[cv.Shape] = []

        def _xy(idx: int, value: float) -> tuple[float, float]:
            x = left + (inner_w * idx / max(n - 1, 1) if n > 1 else inner_w / 2)
            y = top + inner_h * (1.0 - (value / max_val))
            return x, y

        ticks = 4
        for i in range(ticks + 1):
            frac = i / ticks
            value = max_val * frac
            y = top + inner_h * (1.0 - frac)
            shapes.append(
                cv.Line(
                    left,
                    y,
                    left + inner_w,
                    y,
                    paint=_stroke(ft.Colors.with_opacity(0.22, muted), 1),
                )
            )
            shapes.append(
                cv.Text(
                    2,
                    y - 7,
                    _money_formatter(value),
                    style=ft.TextStyle(size=10, color=muted, weight=ft.FontWeight.W_500),
                )
            )

        baseline = top + inner_h

        def _draw_series(series: Sequence[float], color: str, *, mark: bool) -> None:
            pts = [_xy(i, series[i]) for i in range(n)]
            fill = _area(pts, baseline)
            if fill:
                shapes.append(
                    cv.Path(
                        fill,
                        paint=ft.Paint(
                            color=ft.Colors.with_opacity(0.16 if glow else 0.10, color),
                            style=ft.PaintingStyle.FILL,
                        ),
                    )
                )
            path = _polyline(pts)
            if glow:
                shapes.append(cv.Path(path, paint=_stroke(color, 9, glow=True)))
            if len(pts) >= 2 and series[-1] < series[-2]:
                shapes.append(cv.Path(_polyline(pts[:-1]), paint=_stroke(color, 2.8)))
                shapes.append(
                    cv.Path(_polyline([pts[-2], pts[-1]]), paint=_stroke(expense_color, 3.1))
                )
            else:
                shapes.append(cv.Path(path, paint=_stroke(color, 2.8)))
            last = pts[-1]
            if mark:
                shapes.append(cv.Circle(last[0], last[1], 8, paint=ft.Paint(color=warn)))
                shapes.append(
                    cv.Circle(
                        last[0],
                        last[1],
                        3.5,
                        paint=ft.Paint(color=line_color if dark else "#FFFFFF"),
                    )
                )

        if show_income:
            _draw_series(inc, income_color if dual else line_color, mark=not show_expense)
        if show_expense:
            _draw_series(exp, expense_color if dual else line_color, mark=True)

        keep = _x_keep(n, int(plot_w))
        for i in sorted(keep):
            x = _xy(i, 0.0)[0]
            label = periods[i]
            shapes.append(
                cv.Text(
                    x - (len(label) * 2.6),
                    baseline + 4,
                    label,
                    style=ft.TextStyle(size=10, color=muted, weight=ft.FontWeight.W_500),
                )
            )
        return shapes

    canvas = cv.Canvas(
        expand=True,
        width=width,
        height=plot_h,
        shapes=_shapes(float(width), float(plot_h)),
        resize_interval=16,
    )
    last_size = [float(width), float(plot_h)]

    def _on_resize(e: cv.CanvasResizeEvent) -> None:
        w = float(getattr(e, "width", 0) or 0)
        h = float(getattr(e, "height", 0) or 0)
        if w < 60 or h < 60:
            return
        if abs(w - last_size[0]) < 1 and abs(h - last_size[1]) < 1:
            return
        last_size[0], last_size[1] = w, h
        canvas.shapes = _shapes(w, h)
        canvas.update()

    canvas.on_resize = _on_resize
    legend: list[ft.Control] = []
    if show_income:
        legend.append(
            _legend_dot(income_color if dual else line_color, t("transaction.income", language))
        )
    if show_expense:
        legend.append(
            _legend_dot(expense_color if dual else line_color, t("transaction.expense", language))
        )
    last_bits: list[str] = [t("chart.last", language)]
    if show_income:
        last_bits.append(_money_formatter(inc[-1]))
    if show_expense:
        last_bits.append(_money_formatter(exp[-1]))
    plot = ft.Container(
        expand=True,
        height=plot_h,
        border_radius=skin.card_radius,
        padding=ft.Padding.only(top=4, bottom=2, right=4),
        content=canvas,
        **glass_layer(elevated=True, opacity=0.22),
    )
    return _living_wrap(
        ft.Column(
            tight=True,
            spacing=6,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                    spacing=8,
                    run_spacing=4,
                    controls=[
                        ft.Row(spacing=12, wrap=True, controls=legend),
                        ft.Text(
                            " · ".join(last_bits),
                            size=11,
                            color=muted,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                ),
                plot,
            ],
        )
    )


def _info_donut_chart(
    labels: Sequence[str],
    values: Sequence[Decimal | float | int],
    *,
    width: int,
    height: int,
    language: str,
    dark: bool,
    show_legend: bool,
    empty_message: str | None = None,
) -> ft.Control:
    from lib.infrastructure.services.localization import t

    nums = [float(v) for v in values]
    if not nums or sum(nums) <= 0:
        return _empty_chart(
            empty_message or t("chart.no_expenses", language),
            t("chart.add_month_ops", language),
            width=width,
            height=height,
        )

    skin = get_active_skin()
    palette = _chart_palette()
    total = sum(nums)
    size = max(148, min(int(width * 0.72), height - 8, 220 if width < 400 else 240))
    cx = size / 2
    cy = size / 2
    radius = size * 0.34
    stroke = max(12.0, size * 0.10)
    track = skin.dark_surface_3 if dark else skin.light_surface_3
    shapes: list[cv.Shape] = [
        cv.Circle(cx, cy, radius, paint=_stroke(track, stroke)),
    ]
    start = -math.pi / 2
    for idx, amount in enumerate(nums):
        share = amount / total if total else 0
        sweep = share * 2 * math.pi
        color = palette[idx % len(palette)]
        shapes.append(
            cv.Arc(
                cx - radius,
                cy - radius,
                radius * 2,
                radius * 2,
                start_angle=start,
                sweep_angle=max(sweep, 0.02),
                paint=_stroke(color, stroke),
            )
        )
        start += sweep

    top_share = nums[0] / total * 100 if total else 0
    center = ft.Column(
        tight=True,
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Text(
                f"{top_share:.0f}%",
                size=24,
                weight=ft.FontWeight.W_800,
                color=skin.text_hex(dark=dark),
            ),
            ft.Text(
                _money_formatter(total),
                size=11,
                color=skin.muted_hex(dark=dark),
            ),
        ],
    )
    ring = cv.Canvas(
        width=size,
        height=size,
        expand=False,
        shapes=shapes,
        content=ft.Container(alignment=ft.Alignment.CENTER, content=center),
    )
    donut = ft.Container(
        width=size,
        height=size,
        alignment=ft.Alignment.CENTER,
        clip_behavior=ft.ClipBehavior.NONE,
        content=ring,
    )
    legend: list[ft.Control] = []
    if show_legend:
        for idx, (label, amount) in enumerate(zip(labels, nums)):
            share = amount / total * 100 if total else 0
            legend.append(
                _legend_dot(
                    palette[idx % len(palette)],
                    f"{label} · {_money_formatter(amount)} · {share:.0f}%",
                )
            )
    return _living_wrap(
        ft.Column(
            tight=True,
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=donut,
                ),
                *(
                    [ft.Column(spacing=5, tight=True, expand=True, controls=legend)]
                    if legend
                    else []
                ),
            ],
        )
    )


def build_pie_chart_image(
    labels: Sequence[str],
    values: Sequence[Decimal | float | int],
    *,
    title: str = "",
    width: int = 360,
    height: int = 280,
    dark: bool = True,
    language: str = "ru",
    show_legend: bool = True,
    empty_message: str | None = None,
) -> ft.Control:
    """Category share donut used on every platform."""
    _ = title
    return _info_donut_chart(
        labels,
        values,
        width=width,
        height=height,
        language=language,
        dark=dark,
        show_legend=show_legend,
        empty_message=empty_message,
    )


def build_line_chart_image(
    periods: Sequence[str],
    income: Sequence[Decimal | float | int],
    expense: Sequence[Decimal | float | int],
    *,
    title: str = "",
    width: int = 360,
    height: int = 260,
    dark: bool = True,
    language: str = "ru",
    show_income: bool = True,
    show_expense: bool = True,
) -> ft.Control:
    """Income / expense line chart with grid, last-point marker, and drop highlight."""
    _ = title
    return _info_line_chart(
        periods,
        income,
        expense,
        width=width,
        height=height,
        language=language,
        dark=dark,
        show_income=show_income,
        show_expense=show_expense,
    )
