"""Unit tests for responsive sizing helpers."""

from __future__ import annotations

from lib.presentation.responsive import (
    MIN_TAP,
    calendar_cell_size,
    calendar_day_width,
    clamp_content_width,
    compact_chart_size,
    content_inset,
    form_control_width,
    form_shell_inset,
    is_compact,
    is_wide,
    layout_width,
    list_nav_padding,
    nav_chrome_metrics,
    nav_overlay_height,
    note_viewport_from_event,
    note_viewport_size,
    page_height,
    page_width,
    scale_font,
    shell_max_width,
    should_rebuild_layout,
    swipe_action_strip_width,
    swipe_reveal_offset,
    uses_column_nav_shell,
)


class _FakePage:
    def __init__(self, width: float, height: float = 780) -> None:
        self.width = width
        self.height = height
        self.window = type("W", (), {"width": width, "height": height})()


def test_page_width_prefers_smaller_window_when_page_lags() -> None:
    """When the cache is empty, window.width beats a stale page.width."""
    page = _FakePage(1266, height=800)
    page.window.width = 300
    page.window.height = 640
    assert page_width(page) == 300  # type: ignore[arg-type]
    assert page_height(page) == 640  # type: ignore[arg-type]
    assert content_inset(page) * 2 + min(240, 300) <= 300  # type: ignore[arg-type]
    assert uses_column_nav_shell(page) is True  # type: ignore[arg-type]
    assert is_compact(page) is True  # type: ignore[arg-type]


def test_page_width_prefers_viewport_cache_when_page_and_window_lag() -> None:
    """Flet Windows: both page.width and window.width can stay ~1266.

    The resize event carries the live ~300px; note_viewport_size must win.
    """
    page = _FakePage(1266, height=800)
    page.window.width = 1266
    page.window.height = 800
    assert page_width(page) == 1266  # type: ignore[arg-type]
    note_viewport_size(page, width=300, height=640)
    assert page_width(page) == 300  # type: ignore[arg-type]
    assert page_height(page) == 640  # type: ignore[arg-type]
    assert getattr(page, "_fw_viewport_w") == 300
    assert content_inset(page) * 2 + min(240, 300) <= 300  # type: ignore[arg-type]
    assert uses_column_nav_shell(page) is True  # type: ignore[arg-type]


def test_note_viewport_from_event_reads_resize_payload() -> None:
    page = _FakePage(1266, height=800)
    page.window.width = 1266
    event = type("Resize", (), {"width": 312, "height": 640})()
    note_viewport_from_event(page, event)  # type: ignore[arg-type]
    assert page_width(page) == 312  # type: ignore[arg-type]
    assert page_height(page) == 640  # type: ignore[arg-type]


def test_note_viewport_size_ignores_non_positive() -> None:
    page = _FakePage(1266)
    note_viewport_size(page, width=320, height=600)
    note_viewport_size(page, width=0, height=None)
    assert page_width(page) == 320  # type: ignore[arg-type]
    assert page_height(page) == 600  # type: ignore[arg-type]


def test_scale_font_clamped_on_se_and_pro_max() -> None:
    se = scale_font(16, _FakePage(320))  # type: ignore[arg-type]
    wide = scale_font(16, _FakePage(430))  # type: ignore[arg-type]
    assert se <= 16
    assert wide >= 16
    assert se >= 10
    assert wide <= 20


def test_compact_and_wide_breakpoints() -> None:
    assert is_compact(_FakePage(360))  # type: ignore[arg-type]
    assert is_compact(_FakePage(420))  # type: ignore[arg-type]
    assert not is_compact(_FakePage(421))  # type: ignore[arg-type]
    assert not is_compact(_FakePage(480))  # type: ignore[arg-type]
    assert is_wide(_FakePage(800))  # type: ignore[arg-type]
    assert not is_wide(_FakePage(600))  # type: ignore[arg-type]


def test_form_and_calendar_fit_narrow() -> None:
    se = _FakePage(320)  # type: ignore[arg-type]
    assert form_control_width(se) is None  # type: ignore[arg-type]
    assert clamp_content_width(se, margin=24, max_width=400) <= 320  # type: ignore[arg-type]
    # Floor of 280 must never exceed the remaining viewport.
    locked = clamp_content_width(se, margin=56, max_width=280)  # type: ignore[arg-type]
    assert locked <= 320 - 112
    assert calendar_cell_size(se) >= MIN_TAP  # type: ignore[arg-type]
    day_w = calendar_day_width(se)  # type: ignore[arg-type]
    assert 7 * day_w + 6 * 4 <= 320 - 40
    w, h = compact_chart_size(se)  # type: ignore[arg-type]
    assert w <= 320
    assert 100 <= h <= 180
    assert form_shell_inset(se) <= 12  # type: ignore[arg-type]


def test_shell_centers_on_desktop_without_skinny_island() -> None:
    desk = _FakePage(1400)  # type: ignore[arg-type]
    phone = _FakePage(390)  # type: ignore[arg-type]
    tablet = _FakePage(800)  # type: ignore[arg-type]
    assert shell_max_width(phone) is None  # type: ignore[arg-type]
    assert shell_max_width(desk) == 960  # type: ignore[arg-type]
    body = layout_width(desk)  # type: ignore[arg-type]
    assert 840 <= body <= 960
    # Gutters eat the leftover — content is centered, not edge-to-edge.
    assert content_inset(desk) >= 200  # type: ignore[arg-type]
    assert abs(1400 - body - content_inset(desk) * 2) < 2  # type: ignore[arg-type]
    # Common phone fills the gutters (no 400px island).
    assert layout_width(phone) >= 360  # type: ignore[arg-type]
    # Large phone / small tablet: two card columns, not a crushed single strip.
    assert layout_width(tablet) >= 700  # type: ignore[arg-type]
    nav = nav_chrome_metrics(desk)  # type: ignore[arg-type]
    # Grouped tab bar, not four icons stretched 1400px apart.
    assert nav["margin_h"] * 2 + 560 <= 1400
    assert nav["margin_h"] >= 100
    se_nav = nav_chrome_metrics(_FakePage(320))  # type: ignore[arg-type]
    assert se_nav["margin_h"] <= 8
    assert se_nav["label"] <= 11
    pad = list_nav_padding()
    assert pad.bottom == 104


def test_phone_widths_keep_nav_and_home_in_viewport() -> None:
    """320–390 must use compact nav so four tabs stay on-screen (QA ~375)."""
    from lib.presentation.responsive import BP_XS, breakpoint

    for width in (320, 360, 375, 390):
        page = _FakePage(width, height=667)  # type: ignore[arg-type]
        assert breakpoint(page) == BP_XS  # type: ignore[arg-type]
        nav = nav_chrome_metrics(page)  # type: ignore[arg-type]
        bar = width - 2 * nav["margin_h"]
        per_tab = nav["pill_w"] + 2 * nav["item_pad_h"]
        assert 4 * per_tab <= bar
        assert nav["label"] <= 10
        overlay = nav_overlay_height(page)  # type: ignore[arg-type]
        bar_plus_margin = nav["bar_h"] + nav["margin_top"] + nav["margin_bottom"]
        assert overlay >= bar_plus_margin
        assert overlay < 96
        assert overlay < 667 * 0.18
        chart_w, _chart_h = compact_chart_size(page)  # type: ignore[arg-type]
        assert 0 < chart_w <= layout_width(page) <= width  # type: ignore[arg-type]
        assert content_inset(page) <= 10  # type: ignore[arg-type]


def test_nav_overlay_capped_on_short_narrow_window() -> None:
    """Short+narrow must not let the tab overlay cover the body."""
    page = _FakePage(375, height=320)  # type: ignore[arg-type]
    overlay = nav_overlay_height(page)  # type: ignore[arg-type]
    assert overlay <= int(320 * 0.18) or overlay <= 56
    assert overlay < 320 * 0.5
    assert overlay >= 56


def test_xs_resize_from_fallback_rebuilds_layout() -> None:
    """390 (page_width fallback) → 375 must remount, not keep a 390 chart."""
    from lib.presentation.responsive import BP_XS

    assert should_rebuild_layout(
        old_bp=BP_XS, new_bp=BP_XS, old_width=390, new_width=375
    )
    assert should_rebuild_layout(
        old_bp=BP_XS, new_bp=BP_XS, old_width=360, new_width=320
    )
    assert not should_rebuild_layout(
        old_bp=BP_XS, new_bp=BP_XS, old_width=375, new_width=375
    )
    assert not should_rebuild_layout(
        old_bp="lg", new_bp="lg", old_width=1100, new_width=1140
    )


def test_breakpoints_and_grid() -> None:
    from lib.presentation.responsive import (
        BP_LG,
        BP_XS,
        breakpoint,
        grid_columns,
        layout_width,
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
    row = (
        metrics["icon"]
        + metrics["amount_width"]
        + MIN_TAP
        + 20
        + 24
    )
    assert row <= layout_width(_FakePage(320))  # type: ignore[arg-type]
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


def test_wrap_safe_area_skips_on_desktop_windows() -> None:
    import flet as ft

    from lib.presentation.responsive import wrap_safe_area

    page = _FakePage(1280)
    page.platform = "windows"
    child = ft.Text("ok")
    wrapped = wrap_safe_area(child, page=page)  # type: ignore[arg-type]
    assert not isinstance(wrapped, ft.SafeArea)
    assert wrapped.content is child
    assert wrapped.expand is True


def test_wrap_safe_area_uses_os_insets_on_ios() -> None:
    import flet as ft

    from lib.presentation.responsive import (
        SAFE_MIN_BOTTOM,
        SAFE_MIN_TOP,
        safe_area_minimum,
        wrap_safe_area,
    )

    assert 0 < SAFE_MIN_TOP < 20
    assert 0 < SAFE_MIN_BOTTOM < 20
    page = _FakePage(375)
    page.platform = "ios"
    child = ft.Text("ok")
    shell = wrap_safe_area(child, page=page)  # type: ignore[arg-type]
    assert isinstance(shell, ft.SafeArea)
    assert shell.avoid_intrusions_top is True
    assert shell.avoid_intrusions_bottom is True
    assert shell.avoid_intrusions_left is True
    assert shell.avoid_intrusions_right is True
    assert shell.maintain_bottom_view_padding is True
    assert shell.minimum_padding == safe_area_minimum()
    toast = wrap_safe_area(child, page=page, expand=False, bottom=False)  # type: ignore[arg-type]
    assert toast.avoid_intrusions_bottom is False
    assert toast.maintain_bottom_view_padding is False
    assert toast.avoid_intrusions_top is True
    nested = wrap_safe_area(child, page=page, minimum=0)  # type: ignore[arg-type]
    assert nested.minimum_padding == 0
    assert nested.avoid_intrusions_top is True


def test_insets_never_zero_body_at_320() -> None:
    from lib.presentation.responsive import page_frame_inset, shell_side_padding

    phone = _FakePage(320)
    desk = _FakePage(1400)
    assert content_inset(phone) * 2 + 240 <= 320  # type: ignore[arg-type]
    assert page_frame_inset(phone) <= 8  # type: ignore[arg-type]
    assert shell_side_padding(phone) == 0  # type: ignore[arg-type]
    assert page_frame_inset(desk) <= 12  # type: ignore[arg-type]
    assert shell_side_padding(desk) >= 180  # type: ignore[arg-type]
    assert content_inset(desk) >= 200  # type: ignore[arg-type]


def test_content_inset_never_exceeds_half_remaining() -> None:
    """Gutters cannot exceed (width - min(240, width)) / 2."""
    for width in (200, 240, 300, 312, 320, 1266):
        page = _FakePage(1266)
        page.window.width = 1266
        note_viewport_size(page, width=width, height=640)
        inset = content_inset(page)  # type: ignore[arg-type]
        max_inset = (width - min(240, width)) / 2
        assert inset <= max_inset
        assert 2 * inset + min(240, width) <= width + 0.01


def test_page_frame_uses_small_gutters_and_clips_body() -> None:
    import flet as ft

    from lib.presentation.components.layout.page_shell import page_frame

    kids = page_frame(
        title="Home",
        body=ft.Text("body"),
        page=_FakePage(1400),  # type: ignore[arg-type]
    )
    host = kids[-1]
    pad = host.padding
    left = getattr(pad, "left", pad)
    right = getattr(pad, "right", pad)
    assert float(left) <= 12
    assert float(right) <= 12
    assert host.clip_behavior == ft.ClipBehavior.HARD_EDGE


def test_nav_chrome_layer_is_translucent_on_classic() -> None:
    import flet as ft

    from lib.presentation.styles import nav_chrome_layer

    native = nav_chrome_layer(_FakePage(375))  # type: ignore[arg-type]
    assert native["bgcolor"] != ft.Colors.SURFACE_CONTAINER
    assert "0.58" in str(native["bgcolor"])
    assert native["blur"] is not None
    web = _FakePage(375)
    web.web = True
    compact_web = nav_chrome_layer(web)  # type: ignore[arg-type]
    assert compact_web["blur"] is None
    wide = nav_chrome_layer(_FakePage(1280))  # type: ignore[arg-type]
    assert wide["blur"] is not None
