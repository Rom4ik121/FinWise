"""Entity cards — thin public API over ``lib.presentation.widgets``."""

from lib.presentation.widgets.account_card import AccountCard
from lib.presentation.widgets.budget_summary_ring import budget_list_card
from lib.presentation.widgets.debt_card import DebtCard
from lib.presentation.widgets.goal_progress import GoalProgress
from lib.presentation.widgets.subscription_card import SubscriptionCard
from lib.presentation.widgets.summary_card import SummaryCard
from lib.presentation.widgets.transaction_tile import TransactionTile

__all__ = [
    "AccountCard",
    "DebtCard",
    "GoalProgress",
    "SubscriptionCard",
    "SummaryCard",
    "TransactionTile",
    "budget_list_card",
]
