"""Mobile-friendly keyboard types and Enter / Done focus chaining."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Optional

import flet as ft

from lib.presentation.utils import run_async, safe_update

_Kind = str  # "text" | "name" | "number" | "phone" | "email" | "url" | "password" | "search"


def keyboard_for(kind: _Kind) -> ft.KeyboardType:
    """Map a logical field kind to a soft-keyboard type."""
    mapping = {
        "text": ft.KeyboardType.TEXT,
        "name": ft.KeyboardType.NAME,
        "number": ft.KeyboardType.NUMBER,
        "phone": ft.KeyboardType.PHONE,
        "email": ft.KeyboardType.EMAIL,
        "url": ft.KeyboardType.URL,
        "password": ft.KeyboardType.VISIBLE_PASSWORD,
        "search": ft.KeyboardType.WEB_SEARCH,
    }
    return mapping.get(kind, ft.KeyboardType.TEXT)


def configure_field(
    field: ft.TextField,
    kind: _Kind = "text",
    *,
    dismiss_on_outside: bool = True,
) -> ft.TextField:
    """Set keyboard type and sensible mobile input flags for ``kind``."""
    field.keyboard_type = keyboard_for(kind)
    if kind in {"number", "phone", "password"}:
        field.autocorrect = False
        field.enable_suggestions = False
    if kind == "number":
        # Keep single-line so Enter triggers on_submit / Done on iOS.
        field.multiline = False
        field.min_lines = 1
        field.max_lines = 1
    if dismiss_on_outside and field.on_tap_outside is None:
        field.on_tap_outside = lambda _e, f=field: _schedule_dismiss(f)
    return field


def configure_pin_field(field: ft.TextField) -> ft.TextField:
    """Number pad + digits-only filter for PIN entry (4–8 digits)."""
    configure_field(field, "number")
    field.max_length = 8
    field.password = True
    field.can_reveal_password = False
    field.keyboard_type = ft.KeyboardType.NUMBER
    filt_cls = getattr(ft, "InputFilter", None)
    if filt_cls is not None:
        try:
            field.input_filter = filt_cls(
                regex_string=r"[0-9]",
                allow=True,
                replacement_string="",
            )
        except Exception:  # noqa: BLE001
            pass
    return field


def _schedule_dismiss(field: ft.TextField) -> None:
    page = getattr(field, "page", None)
    if page is not None:
        run_async(page, dismiss_soft_keyboard, field)
        return
    _dismiss_sync(field)


def _dismiss_sync(field: ft.TextField) -> None:
    """Hide the soft keyboard by briefly making the field read-only.

    Flet has no public ``blur()``; Flutter still collapses IME when the
    field becomes read-only / loses the editable caret.
    """
    try:
        was_ro = bool(field.read_only)
        was_cursor = field.show_cursor
        field.read_only = True
        field.show_cursor = False
        safe_update(field)
        field.read_only = was_ro
        field.show_cursor = True if was_cursor is None else was_cursor
        safe_update(field)
    except Exception:  # noqa: BLE001
        pass


async def dismiss_soft_keyboard(field: ft.TextField | None = None) -> None:
    """Dismiss the on-screen keyboard for ``field`` (or no-op)."""
    if field is None:
        return
    _dismiss_sync(field)


async def focus_field(field: ft.TextField) -> None:
    """Move focus to ``field`` so the matching keyboard type appears."""
    try:
        await field.focus()
    except Exception:  # noqa: BLE001
        pass


def wire_field_chain(
    page: ft.Page | None,
    fields: Sequence[ft.TextField | None],
    *,
    on_done: Optional[Callable[[], Any]] = None,
) -> None:
    """On Enter: focus the next field; on the last field: hide keyboard.

    Existing ``on_submit`` handlers are chained (called first).
    ``page`` may be ``None`` at wire time — resolved from the field when Enter fires.
    """
    chain = [f for f in fields if f is not None]
    if not chain:
        return

    for index, field in enumerate(chain):
        nxt = chain[index + 1] if index + 1 < len(chain) else None
        previous = field.on_submit

        def _make(
            current: ft.TextField,
            next_field: ft.TextField | None,
            prev: Any,
        ) -> Callable[[ft.ControlEvent], None]:
            def _on_submit(e: ft.ControlEvent) -> None:
                if prev is not None:
                    try:
                        prev(e)
                    except Exception:  # noqa: BLE001
                        pass

                async def _advance() -> None:
                    if next_field is not None:
                        await focus_field(next_field)
                        return
                    await dismiss_soft_keyboard(current)
                    if on_done is not None:
                        result = on_done()
                        if hasattr(result, "__await__"):
                            await result  # type: ignore[misc]

                host = page or getattr(current, "page", None) or getattr(e, "page", None)
                if host is not None:
                    run_async(host, _advance)
                else:
                    _dismiss_sync(current)

            return _on_submit

        field.on_submit = _make(field, nxt, previous)


def text_field(kind: _Kind = "text", **kwargs: Any) -> ft.TextField:
    """Build a TextField with the right soft keyboard for ``kind``."""
    field = ft.TextField(**kwargs)
    return configure_field(field, kind)
