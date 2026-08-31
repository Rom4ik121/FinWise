"""Count-up animation for money Text widgets after a manual refresh."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Optional

import flet as ft

from lib.presentation.utils import format_money, format_money_compact, format_money_parts, safe_update

_META_KEY = "count_up"
_STEPS = 18
_DURATION_S = 0.55


def mark_money_text(
    text: ft.Text,
    amount: Decimal | float | int | str,
    *,
    currency: str,
    compact: bool = False,
    signed: bool = False,
    figure_only: bool = False,
) -> ft.Text:
    """Tag a ``Text`` so :func:`play_count_ups` can animate it from zero."""
    value = Decimal(str(amount))
    meta = {
        _META_KEY: True,
        "amount": str(value),
        "currency": currency,
        "compact": compact,
        "signed": signed,
        "figure_only": figure_only,
    }
    existing = getattr(text, "data", None)
    if isinstance(existing, dict):
        existing.update(meta)
        text.data = existing
    else:
        text.data = meta
    return text


def _format(meta: dict[str, Any], amount: Decimal) -> str:
    currency = str(meta.get("currency") or "RUB")
    signed = bool(meta.get("signed"))
    if meta.get("figure_only"):
        figure, _code = format_money_parts(amount, currency, signed=signed)
        return figure
    if meta.get("compact"):
        return format_money_compact(amount, currency, signed=signed)
    return format_money(amount, currency, signed=signed)


def _collect(control: Any, out: list[ft.Text]) -> None:
    if control is None:
        return
    if isinstance(control, ft.Text):
        data = getattr(control, "data", None)
        if isinstance(data, dict) and data.get(_META_KEY):
            out.append(control)
    for child in getattr(control, "controls", None) or []:
        _collect(child, out)
    _collect(getattr(control, "content", None), out)


def _ease_out(t: float) -> float:
    u = 1.0 - t
    return 1.0 - u * u * u


async def play_count_ups(
    root: ft.Control,
    page: ft.Page,
    *,
    duration_s: float = _DURATION_S,
    steps: int = _STEPS,
) -> None:
    """Animate all marked money texts under ``root`` from 0 → target."""
    targets: list[ft.Text] = []
    _collect(root, targets)
    if not targets:
        return

    specs: list[tuple[ft.Text, Decimal, dict[str, Any]]] = []
    for text in targets:
        meta = text.data if isinstance(text.data, dict) else {}
        try:
            amount = Decimal(str(meta.get("amount") or "0"))
        except Exception:  # noqa: BLE001
            continue
        specs.append((text, amount, meta))
        text.value = _format(meta, Decimal("0"))

    try:
        safe_update(page)
    except Exception:  # noqa: BLE001
        pass

    if steps < 2:
        steps = 2
    delay = max(duration_s / steps, 0.012)
    for i in range(1, steps + 1):
        progress = _ease_out(i / steps)
        for text, amount, meta in specs:
            current = (amount * Decimal(str(progress))).quantize(Decimal("0.01"))
            if i == steps:
                current = amount
            text.value = _format(meta, current)
        try:
            safe_update(page)
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(delay)


def refresh_handler(page: ft.Page, reload_fn) -> Any:
    """Build an ``on_click`` that reloads with count-up animation."""

    async def _run(_e: Optional[ft.ControlEvent] = None) -> None:
        result = reload_fn(animate=True)
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]

    from lib.presentation.utils import run_async

    return lambda e: run_async(page, _run, e)
