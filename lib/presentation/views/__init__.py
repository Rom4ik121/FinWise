"""Screen layer — high-level assembly of components.

Implementations currently live in ``lib.presentation.pages`` (large Flet
views). This package is the stable import path for the app shell.
"""

from lib.presentation.pages.account_detail import AccountDetailPage
from lib.presentation.pages.accounts import AccountsPage
from lib.presentation.pages.analytics import AnalyticsPage
from lib.presentation.pages.budgets import BudgetsPage
from lib.presentation.pages.currencies import CurrenciesPage
from lib.presentation.pages.csv_import import CsvImportPage
from lib.presentation.pages.dashboard import DashboardPage
from lib.presentation.pages.debts import DebtsPage
from lib.presentation.pages.goals import GoalsPage
from lib.presentation.pages.recurring import RecurringPage
from lib.presentation.pages.settings import SettingsPage
from lib.presentation.pages.subscriptions import SubscriptionsPage
from lib.presentation.pages.transactions import TransactionsPage

__all__ = [
    "AccountDetailPage",
    "AccountsPage",
    "AnalyticsPage",
    "BudgetsPage",
    "CurrenciesPage",
    "CsvImportPage",
    "DashboardPage",
    "DebtsPage",
    "GoalsPage",
    "RecurringPage",
    "SettingsPage",
    "SubscriptionsPage",
    "TransactionsPage",
]
