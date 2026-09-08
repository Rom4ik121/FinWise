"""Component-driven UI kit for FinWise screens.

Grouped public API. Implementations stay in ``widgets/`` so existing imports
and tests keep working; new code should prefer this package.

Submodule imports (``components.layout.grid``) must not load this file's
widget graph — keep re-exports lazy.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AccountCard",
    "CategoryPicker",
    "CurrencyTickerPicker",
    "DateTimeField",
    "DebtCard",
    "EmptyState",
    "GoalProgress",
    "LineItemsEditor",
    "SubscriptionCard",
    "SummaryCard",
    "TransactionTile",
    "adaptive_text",
    "budget_list_card",
    "card_action_button",
    "card_grid",
    "card_with_actions",
    "color_badge",
    "confirm_dialog",
    "dismiss_fullscreen",
    "dual_add_button",
    "fill_loading",
    "loading_indicator",
    "make_amount_field",
    "money_label",
    "open_fullscreen_form",
    "open_quick_add",
    "open_transfer",
    "page_column",
    "page_frame",
    "parse_amount",
]


def __getattr__(name: str) -> Any:
    if name in {
        "AccountCard",
        "DebtCard",
        "GoalProgress",
        "SubscriptionCard",
        "SummaryCard",
        "TransactionTile",
        "budget_list_card",
    }:
        from lib.presentation.components import cards as _cards

        return getattr(_cards, name)
    if name in {
        "confirm_dialog",
        "dismiss_fullscreen",
        "open_fullscreen_form",
        "open_quick_add",
        "open_transfer",
    }:
        from lib.presentation.components import dialogs as _dialogs

        return getattr(_dialogs, name)
    if name in {
        "CategoryPicker",
        "CurrencyTickerPicker",
        "DateTimeField",
        "LineItemsEditor",
        "dual_add_button",
        "make_amount_field",
        "parse_amount",
    }:
        from lib.presentation.components import inputs as _inputs

        return getattr(_inputs, name)
    if name in {
        "adaptive_text",
        "card_action_button",
        "card_grid",
        "card_with_actions",
        "color_badge",
        "money_label",
        "page_column",
        "page_frame",
    }:
        from lib.presentation.components import layout as _layout

        return getattr(_layout, name)
    if name in {"EmptyState", "fill_loading", "loading_indicator"}:
        if name == "EmptyState":
            from lib.presentation.widgets.empty_state import EmptyState

            return EmptyState
        from lib.presentation.widgets.loading import fill_loading, loading_indicator

        return fill_loading if name == "fill_loading" else loading_indicator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
