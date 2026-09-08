"""Layout primitives: type, grids, badges, page chrome."""

from lib.presentation.components.layout.actions import (
    card_action_button,
    card_with_actions,
)
from lib.presentation.components.layout.badge import color_badge
from lib.presentation.components.layout.grid import card_grid
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.components.layout.text import adaptive_text, money_label

__all__ = [
    "adaptive_text",
    "card_action_button",
    "card_grid",
    "card_with_actions",
    "color_badge",
    "money_label",
    "page_column",
    "page_frame",
]
