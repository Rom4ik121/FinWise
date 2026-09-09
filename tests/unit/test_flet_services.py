"""Attach Flet services without putting them in the visual tree."""

from __future__ import annotations

from lib.infrastructure.services.flet_services import (
    attach_page_service,
    existing_page_service,
)


class _Page:
    def __init__(self, *, web: bool = False) -> None:
        self.web = web
        self.services: list[object] = []
        self.updated = False

    def update(self) -> None:
        self.updated = True


def test_attach_skips_native_extension_on_web() -> None:
    page = _Page(web=True)
    assert attach_page_service(page, object()) is False
    assert page.services == []


def test_attach_allows_builtin_on_web() -> None:
    page = _Page(web=True)
    service = object()
    assert attach_page_service(page, service, native_extension=False) is True
    assert page.services == [service]


class _A:
    pass


class _B:
    pass


def test_attach_registers_on_native_page() -> None:
    page = _Page(web=False)
    first = _A()
    second = _B()
    assert attach_page_service(page, first) is True
    assert attach_page_service(page, second) is True
    assert len(page.services) == 2
    assert attach_page_service(page, _A()) is True
    assert len(page.services) == 2
    assert existing_page_service(page, _A) is first
