"""Budget template catalog sanity checks."""

from __future__ import annotations

from decimal import Decimal

from lib.infrastructure.services.localization import STRINGS
from lib.presentation.budgets_templates import BUDGET_TEMPLATES
from lib.presentation.icon_registry import resolve_icon


def test_budget_templates_have_valid_icons_and_i18n() -> None:
    assert len(BUDGET_TEMPLATES) >= 8
    for template in BUDGET_TEMPLATES:
        assert resolve_icon(template.icon) is not None, template.id
        key = f"budgets.template.{template.id}"
        assert key in STRINGS
        assert STRINGS[key]["ru"]
        assert STRINGS[key]["en"]
        assert STRINGS[key]["uz"]
        assert Decimal(template.default_amount) > 0
        assert template.color.startswith("#")
        assert template.category
