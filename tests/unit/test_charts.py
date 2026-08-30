"""Chart hit-testing helpers and donut stroke style."""

from __future__ import annotations

import math

import flet as ft

from lib.presentation.widgets.charts import (
    _arc_stroke,
    _donut_slice_index,
    _nearest_period_index,
    _normalize_donut_sweeps,
    _stroke,
)


def test_nearest_period_index_edges() -> None:
    assert _nearest_period_index(0, n=5, plot_w=400) == 0
    assert _nearest_period_index(400, n=5, plot_w=400) == 4
    assert _nearest_period_index(200, n=1, plot_w=400) == 0


def test_nearest_period_index_midpoint() -> None:
    # left=48, inner=340 on a 400-wide plot with 5 points (indexes 0..4)
    left = 48.0
    inner = 400.0 - 48.0 - 12.0
    x = left + inner * 0.5
    assert _nearest_period_index(x, n=5, plot_w=400) == 2


def test_donut_slice_index_quarters() -> None:
    sweeps = [math.pi / 2] * 4
    # Clockwise from 12 o'clock: N→E, E→S, S→W, W→N.
    assert _donut_slice_index(5, -10, sweeps) == 0
    assert _donut_slice_index(10, 5, sweeps) == 1
    assert _donut_slice_index(-5, 10, sweeps) == 2
    assert _donut_slice_index(-10, -5, sweeps) == 3


def test_donut_arcs_use_butt_caps() -> None:
    paint = _arc_stroke("#2DD4BF", 14)
    assert paint.stroke_cap == ft.StrokeCap.BUTT
    line = _stroke("#2DD4BF", 2.8)
    assert line.stroke_cap == ft.StrokeCap.ROUND


def test_normalize_donut_sweeps_fills_ring_with_tiny_shares() -> None:
    sweeps = _normalize_donut_sweeps([1_000_000, 25_000, 25_000])
    assert len(sweeps) == 3
    assert abs(sum(sweeps) - 2 * math.pi) < 1e-9
    assert all(s >= 0.05 for s in sweeps)


def test_normalize_donut_sweeps_empty() -> None:
    assert _normalize_donut_sweeps([]) == []
    assert _normalize_donut_sweeps([0, 0]) == []
