"""Chart hit-testing helpers."""

from __future__ import annotations

import math

from lib.presentation.widgets.charts import _donut_slice_index, _nearest_period_index


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
