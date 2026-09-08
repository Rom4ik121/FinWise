"""Coalesce hidden-page reloads into a single follow-up."""

from __future__ import annotations

import asyncio

from lib.presentation.reload_gate import ReloadGate


class _FakePage:
    def run_task(self, handler, *args, **kwargs):  # noqa: ANN001
        asyncio.get_running_loop().create_task(handler(*args, **kwargs))


class _Host:
    def __init__(self) -> None:
        self.page = None


def test_first_request_runs_even_if_unmounted() -> None:
    calls: list[bool] = []

    async def reload(*, animate: bool = False) -> None:
        calls.append(animate)

    async def _run() -> None:
        host = _Host()
        page = _FakePage()
        gate = ReloadGate(page, host, reload)  # type: ignore[arg-type]
        gate.request()
        await asyncio.sleep(0.05)
        assert calls == [False]

    asyncio.run(_run())


def test_later_unmounted_requests_wait_for_mount() -> None:
    calls: list[bool] = []

    async def reload(*, animate: bool = False) -> None:
        calls.append(animate)

    async def _run() -> None:
        host = _Host()
        page = _FakePage()
        host.page = page
        gate = ReloadGate(page, host, reload)  # type: ignore[arg-type]
        gate.request()
        await asyncio.sleep(0.05)
        assert calls == [False]
        host.page = None
        gate.request()
        gate.request(True)
        await asyncio.sleep(0.05)
        assert calls == [False]
        host.page = page
        gate.on_mounted()
        await asyncio.sleep(0.05)
        assert calls == [False, True]

    asyncio.run(_run())


def test_mark_hidden_skips_reload_until_shown() -> None:
    calls: list[int] = []

    async def reload(*, animate: bool = False) -> None:
        calls.append(1)

    async def _run() -> None:
        host = _Host()
        page = _FakePage()
        host.page = page
        gate = ReloadGate(page, host, reload)  # type: ignore[arg-type]
        gate.on_mounted()
        gate.request()
        await asyncio.sleep(0.05)
        assert len(calls) == 1
        gate.mark_hidden()
        gate.request()
        gate.request()
        await asyncio.sleep(0.05)
        assert len(calls) == 1
        gate.mark_shown()
        gate.on_mounted()
        await asyncio.sleep(0.05)
        assert len(calls) == 2

    asyncio.run(_run())


def test_gate_coalesces_in_flight_requests() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def reload(*, animate: bool = False) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    async def _run() -> None:
        host = _Host()
        page = _FakePage()
        host.page = page
        gate = ReloadGate(page, host, reload)  # type: ignore[arg-type]
        gate.on_mounted()
        gate.request()
        await started.wait()
        gate.request()
        gate.request()
        release.set()
        await asyncio.sleep(0.05)
        assert calls == 2

    asyncio.run(_run())
