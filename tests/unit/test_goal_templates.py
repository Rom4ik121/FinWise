"""Goal template catalog sanity checks."""

from __future__ import annotations

from decimal import Decimal

from lib.presentation.icon_registry import resolve_icon
from lib.presentation.goals_templates import GOAL_TEMPLATES
from lib.infrastructure.services.localization import STRINGS


def test_goal_templates_have_valid_icons_and_i18n() -> None:
    assert len(GOAL_TEMPLATES) >= 15
    for template in GOAL_TEMPLATES:
        assert resolve_icon(template.icon) is not None, template.id
        assert template.name_key in STRINGS
        assert STRINGS[template.name_key]["ru"]
        assert STRINGS[template.name_key]["en"]
        assert STRINGS[template.name_key]["uz"]
        if template.items:
            for item in template.items:
                assert item.name_key in STRINGS
                assert Decimal(item.default_amount) > 0
        else:
            assert template.default_amount is not None
            assert Decimal(template.default_amount) > 0
