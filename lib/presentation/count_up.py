"""Count-up animation for money Text widgets after a manual refresh."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import flet as ft

from lib.presentation.utils import format_money, format_money_compact, format_money_parts, safe_update

_META_KEY = "count_up"
_PROGRESS_KEY = "progress_anim"
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


def mark_progress(control: ft.Control, target: float) -> ft.Control:
    """Tag a ProgressBar / ProgressRing so :func:`play_count_ups` can fill it."""
    meta = {
        _PROGRESS_KEY: True,
        "target": max(0.0, min(float(target), 1.0)),
    }
    existing = getattr(control, "data", None)
    if isinstance(existing, dict):
        existing.update(meta)
        control.data = existing
    else:
        control.data = meta
    return control


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


def _collect_progress(control: Any, out: list[Any]) -> None:
    if control is None:
        return
    data = getattr(control, "data", None)
    if isinstance(data, dict) and data.get(_PROGRESS_KEY):
        if isinstance(control, (ft.ProgressBar, ft.ProgressRing)):
            out.append(control)
    for child in getattr(control, "controls", None) or []:
        _collect_progress(child, out)
    _collect_progress(getattr(control, "content", None), out)


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
    """Animate marked money texts and progress bars; flush queued charts.

    Updates only ``root`` (never the whole page) so ListView scroll stays put.
    """
    chart_task = asyncio.create_task(_play_queued_charts())
    try:
        targets: list[ft.Text] = []
        bars: list[Any] = []
        _collect(root, targets)
        _collect_progress(root, bars)
        if not targets and not bars:
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
        bar_specs: list[tuple[Any, float]] = []
        for bar in bars:
            meta = bar.data if isinstance(bar.data, dict) else {}
            try:
                goal = max(0.0, min(float(meta.get("target") or 0), 1.0))
            except (TypeError, ValueError):
                continue
            bar_specs.append((bar, goal))
            bar.value = 0.0

        try:
            safe_update(root)
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
            for bar, goal in bar_specs:
                bar.value = goal if i == steps else goal * progress
            try:
                safe_update(root)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(delay)
    finally:
        await chart_task
        _ = page  # kept for API compatibility with callers


async def _play_queued_charts() -> None:
    try:
        from lib.presentation.widgets.charts import play_queued_charts

        await play_queued_charts()
    except Exception:  # noqa: BLE001
        return


async def flush_chart_draws() -> None:
    """Drain any leftover chart animations (safe after a failed reload)."""
    await _play_queued_charts()
