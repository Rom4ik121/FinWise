"""Coalesce page reloads so off-screen token bumps don't replay N times."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

import flet as ft

from lib.presentation.utils import run_async

ReloadFn = Callable[..., Awaitable[Any]]


class ReloadGate:
    """At most one in-flight reload; extra requests collapse into a single follow-up.

    The first reload runs even before the host is mounted (so the first frame
    is not blank). After that, bumps while the view is off-screen wait for
    :meth:`on_mounted` / :meth:`mark_shown`.

    Cached-but-hidden tabs in Flet often still expose ``control.page``, so
    visibility is an explicit flag — otherwise every save reloads every tab
    the user has ever opened and the phone starts hitching.
    """

    def __init__(self, page: ft.Page, host: ft.Control, reload_fn: ReloadFn) -> None:
        self._page = page
        self._host = host
        self._reload_fn = reload_fn
        self._takes_animate = "animate" in inspect.signature(reload_fn).parameters
        self._busy = False
        self._pending = False
        self._pending_animate = False
        self._completed = False
        self._visible = False
        self._hook_unmount()

    def _hook_unmount(self) -> None:
        host = self._host
        if getattr(host, "_fw_gate_unmount", False):
            return
        setattr(host, "_fw_gate_unmount", True)
        original = getattr(host, "will_unmount", None)

        def _will_unmount(*args: Any, **kwargs: Any) -> Any:
            self.mark_hidden()
            if callable(original):
                try:
                    return original(*args, **kwargs)
                except TypeError:
                    return original()
            return None

        host.will_unmount = _will_unmount  # type: ignore[method-assign]

    def mark_shown(self) -> None:
        """Shell is displaying this view (even if Flet skips a remount)."""
        self._visible = True

    def mark_hidden(self) -> None:
        """Shell swapped away from this view — do not reload in the background."""
        self._visible = False

    def request(self, animate: bool = False) -> None:
        """Ask for a reload; coalesces with any already queued/running one."""
        self._pending = True
        if animate:
            self._pending_animate = True
        if self._busy:
            return
        if self._completed and not self._visible:
            return
        run_async(self._page, self._drain)

    def on_mounted(self) -> None:
        """Flush a reload that was requested while this view was hidden."""
        self._visible = True
        if not self._pending or self._busy:
            return
        run_async(self._page, self._drain)

    async def _drain(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            while self._pending:
                # After the first paint, do not burn CPU for off-screen hosts —
                # keep ``_pending`` and wait for :meth:`on_mounted`.
                if self._completed and not self._visible:
                    break
                self._pending = False
                animate = self._pending_animate
                self._pending_animate = False
                await self._invoke(animate)
                self._completed = True
        finally:
            self._busy = False
            if self._pending and (self._visible or not self._completed):
                run_async(self._page, self._drain)

    async def _invoke(self, animate: bool) -> None:
        if self._takes_animate:
            await self._reload_fn(animate=animate)
            return
        await self._reload_fn()
