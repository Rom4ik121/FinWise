"""Unit tests for responsive sizing helpers."""

from __future__ import annotations

from lib.presentation.responsive import (
    MIN_TAP,
    calendar_cell_size,
    calendar_day_width,
    clamp_content_width,
    compact_chart_size,
    form_control_width,
    is_compact,
    is_wide,
    scale_font,
    swipe_action_strip_width,
    swipe_reveal_offset,
)


class _FakePage:
    def __init__(self, width: float, height: float = 780) -> None:
        self.width = width
        self.height = height
        self.window = type("W", (), {"width": width, "height": height})()


def test_scale_font_clamped_on_se_and_pro_max() -> None:
    se = scale_font(16, _FakePage(320))  # type: ignore[arg-type]
    wide = scale_font(16, _FakePage(430))  # type: ignore[arg-type]
    assert se <= 16
    assert wide >= 16
    assert se >= 10
    assert wide <= 20


def test_compact_and_wide_breakpoints() -> None:
    assert is_compact(_FakePage(360))  # type: ignore[arg-type]
    assert not is_compact(_FakePage(480))  # type: ignore[arg-type]
    assert is_wide(_FakePage(800))  # type: ignore[arg-type]
    assert not is_wide(_FakePage(600))  # type: ignore[arg-type]


def test_form_and_calendar_fit_narrow() -> None:
    se = _FakePage(320)  # type: ignore[arg-type]
    assert form_control_width(se) is None  # type: ignore[arg-type]
    assert clamp_content_width(se, margin=24, max_width=400) <= 320  # type: ignore[arg-type]
    assert calendar_cell_size(se) >= MIN_TAP  # type: ignore[arg-type]
    day_w = calendar_day_width(se)  # type: ignore[arg-type]
    assert 7 * day_w + 6 * 4 <= 320 - 40
    w, h = compact_chart_size(se)  # type: ignore[arg-type]
    assert w <= 320
    assert 100 <= h <= 180


def test_breakpoints_and_grid() -> None:
    from lib.presentation.responsive import (
        BP_LG,
        BP_XS,
        breakpoint,
        grid_columns,
        scale_size,
        tx_tile_metrics,
    )

    assert breakpoint(_FakePage(320)) == BP_XS  # type: ignore[arg-type]
    assert breakpoint(_FakePage(800)) == BP_LG  # type: ignore[arg-type]
    assert grid_columns(_FakePage(360)) == 1  # type: ignore[arg-type]
    assert grid_columns(_FakePage(800)) >= 2  # type: ignore[arg-type]
    assert grid_columns(_FakePage(1200)) == 3  # type: ignore[arg-type]
    se_pad = scale_size(16, _FakePage(320))  # type: ignore[arg-type]
    desk_pad = scale_size(16, _FakePage(1100))  # type: ignore[arg-type]
    assert se_pad <= 16 <= desk_pad
    metrics = tx_tile_metrics(_FakePage(320))  # type: ignore[arg-type]
    assert metrics["height"] >= 52
    assert metrics["amount_width"] >= 72
    from lib.presentation.responsive import entity_card_metrics

    entity = entity_card_metrics(_FakePage(320))  # type: ignore[arg-type]
    assert entity["icon"] >= 30
    assert entity["title"] >= 12
    desk = entity_card_metrics(_FakePage(1100))  # type: ignore[arg-type]
    assert desk["padding"] >= entity["padding"]


def test_block_metrics_shrink_in_kpi_row() -> None:
    from lib.presentation.responsive import (
        block_inner_width,
        hero_block_metrics,
        kpi_card_metrics,
        ring_label_font,
    )
    from lib.presentation.widgets.charts import chart_layout

    se = _FakePage(320)  # type: ignore[arg-type]
    inner_one = block_inner_width(se, columns=1)  # type: ignore[arg-type]
    inner_two = block_inner_width(se, columns=2)  # type: ignore[arg-type]
    inner_three = block_inner_width(se, columns=3)  # type: ignore[arg-type]
    assert inner_three < inner_two < inner_one
    assert inner_one <= 320
    kpi2 = kpi_card_metrics(se, columns=2)  # type: ignore[arg-type]
    kpi3 = kpi_card_metrics(se, columns=3)  # type: ignore[arg-type]
    assert kpi3["value"] <= kpi2["value"]
    assert kpi3["title"] >= 9
    assert kpi3["value"] >= 10
    hero = hero_block_metrics(se)  # type: ignore[arg-type]
    assert 56 <= hero["ring"] <= 88
    assert hero["amount"] >= 16
    assert ring_label_font(48, "88%") < ring_label_font(88, "88%")
    assert ring_label_font(52, "88%") <= 14
    from lib.presentation.responsive import donut_center_metrics

    hole = donut_center_metrics(168)
    assert hole["percent"] <= 15
    assert hole["percent"] < ring_label_font(168, "88%")
    assert hole["amount"] <= hole["percent"]
    assert hole["caption"] <= hole["amount"]
    chart_w, chart_h = chart_layout(se)  # type: ignore[arg-type]
    assert chart_w < 320
    assert chart_w <= inner_one + 8
    assert 140 <= chart_h <= 200


def test_card_grid_one_and_many_columns() -> None:
    import flet as ft

    from lib.presentation.components.layout.grid import card_grid

    a, b, c = ft.Text("a"), ft.Text("b"), ft.Text("c")
    single = card_grid([a, b], _FakePage(360))  # type: ignore[arg-type]
    assert single == [a, b]
    packed = card_grid([a, b, c], _FakePage(900), min_card=280)  # type: ignore[arg-type]
    assert packed
    assert all(isinstance(row, ft.Row) for row in packed)


def test_swipe_strip_shrinks_on_narrow_phones() -> None:
    narrow = swipe_action_strip_width(_FakePage(320), buttons=2)  # type: ignore[arg-type]
    wide = swipe_action_strip_width(_FakePage(430), buttons=2)  # type: ignore[arg-type]
    assert narrow <= wide
    assert narrow >= 96
    frac = swipe_reveal_offset(_FakePage(320), strip_width=narrow, buttons=2)  # type: ignore[arg-type]
    assert 0.32 <= frac <= 0.92
    # Revealed width roughly covers the strip.
    assert frac * 320 >= narrow * 0.85
