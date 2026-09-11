"""Fullscreen form overlay (covers nav / content like a native screen)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Optional

import flet as ft

from lib.presentation.skins import get_active_skin
from lib.presentation.styles import (
    card_surface,
    form_header_bar,
    form_save_button,
    polish_form_control,
)
from lib.presentation.theme import is_dark_mode
from lib.presentation.responsive import (
    clamp_content_width,
    form_shell_inset,
    is_narrow,
    tap_button_style,
    wrap_safe_area,
)
from lib.presentation.ui_motion import (
    DUR_MED,
    apply_overlay_enter,
    bump_overlay_gen,
    is_web_page,
    motion_ms,
    overlay_enter_style,
    overlay_generation,
    overlay_skips_fade,
    prefers_reduced_motion,
)
from lib.presentation.utils import run_async, safe_update, tr

CloseFn = Callable[[], None]
SaveFn = Callable[[], Awaitable[None]]


def _hide_overlay_now(item: ft.Control) -> None:
    try:
        item.visible = False
        item.content = None
        item.ignore_interactions = True
        item.opacity = 1
        item.offset = ft.Offset(0, 0)
    except Exception:  # noqa: BLE001
        pass
    try:
        safe_update(item)
    except Exception:  # noqa: BLE001
        pass


def _disarm_overlay(item: ft.Control) -> None:
    """Stop hit-testing immediately so a fading sheet cannot steal taps."""
    try:
        item.ignore_interactions = True
    except Exception:  # noqa: BLE001
        pass


async def _fade_out_overlay(item: ft.Control, gen: int) -> None:
    _disarm_overlay(item)
    try:
        item.opacity = 0
        item.offset = ft.Offset(0, 0.02)
        safe_update(item)
    except Exception:  # noqa: BLE001
        _hide_overlay_now(item)
        return
    await asyncio.sleep(motion_ms(DUR_MED) / 1000 or 0.01)
    if overlay_generation(item) != gen:
        return
    _hide_overlay_now(item)


def dismiss_fullscreen(page: ft.Page, *, key: str) -> None:
    """Hide the overlay tagged with ``key`` and drop its widget tree.

    Keep the slot in ``page.overlay`` and update *that control only*.
    Removing it without ``page.update()`` leaves a live Flutter overlay;
    calling ``page.update()`` snaps ListViews to the top. Reuse + empty
    content avoids both.
    """
    for item in list(page.overlay):
        if getattr(item, "data", None) != key:
            continue
        gen = bump_overlay_gen(item)
        _disarm_overlay(item)
        if (
            prefers_reduced_motion(page)
            or is_web_page(page)
            or not getattr(item, "visible", True)
        ):
            _hide_overlay_now(item)
            continue
        if not _safe_run_async(page, _fade_out_overlay, item, gen):
            _hide_overlay_now(item)


def _toast_overlay_index(page: ft.Page) -> int | None:
    """Index of the save/error toast so forms insert *under* it."""
    from lib.presentation.ui_feedback import TOAST_OVERLAY_TAG

    for i, item in enumerate(list(page.overlay or [])):
        if getattr(item, "data", None) == TOAST_OVERLAY_TAG:
            return i
    return None


def _append_overlay(page: ft.Page, overlay: ft.Control) -> None:
    """Keep the toast last so it paints above fullscreen sheets."""
    idx = _toast_overlay_index(page)
    try:
        if idx is None:
            page.overlay.append(overlay)
        else:
            page.overlay.insert(idx, overlay)
    except Exception:  # noqa: BLE001
        page.overlay.append(overlay)


def _find_overlay(page: ft.Page, key: str) -> ft.Control | None:
    for item in list(page.overlay):
        if getattr(item, "data", None) == key:
            return item
    return None


def _safe_run_async(page: ft.Page, handler, *args) -> bool:
    """Schedule async work; False when there is no event loop (unit tests)."""
    if hasattr(page, "run_task"):
        try:
            page.run_task(handler, *args)
            return True
        except Exception:  # noqa: BLE001
            return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    try:
        loop.create_task(handler(*args))
        return True
    except Exception:  # noqa: BLE001
        return False


def _reveal_overlay(page: ft.Page, overlay: ft.Control) -> None:
    """Ease opacity/offset to the resting pose after the first paint."""
    # Native mobile fades from opacity=0; keep hit-testing off until visible.
    # Web and Windows desktop stay opaque from the first frame.
    instant = prefers_reduced_motion(page) or overlay_skips_fade(page)
    if instant:
        try:
            overlay.opacity = 1
            overlay.offset = ft.Offset(0, 0)
            overlay.ignore_interactions = False
            safe_update(overlay)
        except Exception:  # noqa: BLE001
            pass
        return

    async def _play() -> None:
        await asyncio.sleep(0.016)
        try:
            overlay.opacity = 1
            overlay.offset = ft.Offset(0, 0)
            overlay.ignore_interactions = False
            safe_update(overlay)
        except Exception:  # noqa: BLE001
            pass

    if not _safe_run_async(page, _play):
        try:
            overlay.opacity = 1
            overlay.offset = ft.Offset(0, 0)
            overlay.ignore_interactions = False
        except Exception:  # noqa: BLE001
            pass


def push_overlay(page: ft.Page, overlay: ft.Control) -> None:
    """Show ``overlay`` (must set ``data`` key), reusing an existing slot."""
    apply_overlay_enter(overlay, page)
    key = getattr(overlay, "data", None)
    if not key:
        _append_overlay(page, overlay)
        safe_update(page)
        _reveal_overlay(page, overlay)
        return
    overlay.visible = True
    slot = _find_overlay(page, str(key))
    if slot is None:
        _append_overlay(page, overlay)
        bump_overlay_gen(overlay)
        safe_update(page)
        _reveal_overlay(page, overlay)
        return
    bump_overlay_gen(slot)
    slot.content = overlay.content
    slot.visible = True
    for attr in (
        "left",
        "top",
        "right",
        "bottom",
        "width",
        "height",
        "expand",
        "bgcolor",
        "alignment",
        "opacity",
        "offset",
        "animate_opacity",
        "animate_offset",
        "ignore_interactions",
    ):
        if hasattr(overlay, attr):
            try:
                setattr(slot, attr, getattr(overlay, attr))
            except Exception:  # noqa: BLE001
                pass
    safe_update(slot)
    _reveal_overlay(page, slot)


def _polish_tree(controls: Sequence[ft.Control]) -> list[ft.Control]:
    out: list[ft.Control] = []
    for item in controls:
        polish_form_control(item)
        out.append(item)
    return out


def build_form_shell(
    page: ft.Page,
    *,
    title: str,
    lang: str,
    body: Sequence[ft.Control],
    leading: Optional[ft.Control] = None,
    actions: Optional[Sequence[ft.Control]] = None,
    wrap_body: bool = True,
    footer: Optional[ft.Control] = None,
) -> ft.Control:
    """Shared chrome: gradient backdrop, glass header, padded scroll body."""
    skin = get_active_skin()
    dark = is_dark_mode(page)
    inset = form_shell_inset(page)
    form_w = clamp_content_width(page, margin=inset, max_width=560)
    body_controls = _polish_tree(body)
    if wrap_body:
        panel = card_surface(
            ft.Column(spacing=14, tight=True, controls=body_controls),
            padding=18,
        )
        scroll_kids: list[ft.Control] = [
            ft.Container(
                alignment=ft.Alignment.TOP_CENTER,
                content=ft.Container(
                    width=form_w,
                    content=panel,
                ),
            ),
            ft.Container(height=40),
        ]
    else:
        scroll_kids = [
            ft.Container(
                alignment=ft.Alignment.TOP_CENTER,
                content=ft.Container(
                    width=form_w,
                    content=ft.Column(spacing=14, tight=True, controls=body_controls),
                ),
            ),
            ft.Container(height=40),
        ]

    close_leading = leading or ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color=ft.Colors.ON_SURFACE,
        tooltip=tr("action.cancel", lang),
        style=tap_button_style(horizontal=10, vertical=10),
    )

    return wrap_safe_area(
        ft.Container(
            expand=True,
            gradient=skin.page_gradient(dark=dark),
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    form_header_bar(
                        title,
                        leading=close_leading,
                        actions=list(actions or []),
                        page=page,
                    ),
                    ft.Container(
                        expand=True,
                        padding=ft.Padding.symmetric(horizontal=inset, vertical=12),
                        content=ft.Column(
                            expand=True,
                            spacing=0,
                            scroll=ft.ScrollMode.AUTO,
                            controls=scroll_kids,
                        ),
                    ),
                    *([footer] if footer is not None else []),
                ],
            ),
        ),
    )


def open_fullscreen_form(
    page: ft.Page,
    *,
    title: str,
    lang: str,
    body: Sequence[ft.Control],
    on_save: SaveFn | None = None,
    overlay_key: str = "fullscreen_form",
    save_icon: ft.IconData = ft.Icons.CHECK,
    save_label: str | None = None,
    show_save: bool = True,
    wrap_body: bool = True,
    save_compact: bool = False,
    footer: Optional[ft.Control] = None,
    on_close: Optional[Callable[[], None]] = None,
) -> CloseFn:
    """Show a full-screen form with close + optional save in the header.

    Returns a ``close`` callback the caller can invoke after a successful save.
    ``save_compact`` keeps a tappable icon in the header on narrow phones.
    ``footer`` stays visible below the scroll body (primary CTA).
    ``on_close`` runs after the overlay is dismissed (X, apply, or caller).
    """
    dismiss_fullscreen(page, key=overlay_key)
    try:
        from lib.presentation.haptics import haptic

        haptic("light")
    except Exception:  # noqa: BLE001
        pass

    busy = {"on": False}

    def _close(_e: Any = None) -> None:
        dismiss_fullscreen(page, key=overlay_key)
        if on_close is not None:
            try:
                on_close()
            except Exception:  # noqa: BLE001
                pass

    async def _save_click(_e: ft.ControlEvent | None = None) -> None:
        if on_save is None or busy["on"]:
            return
        busy["on"] = True
        try:
            await on_save()
        finally:
            busy["on"] = False

    compact = save_compact or is_narrow(page)
    actions: list[ft.Control] = []
    if show_save and on_save is not None:
        if compact:
            actions.append(
                ft.IconButton(
                    icon=save_icon,
                    icon_color=ft.Colors.PRIMARY,
                    tooltip=save_label or tr("action.save", lang),
                    on_click=lambda e: run_async(page, _save_click, e),
                    style=tap_button_style(horizontal=10, vertical=10),
                )
            )
        else:
            actions.append(
                form_save_button(
                    save_label or tr("action.save", lang),
                    icon=save_icon,
                    on_click=lambda e: run_async(page, _save_click, e),
                )
            )

    close_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color=ft.Colors.ON_SURFACE,
        tooltip=tr("action.cancel", lang),
        on_click=lambda _e: _close(),
        style=tap_button_style(horizontal=10, vertical=10),
    )

    overlay = ft.Container(
        left=0,
        top=0,
        right=0,
        bottom=0,
        width=getattr(page, "width", None) or None,
        height=getattr(page, "height", None) or None,
        expand=True,
        bgcolor=ft.Colors.SURFACE,
        alignment=ft.Alignment.TOP_CENTER,
        data=overlay_key,
        **overlay_enter_style(page),
        content=build_form_shell(
            page,
            title=title,
            lang=lang,
            body=body,
            leading=close_btn,
            actions=actions,
            wrap_body=wrap_body,
            footer=footer,
        ),
    )
    push_overlay(page, overlay)
    return _close
