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


class _SafeCanvas(cv.Canvas):
    """Canvas that drops events when already unmounted (Flet raises on ``.page``)."""

    def before_event(self, e):  # noqa: ANN001
        parent = self
        try:
            from flet.controls.page import Page

            while parent is not None:
                if isinstance(parent, Page):
                    return True
                parent = parent.parent
        except Exception:  # noqa: BLE001
            return False
        return False


def _chart_palette() -> Sequence[str]:
    colors = get_active_skin().chart_colors
    return colors if colors else _CHART_COLORS


def _prefer_native_charts() -> bool:
    """Always native so every platform renders the same widgets."""
    return True


def chart_layout(page: ft.Page | None = None) -> tuple[int, int]:
    """Width and plot height that fill the current window."""
    from lib.presentation.responsive import page_height, page_width

    width = int(page_width(page))
    height = int(page_height(page))
    inset = 28 if width < 420 else 40
    chart_w = max(240, min(width - inset, 860))
    chart_h = max(180, min(340, int(height * 0.32)))
    if width < 360:
        chart_h = max(180, min(chart_h, 220))
    elif width < 400:
        chart_h = max(chart_h, 200)
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


def _stroke(
    color: str,
    width: float,
    *,
    glow: bool = False,
    cap: ft.StrokeCap = ft.StrokeCap.ROUND,
) -> ft.Paint:
    return ft.Paint(
        color=ft.Colors.with_opacity(0.22, color) if glow else color,
        stroke_width=width,
        style=ft.PaintingStyle.STROKE,
        stroke_cap=cap,
        stroke_join=ft.StrokeJoin.ROUND if cap == ft.StrokeCap.ROUND else ft.StrokeJoin.MITER,
        anti_alias=True,
    )


def _arc_stroke(color: str, width: float) -> ft.Paint:
    """Donut segments must use BUTT caps so slices meet flush (no blob overlaps)."""
    return _stroke(color, width, cap=ft.StrokeCap.BUTT)


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


_QUEUED_DRAWS: list[tuple] = []


def _start_draw(
    canvas: cv.Canvas,
    make_shapes,
    *,
    page: ft.Page | None,
    frames: int = 36,
    playing: list[bool] | None = None,
) -> None:
    """Queue a draw-from-empty animation until the canvas is on the page."""
    flag = playing if playing is not None else [False]
    if page is None or frames <= 1:
        canvas.shapes = make_shapes(1.0)
        flag[0] = False
        return
    canvas.shapes = make_shapes(0.0)
    flag[0] = True
    _QUEUED_DRAWS.append((canvas, make_shapes, max(8, frames), flag, page))


async def play_queued_charts() -> None:
    """Play chart animations after parents are mounted (reload / refresh)."""
    batch = _QUEUED_DRAWS[:]
    _QUEUED_DRAWS.clear()
    if not batch:
        return

    async def _snap(canvas, make_shapes, flag: list[bool]) -> None:
        try:
            canvas.shapes = make_shapes(1.0)
        except Exception:  # noqa: BLE001
            pass
        flag[0] = False

    async def _play(canvas, make_shapes, frames: int, flag: list[bool], page: ft.Page) -> None:
        from lib.presentation.utils import control_page, safe_update

        try:
            mounted = False
            for _ in range(12):
                if control_page(canvas) is None:
                    await asyncio.sleep(0.02)
                    continue
                mounted = True
                break
            if not mounted:
                await _snap(canvas, make_shapes, flag)
                return
            total = frames
            for i in range(1, total + 1):
                if control_page(canvas) is None:
                    await _snap(canvas, make_shapes, flag)
                    return
                t = i / total
                eased = 1.0 - (1.0 - t) ** 2
                canvas.shapes = make_shapes(eased)
                safe_update(canvas)
                await asyncio.sleep(0.016)
            if control_page(canvas) is not None:
                canvas.shapes = make_shapes(1.0)
                safe_update(canvas)
        except Exception:  # noqa: BLE001
            await _snap(canvas, make_shapes, flag)
            return
        finally:
            flag[0] = False

    await asyncio.gather(*(_play(*item) for item in batch))


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


def _normalize_donut_sweeps(amounts: Sequence[float]) -> list[float]:
    """Turn amounts into radian sweeps that always fill the ring.

    Tiny categories get a minimum visible arc, then everything is scaled so
    the total is exactly ``2π`` (no holes from skipped slices).
    """
    positive = [max(0.0, float(v)) for v in amounts]
    total = sum(positive)
    if total <= 0:
        return []
    raw = [(v / total) * 2 * math.pi for v in positive]
    n = len(raw)
    # ~6° floor so Canvas Arc + BUTT caps still paint tiny shares.
    min_vis = min(0.11, (2 * math.pi) / max(n * 2.5, 3))
    boosted = [max(s, min_vis) if s > 0 else 0.0 for s in raw]
    boost_sum = sum(boosted) or 1.0
    return [(s / boost_sum) * 2 * math.pi for s in boosted]


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


def _x_keep(n: int, width: int, *, compact: bool = False) -> set[int]:
    if n <= 1:
        return {0}
    if compact:
        budget = 3 if width < 340 else 4
    else:
        budget = 4 if width < 340 else (5 if width < 520 else 7)
    budget = min(budget, n)
    if budget >= n:
        return set(range(n))
    step = max(1, (n - 1) / (budget - 1))
    keep = {int(round(i * step)) for i in range(budget)}
    keep.add(0)
    keep.add(n - 1)
    return keep


def _downsample_line(
    periods: list[str],
    series: list[float],
    inc: list[float],
    exp: list[float],
    *,
    max_points: int,
) -> tuple[list[str], list[float], list[float], list[float]]:
    """Evenly thin a dense series while keeping endpoints (compact charts)."""
    n = len(series)
    if n <= max_points or max_points < 3:
        return periods, series, inc, exp
    step = (n - 1) / (max_points - 1)
    indices = sorted({0, n - 1, *(int(round(i * step)) for i in range(1, max_points - 1))})
    return (
        [periods[i] for i in indices],
        [series[i] for i in indices],
        [inc[i] for i in indices],
        [exp[i] for i in indices],
    )


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
    compact: bool = False,
    animate: bool = True,
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
    if compact and len(series) > 40:
        periods_list = list(periods)
        periods_list, series, inc, exp = _downsample_line(
            periods_list, series, inc, exp, max_points=40
        )
        periods = periods_list
    n = len(periods)
    lo = _nice_floor(min(0.0, min(series)))
    hi = _nice_ceiling(max(0.0, max(series), 1.0))
    if hi <= lo:
        hi = lo + 1.0
    # Slight pad so the line doesn't hug the top/bottom edge.
    pad = (hi - lo) * (0.06 if compact else 0.04)
    lo -= pad
    hi += pad
    span = hi - lo
    income_color = skin.income_hex(dark=dark)
    expense_color = skin.expense_hex(dark=dark)
    line_color = skin.text_hex(dark=dark)
    muted = skin.muted_hex(dark=dark)
    glow = skin.chart_kind == "glow"
    # Density-aware stroke: many points → thinner line, never stretch the plot.
    density = max(1.0, n / 14.0)
    if compact:
        plot_h = max(int(height), 128)
        tick_count = 3  # 4 Y labels (lo … hi) with even spacing
        label_size = 8
        sample_labels = [
            _money_formatter(lo + span * i / 3) for i in range(4)
        ]
        label_chars = max(len(s) for s in sample_labels)
        margin_left = max(34.0, 8.0 + label_chars * 5.6)
        margin_right = 10.0
        margin_top = 12.0
        margin_bottom = 20.0
        line_w = max(1.2, 1.7 / (density**0.4))
        end_r_outer = max(3.0, 4.5 / (density**0.3))
        end_r_inner = max(1.4, 2.2 / (density**0.3))
        anim_frames = 1 if not animate else 16
    else:
        plot_h = max(height - 40, 168)
        margin_left = 42.0 if width < 360 else 48.0
        margin_right = 12.0
        margin_top = 10.0
        margin_bottom = 22.0
        line_w = max(1.4, 2.8 / (density**0.35))
        tick_count = 4
        label_size = 10
        end_r_outer, end_r_inner = 8.0, 3.5
        anim_frames = 1 if not animate else 18

    def _layout(plot_w: float, plot_h_px: float) -> tuple[float, float, float, float]:
        left = margin_left if plot_w >= 200 else max(28.0, margin_left * 0.85)
        right = margin_right
        top = margin_top
        bottom = margin_bottom
        inner_w = max(plot_w - left - right, 40.0)
        # Never force inner_h larger than the canvas — that pushed the line off-screen.
        inner_h = max(plot_h_px - top - bottom, 20.0)
        return left, top, inner_w, inner_h

    def _xy(idx: int, value: float, plot_w: float, plot_h_px: float) -> tuple[float, float]:
        left, top, inner_w, inner_h = _layout(plot_w, plot_h_px)
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
        left, top, inner_w, inner_h = _layout(plot_w, plot_h_px)
        shapes: list[cv.Shape] = []
        ticks = tick_count
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
                    y - (7 if i == ticks else (2 if i == 0 else 5)),
                    _money_formatter(value),
                    style=ft.TextStyle(
                        size=label_size, color=muted, weight=ft.FontWeight.W_500
                    ),
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
                            color=ft.Colors.with_opacity(
                                0.12 if compact else (0.16 if glow else 0.10),
                                fill_color,
                            ),
                            style=ft.PaintingStyle.FILL,
                        ),
                    )
                )
            if glow and not compact:
                shapes.append(
                    cv.Path(_polyline(xy), paint=_stroke(income_color, 9, glow=True))
                )
            for i in range(len(pts) - 1):
                color = income_color if pts[i + 1][2] >= pts[i][2] else expense_color
                shapes.append(
                    cv.Path(
                        _polyline([(pts[i][0], pts[i][1]), (pts[i + 1][0], pts[i + 1][1])]),
                        paint=_stroke(color, line_w),
                    )
                )
            last = pts[-1]
            shapes.append(
                cv.Circle(
                    last[0],
                    last[1],
                    end_r_outer,
                    paint=ft.Paint(
                        color=income_color if last[2] >= 0 else expense_color
                    ),
                )
            )
            shapes.append(
                cv.Circle(
                    last[0],
                    last[1],
                    end_r_inner,
                    paint=ft.Paint(color=line_color if dark else "#FFFFFF"),
                )
            )
        elif len(pts) == 1:
            last = pts[-1]
            shapes.append(
                cv.Circle(last[0], last[1], 3 if compact else 4, paint=ft.Paint(color=income_color))
            )
        baseline = top + inner_h
        keep = _x_keep(n, int(plot_w), compact=compact)
        for i in sorted(keep):
            x = _xy(i, series[i], plot_w, plot_h_px)[0]
            label = periods[i]
            if not label:
                continue
            shapes.append(
                cv.Text(
                    x - (len(label) * 2.4),
                    baseline + 2,
                    label,
                    style=ft.TextStyle(
                        size=label_size, color=muted, weight=ft.FontWeight.W_500
                    ),
                )
            )
        if 0 <= selected_idx < n and progress >= 0.5 and not compact:
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

    # Compact sparkline and full charts both fill the card width.
    canvas = _SafeCanvas(
        expand=True,
        width=None if compact else width,
        height=plot_h,
        shapes=_shapes(
            float(width),
            float(plot_h),
            1.0 if page is None or not animate else 0.0,
        ),
        resize_interval=32,
    )
    last_size = [float(width), float(plot_h)]
    last_progress = [1.0 if page is None or not animate else 0.0]
    playing = [bool(page is not None and animate)]
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
        w = float(getattr(e, "width", 0) or 0)
        h = float(getattr(e, "height", 0) or 0)
        min_side = 40 if compact else 60
        if w < min_side or h < min_side:
            return
        # Keep height locked for compact so the home card does not stretch.
        if compact:
            h = float(plot_h)
        if abs(w - last_size[0]) < 1 and abs(h - last_size[1]) < 1:
            return
        last_size[0], last_size[1] = w, h
        if playing[0]:
            return
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

    _start_draw(canvas, _make, page=page, frames=anim_frames, playing=playing)
    plot_kwargs: dict = {
        "height": plot_h,
        "border_radius": skin.card_radius,
        "padding": ft.Padding.only(top=2 if compact else 4, bottom=2, right=4),
        "content": ft.GestureDetector(
            expand=True,
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap_down=None if compact else _on_pointer,
            content=canvas,
        ),
    }
    if not compact:
        plot_kwargs["expand"] = True
        plot_kwargs.update(glass_layer(elevated=True, opacity=0.22))
    else:
        plot_kwargs["bgcolor"] = ft.Colors.with_opacity(0.12, ft.Colors.SURFACE)
        plot_kwargs["clip_behavior"] = ft.ClipBehavior.HARD_EDGE
    plot = ft.Container(**plot_kwargs)
    if compact:
        return ft.Container(
            height=plot_h,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=plot,
        )
    legend = [
        _legend_dot(income_color, t("chart.net_up", language)),
        _legend_dot(expense_color, t("chart.net_down", language)),
    ]
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
    animate: bool = True,
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
    sweeps = _normalize_donut_sweeps(nums)
    gap = 0.012 if len(sweeps) > 1 else 0.0
    slices: list[tuple[str, float]] = [
        (palette[idx % len(palette)], sweeps[idx]) for idx in range(len(sweeps))
    ]

    selected = [0]

    def _shapes(progress: float) -> list[cv.Shape]:
        budget = max(0.0, min(1.0, progress)) * 2 * math.pi
        shapes: list[cv.Shape] = [
            cv.Circle(cx, cy, radius, paint=_arc_stroke(track, stroke)),
        ]
        start = -math.pi / 2
        remaining = budget
        for idx, (color, sweep) in enumerate(slices):
            if remaining <= 0:
                break
            take = min(sweep, remaining)
            remaining -= take
            if take <= 1e-6:
                start += take
                continue
            draw = take
            # Seams only on larger slices — tiny ones keep full width.
            if len(slices) > 1 and take >= sweep - 1e-9 and sweep > gap * 8:
                draw = max(take - gap, take * 0.92)
            if idx == selected[0]:
                shapes.append(
                    cv.Arc(
                        cx - radius,
                        cy - radius,
                        radius * 2,
                        radius * 2,
                        start_angle=start,
                        sweep_angle=draw,
                        paint=_arc_stroke(
                            ft.Colors.with_opacity(0.28, color), stroke + 7
                        ),
                    )
                )
            shapes.append(
                cv.Arc(
                    cx - radius,
                    cy - radius,
                    radius * 2,
                    radius * 2,
                    start_angle=start,
                    sweep_angle=draw,
                    paint=_arc_stroke(color, stroke),
                )
            )
            start += take
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
    ring = _SafeCanvas(
        width=size,
        height=size,
        expand=False,
        shapes=_shapes(1.0 if page is None or not animate else 0.0),
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

    _start_draw(
        ring,
        _shapes,
        page=page,
        frames=1 if not animate else 36,
    )
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
    animate: bool = True,
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
        animate=animate,
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
    compact: bool = False,
    animate: bool = True,
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
        compact=compact,
        animate=animate,
    )

