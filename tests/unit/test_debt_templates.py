"""Unit tests for debt templates."""

from __future__ import annotations

from lib.presentation.debts_templates import DEBT_TEMPLATES


def test_debt_templates_have_i18n_keys() -> None:
    assert len(DEBT_TEMPLATES) >= 6
    for template in DEBT_TEMPLATES:
        assert template.name_key.startswith("debt.template.")
        assert template.icon
        assert template.color.startswith("#")
