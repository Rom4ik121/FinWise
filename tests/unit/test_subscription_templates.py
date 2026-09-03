"""Unit tests for subscription templates."""

from __future__ import annotations

from lib.presentation.subscriptions_templates import SUBSCRIPTION_TEMPLATES


def test_subscription_templates_have_i18n_keys() -> None:
    assert len(SUBSCRIPTION_TEMPLATES) >= 8
    for template in SUBSCRIPTION_TEMPLATES:
        assert template.name_key.startswith("subscription.template.")
        assert template.icon
        assert template.color.startswith("#")
        assert template.default_amount
