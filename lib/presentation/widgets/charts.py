"""Responsive Flet charts — line plots with axes, readable on any screen."""

from __future__ import annotations

import asyncio
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


def _nice_floor(value: float) -> float:
    if value >= 0:
        return 0.0
    return -_nice_ceiling(-value)


def _start_draw(
    canvas: cv.Canvas,
    make_shapes,
    *,
    page: ft.Page | None,
    frames: int = 36,
    playing: list[bool] | None = None,
) -> None:
    """Draw the chart from empty to full after the canvas is mounted."""
    flag = playing if playing is not None else [False]
    if page is None:
        canvas.shapes = make_shapes(1.0)
        return
    canvas.shapes = make_shapes(0.0)
    flag[0] = True

    async def _play() -> None:
        from lib.presentation.utils import control_page, safe_update

        try:
            mounted = False
            for _ in range(80):
                if control_page(canvas) is not None:
                    mounted = True
                    break
                await asyncio.sleep(0.02)
            if not mounted:
                return
            total = max(16, frames)
            for i in range(1, total + 1):
                if control_page(canvas) is None:
                    return
                t = i / total
                eased = 1.0 - (1.0 - t) ** 2
                canvas.shapes = make_shapes(eased)
                safe_update(canvas)
                await asyncio.sleep(0.018)
            if control_page(canvas) is None:
                return
            canvas.shapes = make_shapes(1.0)
            safe_update(canvas)
        except Exception:  # noqa: BLE001
            return
        finally:
            flag[0] = False

    from lib.presentation.utils import run_async

    run_async(page, _play)


def _chart_shell(control: ft.Control) -> ft.Container:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=control,
    )


def _event_xy(event: object) -> tuple[float, float] | None:
    pos = getattr(event, "local_position", None)
    if pos is None:
        return None
    x = getattr(pos, "x", None)
    y = getattr(pos, "y", None)
    if x is None or y is None:
        try:
            x, y = pos
        except Exception:  # noqa: BLE001
            return None
    return float(x), float(y)


def _nearest_period_index(local_x: float, *, n: int, plot_w: float) -> int:
    """Map a tap X to the closest period on the line chart."""
    if n <= 1:
        return 0
    left = 42.0 if plot_w < 360 else 48.0
    inner_w = max(plot_w - left - 12.0, 80.0)
    ratio = (local_x - left) / inner_w
    return int(round(max(0.0, min(1.0, ratio)) * (n - 1)))


def _donut_slice_index(dx: float, dy: float, sweeps: Sequence[float]) -> int:
    """Map a tap relative to the donut center onto a slice."""
    if not sweeps:
        return 0
    angle = math.atan2(dy, dx) + math.pi / 2
    while angle < 0:
        angle += 2 * math.pi
    while angle >= 2 * math.pi:
        angle -= 2 * math.pi
    acc = 0.0
    last = len(sweeps) - 1
    for idx, sweep in enumerate(sweeps):
        acc += sweep
        if angle <= acc + 1e-9:
            return idx
    return last


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
    page: ft.Page | None = None,
) -> ft.Control:
    from lib.infrastructure.services.localization import t
    from lib.presentation.styles import glass_layer

    _ = show_income, show_expense
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
    running = 0.0
    series: list[float] = []
    for i in range(len(periods)):
        running += inc[i] - exp[i]
        series.append(running)
    n = len(periods)
    lo = _nice_floor(min(0.0, min(series)))
    hi = _nice_ceiling(max(0.0, max(series), 1.0))
    if hi <= lo:
        hi = lo + 1.0
    span = hi - lo
    income_color = skin.income_hex(dark=dark)
    expense_color = skin.expense_hex(dark=dark)
    line_color = skin.text_hex(dark=dark)
    muted = skin.muted_hex(dark=dark)
    glow = skin.chart_kind == "glow"
    plot_h = max(height - 40, 168)

    def _xy(idx: int, value: float, plot_w: float, plot_h_px: float) -> tuple[float, float]:
        left = 42.0 if plot_w < 360 else 48.0
        right = 12.0
        top = 10.0
        bottom = 22.0
        inner_w = max(plot_w - left - right, 80.0)
        inner_h = max(plot_h_px - top - bottom, 96.0)
        x = left + (inner_w * idx / max(n - 1, 1) if n > 1 else inner_w / 2)
        y = top + inner_h * (1.0 - ((value - lo) / span))
        return x, y

    def _visible_points(
        progress: float, plot_w: float, plot_h_px: float
    ) -> list[tuple[float, float, float]]:
        """(x, y, value) along the cumulative path up to ``progress``."""
        full = [_xy(i, series[i], plot_w, plot_h_px) + (series[i],) for i in range(n)]
        if n == 1:
            return full if progress > 0 else []
        pos = max(0.0, min(1.0, progress)) * (n - 1)
        last_i = int(pos)
        frac = pos - last_i
        out = [(full[i][0], full[i][1], full[i][2]) for i in range(last_i + 1)]
        if last_i < n - 1:
            x0, y0, v0 = full[last_i]
            x1, y1, v1 = full[last_i + 1]
            out.append((x0 + (x1 - x0) * frac, y0 + (y1 - y0) * frac, v0 + (v1 - v0) * frac))
        return out

    def _shapes(
        plot_w: float,
        plot_h_px: float,
        progress: float = 1.0,
        selected_idx: int = -1,
    ) -> list[cv.Shape]:
        left = 42.0 if plot_w < 360 else 48.0
        right = 12.0
        top = 10.0
        bottom = 22.0
        inner_w = max(plot_w - left - right, 80.0)
        inner_h = max(plot_h_px - top - bottom, 96.0)
        shapes: list[cv.Shape] = []
        ticks = 4
        for i in range(ticks + 1):
            frac = i / ticks
            value = lo + span * frac
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
        zero_y = top + inner_h * (1.0 - ((0.0 - lo) / span))
        if lo < 0 < hi:
            shapes.append(
                cv.Line(
                    left,
                    zero_y,
                    left + inner_w,
                    zero_y,
                    paint=_stroke(ft.Colors.with_opacity(0.45, muted), 1.2),
                )
            )
        pts = _visible_points(progress, plot_w, plot_h_px)
        if len(pts) >= 2:
            xy = [(p[0], p[1]) for p in pts]
            fill = _area(xy, zero_y)
            if fill:
                last_v = pts[-1][2]
                fill_color = income_color if last_v >= 0 else expense_color
                shapes.append(
                    cv.Path(
                        fill,
                        paint=ft.Paint(
                            color=ft.Colors.with_opacity(0.16 if glow else 0.10, fill_color),
                            style=ft.PaintingStyle.FILL,
                        ),
                    )
                )
            if glow:
                shapes.append(cv.Path(_polyline(xy), paint=_stroke(income_color, 9, glow=True)))
            for i in range(len(pts) - 1):
                color = income_color if pts[i + 1][2] >= pts[i][2] else expense_color
                shapes.append(
                    cv.Path(
                        _polyline([(pts[i][0], pts[i][1]), (pts[i + 1][0], pts[i + 1][1])]),
                        paint=_stroke(color, 2.8),
                    )
                )
            last = pts[-1]
            shapes.append(cv.Circle(last[0], last[1], 8, paint=ft.Paint(color=income_color if last[2] >= 0 else expense_color)))
            shapes.append(
                cv.Circle(
                    last[0],
                    last[1],
                    3.5,
                    paint=ft.Paint(color=line_color if dark else "#FFFFFF"),
                )
            )
        elif len(pts) == 1:
            last = pts[-1]
            shapes.append(cv.Circle(last[0], last[1], 4, paint=ft.Paint(color=income_color)))
        baseline = top + inner_h
        keep = _x_keep(n, int(plot_w))
        for i in sorted(keep):
            x = _xy(i, series[i], plot_w, plot_h_px)[0]
            label = periods[i]
            shapes.append(
                cv.Text(
                    x - (len(label) * 2.6),
                    baseline + 4,
                    label,
                    style=ft.TextStyle(size=10, color=muted, weight=ft.FontWeight.W_500),
                )
            )
        if 0 <= selected_idx < n and progress >= 0.5:
            sx, sy = _xy(selected_idx, series[selected_idx], plot_w, plot_h_px)
            mark = income_color if series[selected_idx] >= 0 else expense_color
            shapes.append(
                cv.Line(
                    sx,
                    top,
                    sx,
                    baseline,
                    paint=_stroke(ft.Colors.with_opacity(0.35, muted), 1),
                )
            )
            shapes.append(cv.Circle(sx, sy, 9, paint=ft.Paint(color=mark)))
            shapes.append(
                cv.Circle(
                    sx,
                    sy,
                    3.8,
                    paint=ft.Paint(color=line_color if dark else "#FFFFFF"),
                )
            )
        return shapes

    canvas = cv.Canvas(
        expand=True,
        width=width,
        height=plot_h,
        shapes=_shapes(float(width), float(plot_h), 1.0 if page is None else 0.0),
        resize_interval=16,
    )
    last_size = [float(width), float(plot_h)]
    last_progress = [1.0 if page is None else 0.0]
    playing = [page is not None]
    selected = [-1]
    last_bits = f"{t('chart.last', language)} · {_money_formatter(series[-1])}"
    caption = ft.Text(
        last_bits,
        size=11,
        color=muted,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    def _on_resize(e: cv.CanvasResizeEvent) -> None:
        if playing[0]:
            return
        w = float(getattr(e, "width", 0) or 0)
        h = float(getattr(e, "height", 0) or 0)
        if w < 60 or h < 60:
            return
        if abs(w - last_size[0]) < 1 and abs(h - last_size[1]) < 1:
            return
        last_size[0], last_size[1] = w, h
        canvas.shapes = _shapes(w, h, last_progress[0], selected[0])
        from lib.presentation.utils import safe_update

        safe_update(canvas)

    canvas.on_resize = _on_resize

    def _make(progress: float) -> list[cv.Shape]:
        last_progress[0] = progress
        return _shapes(last_size[0], last_size[1], progress, selected[0])

    def _point_caption(idx: int) -> str:
        from lib.presentation.utils import tr

        return tr(
            "chart.point",
            language,
            period=periods[idx],
            income=_money_formatter(inc[idx]),
            expense=_money_formatter(exp[idx]),
            net=_money_formatter(series[idx]),
        )

    def _pick(idx: int, *, buzz: bool) -> None:
        if idx == selected[0]:
            if buzz:
                from lib.presentation.haptics import haptic

                haptic("selection")
            return
        selected[0] = idx
        caption.value = _point_caption(idx)
        canvas.shapes = _shapes(last_size[0], last_size[1], last_progress[0], idx)
        from lib.presentation.utils import safe_update

        safe_update(canvas)
        safe_update(caption)
        if buzz:
            from lib.presentation.haptics import haptic

            haptic("selection")

    def _on_pointer(event) -> None:
        xy = _event_xy(event)
        if xy is None:
            return
        _pick(
            _nearest_period_index(xy[0], n=n, plot_w=last_size[0]),
            buzz=True,
        )

    _start_draw(canvas, _make, page=page, frames=40, playing=playing)
    legend = [
        _legend_dot(income_color, t("chart.net_up", language)),
        _legend_dot(expense_color, t("chart.net_down", language)),
    ]
    plot = ft.Container(
        expand=True,
        height=plot_h,
        border_radius=skin.card_radius,
        padding=ft.Padding.only(top=4, bottom=2, right=4),
        content=ft.GestureDetector(
            expand=True,
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap_down=_on_pointer,
            content=canvas,
        ),
        **glass_layer(elevated=True, opacity=0.22),
    )
    return _chart_shell(
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
                        caption,
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
    page: ft.Page | None = None,
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
    slices: list[tuple[str, float]] = []
    for idx, amount in enumerate(nums):
        slices.append((palette[idx % len(palette)], (amount / total) * 2 * math.pi))

    selected = [0]
    sweeps = [item[1] for item in slices]

    def _shapes(progress: float) -> list[cv.Shape]:
        budget = max(0.0, min(1.0, progress)) * 2 * math.pi
        shapes: list[cv.Shape] = [
            cv.Circle(cx, cy, radius, paint=_stroke(track, stroke)),
        ]
        start = -math.pi / 2
        remaining = budget
        for idx, (color, sweep) in enumerate(slices):
            if remaining <= 0:
                break
            take = min(sweep, remaining)
            if take > 0.004:
                width = stroke + 3 if idx == selected[0] else stroke
                shapes.append(
                    cv.Arc(
                        cx - radius,
                        cy - radius,
                        radius * 2,
                        radius * 2,
                        start_angle=start,
                        sweep_angle=take,
                        paint=_stroke(color, width, glow=False),
                    )
                )
            start += take
            remaining -= take
        return shapes

    top_share = nums[0] / total * 100 if total else 0
    share_label = ft.Text(
        f"{top_share:.0f}%",
        size=24,
        weight=ft.FontWeight.W_800,
        color=skin.text_hex(dark=dark),
    )
    amount_label = ft.Text(
        _money_formatter(total),
        size=11,
        color=skin.muted_hex(dark=dark),
        text_align=ft.TextAlign.CENTER,
    )
    name_label = ft.Text(
        t("chart.total", language),
        size=10,
        color=skin.muted_hex(dark=dark),
        text_align=ft.TextAlign.CENTER,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    center = ft.Column(
        tight=True,
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[share_label, amount_label, name_label],
    )
    ring = cv.Canvas(
        width=size,
        height=size,
        expand=False,
        shapes=_shapes(1.0 if page is None else 0.0),
        content=ft.Container(alignment=ft.Alignment.CENTER, content=center),
    )

    def _show_slice(idx: int, *, buzz: bool) -> None:
        idx = max(0, min(idx, len(nums) - 1))
        if idx != selected[0]:
            selected[0] = idx
            share = nums[idx] / total * 100 if total else 0
            share_label.value = f"{share:.0f}%"
            amount_label.value = _money_formatter(nums[idx])
            name_label.value = str(labels[idx] if idx < len(labels) else "")
            ring.shapes = _shapes(1.0)
            from lib.presentation.utils import safe_update

            safe_update(ring)
            safe_update(share_label)
            safe_update(amount_label)
            safe_update(name_label)
        if buzz:
            from lib.presentation.haptics import haptic

            haptic("selection")

    def _on_pointer(event) -> None:
        xy = _event_xy(event)
        if xy is None:
            return
        _show_slice(_donut_slice_index(xy[0] - cx, xy[1] - cy, sweeps), buzz=True)

    _start_draw(ring, _shapes, page=page, frames=42)
    donut = ft.Container(
        width=size,
        height=size,
        alignment=ft.Alignment.CENTER,
        clip_behavior=ft.ClipBehavior.NONE,
        content=ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap_down=_on_pointer,
            content=ring,
        ),
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
    return _chart_shell(
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
    page: ft.Page | None = None,
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
        page=page,
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
    page: ft.Page | None = None,
) -> ft.Control:
    """Single cumulative net line: income lifts it, expense drops it."""
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
        page=page,
    )

