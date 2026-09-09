"""AccountStripPicker helpers."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.entities.account import Account
from lib.presentation.widgets.account_strip_picker import (
    AccountStripPicker,
    logical_index,
    loop_page_count,
    middle_copy_index,
    should_recenter,
)


def test_circular_index_helpers() -> None:
    assert loop_page_count(1) == 1
    assert loop_page_count(3) == 9
    assert logical_index(0, 3) == 0
    assert logical_index(3, 3) == 0
    assert logical_index(5, 3) == 2
    assert middle_copy_index(0, 3) == 3
    assert middle_copy_index(2, 3) == 5
    assert should_recenter(0, 3)
    assert should_recenter(8, 3)
    assert not should_recenter(4, 3)


def test_account_strip_picker_selects_value() -> None:
    accounts = [
        Account(id="a1", name="Cash", currency="USD", balance=Decimal("10.00"), color="#0D9488"),
        Account(id="a2", name="Card", currency="EUR", balance=Decimal("20.00"), color="#2563EB"),
    ]

    class _Page:
        width = 390
        height = 800

        def run_task(self, handler, *args, **kwargs):  # noqa: ANN001
            return None

    picker = AccountStripPicker(_Page(), accounts, lang="en", value="a2")  # type: ignore[arg-type]
    assert picker.value == "a2"
    assert picker.selected_account() is not None
    assert picker.selected_account().id == "a2"  # type: ignore[union-attr]
    # Circular strip clones accounts into the pager.
    assert len(picker._page_accounts) == 6
    picker.set_value("a1", notify=False)
    assert picker.value == "a1"
    picker.set_accounts([accounts[1]], value="a2", notify=False)
    assert picker.value == "a2"
    assert len(picker._accounts) == 1
    assert len(picker._page_accounts) == 1
