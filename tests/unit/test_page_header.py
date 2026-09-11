"""page_header must not wrap a Row that contains Expanded children."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from lib.presentation.styles import form_header_bar, page_header


class _FakePage:
    def __init__(self, width: float, height: float = 780) -> None:
        self.width = width
        self.height = height
        self.window = type("W", (), {"width": width, "height": height})()


def _assert_header_does_not_wrap_expanded(header: ft.Container) -> None:
    row = header.content
    assert isinstance(row, ft.Row)
    assert row.wrap in (False, None)
    left, actions = row.controls
    assert left.expand is True
    assert getattr(actions, "wrap", False) in (False, None)
    title = left.controls[-1]
    assert title.overflow == ft.TextOverflow.ELLIPSIS
    assert title.expand is True


def test_page_header_does_not_wrap_expanded_row_on_xs() -> None:
    """Flutter forbids Expanded inside a wrapping Flex — zeros the page on Windows xs."""
    page = _FakePage(320)
    header = page_header(
        "Settings",
        actions=[ft.Text("ok")],
        page=page,  # type: ignore[arg-type]
    )
    _assert_header_does_not_wrap_expanded(header)


def test_form_header_bar_does_not_wrap_expanded_row_on_xs() -> None:
    page = _FakePage(312)
    header = form_header_bar(
        "Edit account",
        actions=[ft.Text("ok")],
        page=page,  # type: ignore[arg-type]
    )
    _assert_header_does_not_wrap_expanded(header)


def test_no_wrap_is_narrow_beside_expand_in_presentation() -> None:
    """Regression: wrap=is_narrow on a Flex that also expands children."""
    root = Path(__file__).resolve().parents[2] / "lib" / "presentation"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "wrap=is_narrow" in text:
            hits.append(str(path.relative_to(root.parent.parent)))
    assert hits == []


def test_page_frame_on_back_adds_leading_arrow() -> None:
    from lib.presentation.components.layout.page_shell import page_frame

    called: list[int] = []
    kids = page_frame(
        title="Templates",
        body=ft.Text("body"),
        on_back=lambda: called.append(1),
        lang="en",
    )
    header = kids[0]
    leading = header.content.controls[0].controls[0]
    assert isinstance(leading, ft.IconButton)
    assert leading.icon == ft.Icons.ARROW_BACK
    leading.on_click(None)
    assert called == [1]


def test_secondary_pages_wire_back_to_close_secondary() -> None:
    """Every non-primary route must have a leading Back that clears the route."""
    pages = Path(__file__).resolve().parents[2] / "lib" / "presentation" / "pages"
    secondary = (
        "recurring.py",
        "csv_import.py",
        "goals.py",
        "debts.py",
        "subscriptions.py",
        "budgets.py",
        "analytics.py",
        "currencies.py",
        "account_detail.py",
    )
    missing = [
        name
        for name in secondary
        if "on_back=state.close_secondary" not in (pages / name).read_text(encoding="utf-8")
    ]
    assert missing == []
    primary = ("dashboard.py", "transactions.py", "accounts.py", "settings.py")
    leaked = [
        name
        for name in primary
        if "on_back=state.close_secondary" in (pages / name).read_text(encoding="utf-8")
    ]
    assert leaked == []
