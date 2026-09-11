"""Simple dependency-injection container and factory.

``build_container`` wires infrastructure repositories (when available) to
domain use cases. Missing modules are recorded so a partial build remains
usable during incremental development.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from lib.core.config import AppConfig, get_default_config
from lib.core.database import get_session_factory, init_db

logger = logging.getLogger("finanse.dependencies")


@dataclass
class Container:
    """Holds config, repositories, services, and use-case instances.

    Attributes that could not be constructed during a partial build remain
    ``None``. Check :attr:`missing` / :attr:`errors` for diagnostics.
    """

    config: AppConfig

    # Repositories
    transaction_repository: Any = None
    account_repository: Any = None
    goal_repository: Any = None
    goal_audit_repository: Any = None
    debt_repository: Any = None
    debt_audit_repository: Any = None
    subscription_repository: Any = None
    subscription_audit_repository: Any = None
    currency_repository: Any = None
    category_repository: Any = None
    settings_repository: Any = None
    budget_repository: Any = None
    exchange_connection_repository: Any = None
    recurring_rule_repository: Any = None
    net_worth_repository: Any = None

    # Optional infrastructure services
    exchange_rate_provider: Any = None
    notification_service: Any = None
    backup_service: Any = None
    export_service: Any = None
    encryption_service: Any = None

    # Use cases — transactions
    add_transaction: Any = None
    update_transaction: Any = None
    delete_transaction: Any = None
    list_transactions: Any = None
    get_transaction_stats: Any = None
    transfer_between_accounts: Any = None

    # Use cases — accounts
    create_account: Any = None
    update_account: Any = None
    delete_account: Any = None
    list_accounts: Any = None
    recalculate_account_balance: Any = None
    connect_exchange_account: Any = None
    sync_exchange_account: Any = None

    # Use cases — goals
    create_goal: Any = None
    update_goal: Any = None
    delete_goal: Any = None
    list_goals: Any = None
    contribute_to_goal: Any = None
    get_goal_projection: Any = None
    archive_goal: Any = None
    duplicate_goal: Any = None
    delete_goal_contribution: Any = None
    close_goal_item: Any = None
    close_goal_early: Any = None
    withdraw_from_goal: Any = None
    get_goal_contribution_series: Any = None
    append_goal_audit: Any = None
    list_goal_audit: Any = None

    # Use cases — debts
    create_debt: Any = None
    update_debt: Any = None
    delete_debt: Any = None
    list_debts: Any = None
    repay_debt: Any = None
    calculate_debt_interest: Any = None
    get_debt_projection: Any = None
    archive_debt: Any = None
    delete_debt_payment: Any = None
    mark_overdue_debts: Any = None
    accrue_debt_interest: Any = None
    undo_last_debt_payment: Any = None
    list_debt_counterparties: Any = None
    duplicate_debt: Any = None
    forgive_debt: Any = None
    get_debt_payment_series: Any = None
    append_debt_audit: Any = None
    list_debt_audit: Any = None

    # Use cases — subscriptions
    create_subscription: Any = None
    update_subscription: Any = None
    delete_subscription: Any = None
    list_subscriptions: Any = None
    process_due_subscriptions: Any = None
    pause_subscription: Any = None
    resume_subscription: Any = None
    charge_subscription_now: Any = None
    delete_subscription_charge: Any = None
    get_subscription_analytics: Any = None
    get_subscription: Any = None
    skip_subscription_period: Any = None
    duplicate_subscription: Any = None
    cancel_subscription: Any = None
    get_subscription_charge_series: Any = None
    append_subscription_audit: Any = None
    list_subscription_audit: Any = None

    # Use cases — currencies / settings / export / categories
    update_exchange_rates: Any = None
    convert_currency: Any = None
    list_currencies: Any = None
    seed_currencies: Any = None
    get_settings: Any = None
    update_settings: Any = None
    get_pin_credentials: Any = None
    set_pin_credentials: Any = None
    clear_pin_credentials: Any = None
    export_data: Any = None
    list_categories: Any = None
    create_category: Any = None
    update_category: Any = None
    delete_category: Any = None
    find_or_create_category: Any = None
    set_budget: Any = None
    delete_budget: Any = None
    copy_budgets_from_previous: Any = None
    suggest_budget_limit: Any = None
    suggest_subscription_budgets: Any = None
    get_budget_analytics: Any = None
    get_budget_progress: Any = None
    get_budgets_for_month: Any = None
    recalculate_budget_spent: Any = None
    create_recurring_rule: Any = None
    update_recurring_rule: Any = None
    delete_recurring_rule: Any = None
    list_recurring_rules: Any = None
    pause_recurring_rule: Any = None
    skip_recurring_occurrence: Any = None
    process_due_recurring: Any = None
    preview_csv_import: Any = None
    commit_csv_import: Any = None
    record_net_worth_snapshot: Any = None
    list_net_worth_snapshots: Any = None

    missing: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def require(self, name: str) -> Any:
        """Return a wired dependency or raise if it was not built."""
        value = getattr(self, name, None)
        if value is None:
            detail = self.errors.get(name, "not constructed")
            raise RuntimeError(f"Dependency '{name}' is unavailable: {detail}")
        return value

    def rebind_session_factory(self, session_factory: Any) -> None:
        """Point every SQLAlchemy repository at a fresh session factory.

        Used after ``reset_engine()`` + DB restore so open repos do not keep
        a disposed engine.
        """
        for attr in (
            "transaction_repository",
            "account_repository",
            "goal_repository",
            "debt_repository",
            "subscription_repository",
            "currency_repository",
            "category_repository",
            "settings_repository",
            "budget_repository",
            "exchange_connection_repository",
            "goal_audit_repository",
            "debt_audit_repository",
            "subscription_audit_repository",
            "exchange_connection_repository",
            "recurring_rule_repository",
            "net_worth_repository",
        ):
            repo = getattr(self, attr, None)
            if repo is not None and hasattr(repo, "_session_factory"):
                repo._session_factory = session_factory


def _try_import(module_path: str, attr: str) -> tuple[Optional[type], Optional[str]]:
    """Import ``attr`` from ``module_path``.

    Returns:
        ``(class_or_none, error_message_or_none)``.
    """
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        return None, f"import failed: {exc}"
    try:
        return getattr(module, attr), None
    except AttributeError as exc:
        return None, f"attribute missing: {exc}"


def _construct(
    container: Container,
    attr_name: str,
    module_path: str,
    class_name: str,
    *ctor_args: Any,
    **ctor_kwargs: Any,
) -> None:
    """Instantiate a class into ``container`` or record why it failed."""
    cls, err = _try_import(module_path, class_name)
    if cls is None:
        container.missing.append(attr_name)
        container.errors[attr_name] = err or "unknown import error"
        logger.debug("Skip %s: %s", attr_name, container.errors[attr_name])
        return
    try:
        setattr(container, attr_name, cls(*ctor_args, **ctor_kwargs))
    except Exception as exc:  # pragma: no cover - defensive
        container.missing.append(attr_name)
        container.errors[attr_name] = f"construct failed: {exc}"
        logger.warning("Failed to construct %s: %s", attr_name, exc)


def build_container(
    config: Optional[AppConfig] = None,
    *,
    init_database: bool = True,
) -> Container:
    """Build a :class:`Container` with repositories and use cases.

    Infrastructure repository implementations are expected at:

    * ``lib.infrastructure.repositories.transaction_repository.SqlAlchemyTransactionRepository``
    * ``lib.infrastructure.repositories.account_repository.SqlAlchemyAccountRepository``
    * ``lib.infrastructure.repositories.goal_repository.SqlAlchemyGoalRepository``
    * ``lib.infrastructure.repositories.debt_repository.SqlAlchemyDebtRepository``
    * ``lib.infrastructure.repositories.subscription_repository.SqlAlchemySubscriptionRepository``
    * ``lib.infrastructure.repositories.currency_repository.SqlAlchemyCurrencyRepository``
    * ``lib.infrastructure.repositories.settings_repository.SqlAlchemySettingsRepository``

    Optional service:

    * ``lib.infrastructure.services.exchange_rate_provider.HttpExchangeRateProvider``

    When a module is missing, the corresponding slot stays ``None`` and the
    name is listed in :attr:`Container.missing`.
    """
    cfg = config or get_default_config()
    cfg.ensure_directories()
    container = Container(config=cfg)

    if init_database:
        try:
            init_db(cfg)
        except Exception as exc:
            container.errors["database"] = str(exc)
            logger.warning("init_db failed: %s", exc)

    session_factory = get_session_factory(cfg)

    # --- Repositories (infrastructure) ---------------------------------
    repo_specs = [
        (
            "transaction_repository",
            "lib.infrastructure.repositories.transaction_repository",
            "SqlAlchemyTransactionRepository",
        ),
        (
            "account_repository",
            "lib.infrastructure.repositories.account_repository",
            "SqlAlchemyAccountRepository",
        ),
        (
            "goal_repository",
            "lib.infrastructure.repositories.goal_repository",
            "SqlAlchemyGoalRepository",
        ),
        (
            "goal_audit_repository",
            "lib.infrastructure.repositories.goal_audit_repository",
            "SqlAlchemyGoalAuditRepository",
        ),
        (
            "debt_audit_repository",
            "lib.infrastructure.repositories.debt_audit_repository",
            "SqlAlchemyDebtAuditRepository",
        ),
        (
            "debt_repository",
            "lib.infrastructure.repositories.debt_repository",
            "SqlAlchemyDebtRepository",
        ),
        (
            "subscription_repository",
            "lib.infrastructure.repositories.subscription_repository",
            "SqlAlchemySubscriptionRepository",
        ),
        (
            "subscription_audit_repository",
            "lib.infrastructure.repositories.subscription_audit_repository",
            "SqlAlchemySubscriptionAuditRepository",
        ),
        (
            "currency_repository",
            "lib.infrastructure.repositories.currency_repository",
            "SqlAlchemyCurrencyRepository",
        ),
        (
            "settings_repository",
            "lib.infrastructure.repositories.settings_repository",
            "SqlAlchemySettingsRepository",
        ),
        (
            "category_repository",
            "lib.infrastructure.repositories.category_repository",
            "SqlAlchemyCategoryRepository",
        ),
        (
            "budget_repository",
            "lib.infrastructure.repositories.budget_repository",
            "SqlAlchemyBudgetRepository",
        ),
        (
            "exchange_connection_repository",
            "lib.infrastructure.repositories.exchange_connection_repository",
            "SqlAlchemyExchangeConnectionRepository",
        ),
        (
            "recurring_rule_repository",
            "lib.infrastructure.repositories.recurring_rule_repository",
            "SqlAlchemyRecurringRuleRepository",
        ),
        (
            "net_worth_repository",
            "lib.infrastructure.repositories.net_worth_repository",
            "SqlAlchemyNetWorthRepository",
        ),
    ]
    for attr, module_path, class_name in repo_specs:
        _construct(container, attr, module_path, class_name, session_factory)

    _construct(
        container,
        "exchange_rate_provider",
        "lib.infrastructure.services.exchange_rate_provider",
        "HttpExchangeRateProvider",
        api_key=cfg.exchange_rate_api_key,
    )
    _construct(
        container,
        "notification_service",
        "lib.infrastructure.services.notification_service",
        "NotificationService",
    )
    _construct(
        container,
        "backup_service",
        "lib.infrastructure.services.backup_service",
        "BackupService",
        cfg,
    )
    _construct(
        container,
        "export_service",
        "lib.infrastructure.services.export_service",
        "ExportService",
        cfg,
    )
    _construct(
        container,
        "encryption_service",
        "lib.infrastructure.services.encryption_service",
        "EncryptionService",
    )

    # --- Use cases (domain) --------------------------------------------
    from lib.domain.use_cases.accounts import (
        CreateAccountUseCase,
        DeleteAccountUseCase,
        ListAccountsUseCase,
        RecalculateAccountBalanceUseCase,
        UpdateAccountUseCase,
    )
    from lib.domain.use_cases.currencies import (
        ConvertCurrencyUseCase,
        ListCurrenciesUseCase,
        UpdateExchangeRatesUseCase,
    )
    from lib.domain.use_cases.debts import (
        AccrueDebtInterestUseCase,
        AppendDebtAuditUseCase,
        ArchiveDebtUseCase,
        CalculateDebtInterestUseCase,
        CreateDebtUseCase,
        DeleteDebtPaymentUseCase,
        DeleteDebtUseCase,
        DuplicateDebtUseCase,
        ForgiveDebtUseCase,
        GetDebtProjectionUseCase,
        ListDebtAuditUseCase,
        ListDebtCounterpartiesUseCase,
        ListDebtsUseCase,
        MarkOverdueDebtsUseCase,
        RepayDebtUseCase,
        UndoLastDebtPaymentUseCase,
        UpdateDebtUseCase,
    )
    from lib.domain.use_cases.debt_insights import GetDebtPaymentSeriesUseCase
    from lib.domain.use_cases.export_data import ExportDataUseCase
    from lib.domain.use_cases.net_worth import (
        ListNetWorthSnapshotsUseCase,
        RecordNetWorthSnapshotUseCase,
    )
    from lib.domain.use_cases.import_csv import (
        CommitCsvImportUseCase,
        PreviewCsvImportUseCase,
    )
    from lib.domain.use_cases.recurring import (
        CreateRecurringRuleUseCase,
        DeleteRecurringRuleUseCase,
        ListRecurringRulesUseCase,
        PauseRecurringRuleUseCase,
        ProcessDueRecurringRulesUseCase,
        SkipRecurringOccurrenceUseCase,
        UpdateRecurringRuleUseCase,
    )
    from lib.domain.use_cases.goals import (
        ArchiveGoalUseCase,
        CloseGoalEarlyUseCase,
        CloseGoalItemUseCase,
        ContributeToGoalUseCase,
        CreateGoalUseCase,
        DeleteGoalContributionUseCase,
        DeleteGoalUseCase,
        DuplicateGoalUseCase,
        GetGoalProjectionUseCase,
        ListGoalAuditUseCase,
        AppendGoalAuditUseCase,
        ListGoalsUseCase,
        UpdateGoalUseCase,
        WithdrawFromGoalUseCase,
    )
    from lib.domain.use_cases.goal_insights import GetGoalContributionSeriesUseCase
    from lib.domain.use_cases.budget_insights import GetBudgetAnalyticsUseCase
    from lib.domain.use_cases.budgets import (
        CopyBudgetsFromPreviousMonthUseCase,
        DeleteBudgetUseCase,
        GetBudgetProgressUseCase,
        GetBudgetsForMonthUseCase,
        RecalculateBudgetSpentUseCase,
        SetBudgetUseCase,
        SuggestBudgetLimitUseCase,
        SuggestSubscriptionBudgetsUseCase,
    )
    from lib.domain.use_cases.categories import (
        CreateCategoryUseCase,
        DeleteCategoryUseCase,
        FindOrCreateCategoryUseCase,
        ListCategoriesUseCase,
        UpdateCategoryUseCase,
    )
    from lib.domain.use_cases.settings import (
        ClearPinCredentialsUseCase,
        GetPinCredentialsUseCase,
        GetSettingsUseCase,
        SetPinCredentialsUseCase,
        UpdateSettingsUseCase,
    )
    from lib.domain.use_cases.subscriptions import (
        AppendSubscriptionAuditUseCase,
        CancelSubscriptionUseCase,
        ChargeSubscriptionNowUseCase,
        CreateSubscriptionUseCase,
        DeleteSubscriptionChargeUseCase,
        DeleteSubscriptionUseCase,
        DuplicateSubscriptionUseCase,
        GetSubscriptionAnalyticsUseCase,
        GetSubscriptionUseCase,
        ListSubscriptionAuditUseCase,
        ListSubscriptionsUseCase,
        PauseSubscriptionUseCase,
        ProcessDueSubscriptionsUseCase,
        ResumeSubscriptionUseCase,
        SkipSubscriptionPeriodUseCase,
        UpdateSubscriptionUseCase,
    )
    from lib.domain.use_cases.subscription_insights import (
        GetSubscriptionChargeSeriesUseCase,
    )
    from lib.domain.use_cases.transactions import (
        AddTransactionUseCase,
        DeleteTransactionUseCase,
        GetTransactionStatsUseCase,
        ListTransactionsUseCase,
        TransferAccountsUseCase,
        UpdateTransactionUseCase,
    )

    def _wire(attr: str, factory: Any, *deps: str) -> None:
        values = []
        for dep in deps:
            value = getattr(container, dep)
            if value is None:
                container.missing.append(attr)
                container.errors[attr] = f"missing dependency: {dep}"
                return
            values.append(value)
        try:
            setattr(container, attr, factory(*values))
        except Exception as exc:  # pragma: no cover
            container.missing.append(attr)
            container.errors[attr] = f"construct failed: {exc}"

    def _wire_transaction(attr: str, factory: Any) -> None:
        required = (
            "transaction_repository",
            "account_repository",
            "goal_repository",
            "debt_repository",
        )
        values = []
        for dep in required:
            value = getattr(container, dep)
            if value is None:
                container.missing.append(attr)
                container.errors[attr] = f"missing dependency: {dep}"
                return
            values.append(value)
        try:
            kwargs: dict[str, Any] = {
                "budgets": container.budget_repository,
                "settings": container.settings_repository,
                "notifications": container.notification_service,
                "currencies": container.currency_repository,
            }
            if attr in {
                "add_transaction",
                "update_transaction",
                "delete_transaction",
            }:
                kwargs["session_factory"] = session_factory
            if attr == "delete_transaction":
                from lib.infrastructure.services.media_store import MediaStore

                store = MediaStore(container.config)

                def _media_cleanup(tx_id: str, paths: list[str]) -> None:
                    store.delete_paths(list(paths or []))
                    store.delete_transaction_dir(tx_id)

                kwargs["media_cleanup"] = _media_cleanup
            setattr(
                container,
                attr,
                factory(*values, **kwargs),
            )
        except Exception as exc:  # pragma: no cover
            container.missing.append(attr)
            container.errors[attr] = f"construct failed: {exc}"

    _wire_transaction("add_transaction", AddTransactionUseCase)
    _wire_transaction("update_transaction", UpdateTransactionUseCase)
    _wire_transaction("delete_transaction", DeleteTransactionUseCase)
    _wire("list_transactions", ListTransactionsUseCase, "transaction_repository")
    _wire(
        "get_transaction_stats",
        GetTransactionStatsUseCase,
        "transaction_repository",
        "currency_repository",
        "settings_repository",
    )

    _wire(
        "create_account",
        CreateAccountUseCase,
        "account_repository",
        "settings_repository",
    )
    _wire(
        "update_account",
        UpdateAccountUseCase,
        "account_repository",
        "currency_repository",
        "transaction_repository",
    )
    if container.update_account is not None:
        try:
            container.update_account._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire("delete_account", DeleteAccountUseCase, "account_repository")
    _wire("list_accounts", ListAccountsUseCase, "account_repository")
    _wire(
        "recalculate_account_balance",
        RecalculateAccountBalanceUseCase,
        "account_repository",
        "transaction_repository",
    )
    if (
        container.account_repository is not None
        and container.exchange_connection_repository is not None
    ):
        try:
            from lib.domain.use_cases.exchange_sync import (
                ConnectExchangeAccountUseCase,
                SyncExchangeAccountUseCase,
            )
            from lib.infrastructure.api.ccxt_exchange_client import (
                fetch_snapshot as _fetch_snapshot,
                test_credentials as _test_credentials,
            )
            from lib.infrastructure.services.secret_box import (
                decrypt_secret,
                encrypt_secret,
            )
            from types import SimpleNamespace

            gateway = SimpleNamespace(
                test_credentials=_test_credentials,
                fetch_snapshot=_fetch_snapshot,
            )
            container.connect_exchange_account = ConnectExchangeAccountUseCase(
                container.account_repository,
                container.exchange_connection_repository,
                config=cfg,
                gateway=gateway,
                encrypt_secret=encrypt_secret,
            )
            if container.transaction_repository is not None:
                container.sync_exchange_account = SyncExchangeAccountUseCase(
                    container.account_repository,
                    container.transaction_repository,
                    container.exchange_connection_repository,
                    config=cfg,
                    add_transaction=container.add_transaction,
                    gateway=gateway,
                    decrypt_secret=decrypt_secret,
                )
        except Exception as exc:  # pragma: no cover
            container.missing.append("connect_exchange_account")
            container.errors["connect_exchange_account"] = f"construct failed: {exc}"
    else:
        container.missing.append("connect_exchange_account")
        container.errors["connect_exchange_account"] = "missing exchange dependencies"

    _wire("create_goal", CreateGoalUseCase, "goal_repository")
    _wire(
        "update_goal",
        UpdateGoalUseCase,
        "goal_repository",
        "currency_repository",
    )
    _wire(
        "delete_goal",
        DeleteGoalUseCase,
        "goal_repository",
        "transaction_repository",
    )
    if container.delete_goal is not None:
        try:
            container.delete_goal._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire("list_goals", ListGoalsUseCase, "goal_repository")
    _wire("archive_goal", ArchiveGoalUseCase, "goal_repository")
    _wire("close_goal_item", CloseGoalItemUseCase, "goal_repository")
    _wire("close_goal_early", CloseGoalEarlyUseCase, "goal_repository")
    _wire("duplicate_goal", DuplicateGoalUseCase, "goal_repository")
    _wire(
        "get_goal_projection",
        GetGoalProjectionUseCase,
        "goal_repository",
        "transaction_repository",
    )
    _wire(
        "delete_goal_contribution",
        DeleteGoalContributionUseCase,
        "transaction_repository",
        "delete_transaction",
    )
    _wire(
        "contribute_to_goal",
        ContributeToGoalUseCase,
        "goal_repository",
        "account_repository",
        "add_transaction",
        "currency_repository",
        "transaction_repository",
    )
    _wire(
        "withdraw_from_goal",
        WithdrawFromGoalUseCase,
        "goal_repository",
        "account_repository",
        "add_transaction",
        "currency_repository",
    )
    _wire(
        "get_goal_contribution_series",
        GetGoalContributionSeriesUseCase,
        "transaction_repository",
    )
    _wire("append_goal_audit", AppendGoalAuditUseCase, "goal_audit_repository")
    _wire("list_goal_audit", ListGoalAuditUseCase, "goal_audit_repository")

    _wire(
        "create_debt",
        CreateDebtUseCase,
        "debt_repository",
        "account_repository",
        "add_transaction",
        "currency_repository",
    )
    if container.create_debt is not None:
        try:
            container.create_debt._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire(
        "update_debt",
        UpdateDebtUseCase,
        "debt_repository",
        "currency_repository",
    )
    _wire(
        "delete_debt",
        DeleteDebtUseCase,
        "debt_repository",
        "transaction_repository",
        "delete_transaction",
    )
    if container.delete_debt is not None:
        try:
            container.delete_debt._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire("list_debts", ListDebtsUseCase, "debt_repository")
    _wire("archive_debt", ArchiveDebtUseCase, "debt_repository")
    _wire("mark_overdue_debts", MarkOverdueDebtsUseCase, "debt_repository")
    _wire("accrue_debt_interest", AccrueDebtInterestUseCase, "debt_repository")
    _wire(
        "list_debt_counterparties",
        ListDebtCounterpartiesUseCase,
        "debt_repository",
    )
    _wire(
        "get_debt_projection",
        GetDebtProjectionUseCase,
        "debt_repository",
        "transaction_repository",
    )
    _wire(
        "delete_debt_payment",
        DeleteDebtPaymentUseCase,
        "transaction_repository",
        "delete_transaction",
    )
    _wire(
        "undo_last_debt_payment",
        UndoLastDebtPaymentUseCase,
        "transaction_repository",
        "delete_debt_payment",
    )
    _wire(
        "repay_debt",
        RepayDebtUseCase,
        "debt_repository",
        "account_repository",
        "add_transaction",
        "currency_repository",
        "transaction_repository",
    )
    _wire("duplicate_debt", DuplicateDebtUseCase, "debt_repository")
    _wire("forgive_debt", ForgiveDebtUseCase, "debt_repository")
    _wire(
        "get_debt_payment_series",
        GetDebtPaymentSeriesUseCase,
        "transaction_repository",
    )
    _wire("append_debt_audit", AppendDebtAuditUseCase, "debt_audit_repository")
    _wire("list_debt_audit", ListDebtAuditUseCase, "debt_audit_repository")
    _wire(
        "calculate_debt_interest",
        CalculateDebtInterestUseCase,
        "debt_repository",
    )

    _wire(
        "create_subscription",
        CreateSubscriptionUseCase,
        "subscription_repository",
        "category_repository",
    )
    if container.create_subscription is not None:
        # Optional audit — do not fail the use case if audit repo is missing.
        try:
            container.create_subscription._audit = (  # type: ignore[attr-defined]
                container.subscription_audit_repository
            )
        except Exception:  # noqa: BLE001
            pass
    _wire(
        "update_subscription",
        UpdateSubscriptionUseCase,
        "subscription_repository",
        "category_repository",
    )
    if container.update_subscription is not None:
        try:
            container.update_subscription._audit = (  # type: ignore[attr-defined]
                container.subscription_audit_repository
            )
            container.update_subscription._session_factory = (  # type: ignore[attr-defined]
                session_factory
            )
        except Exception:  # noqa: BLE001
            pass
    _wire("delete_subscription", DeleteSubscriptionUseCase, "subscription_repository")
    _wire("list_subscriptions", ListSubscriptionsUseCase, "subscription_repository")
    _wire("get_subscription", GetSubscriptionUseCase, "subscription_repository")
    _wire("pause_subscription", PauseSubscriptionUseCase, "subscription_repository")
    if container.pause_subscription is not None:
        try:
            container.pause_subscription._audit = (  # type: ignore[attr-defined]
                container.subscription_audit_repository
            )
            container.pause_subscription._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire("resume_subscription", ResumeSubscriptionUseCase, "subscription_repository")
    if container.resume_subscription is not None:
        try:
            container.resume_subscription._audit = (  # type: ignore[attr-defined]
                container.subscription_audit_repository
            )
            container.resume_subscription._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire(
        "process_due_subscriptions",
        ProcessDueSubscriptionsUseCase,
        "subscription_repository",
        "account_repository",
        "settings_repository",
        "add_transaction",
        "currency_repository",
        "category_repository",
    )
    if container.process_due_subscriptions is not None:
        try:
            container.process_due_subscriptions._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire(
        "charge_subscription_now",
        ChargeSubscriptionNowUseCase,
        "subscription_repository",
        "account_repository",
        "add_transaction",
        "currency_repository",
        "settings_repository",
        "category_repository",
    )
    if container.charge_subscription_now is not None:
        try:
            container.charge_subscription_now._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire(
        "delete_subscription_charge",
        DeleteSubscriptionChargeUseCase,
        "transaction_repository",
        "subscription_repository",
        "delete_transaction",
    )
    if container.delete_subscription_charge is not None:
        try:
            container.delete_subscription_charge._audit = (  # type: ignore[attr-defined]
                container.subscription_audit_repository
            )
            container.delete_subscription_charge._session_factory = (  # type: ignore[attr-defined]
                session_factory
            )
        except Exception:  # noqa: BLE001
            pass
    _wire(
        "get_subscription_analytics",
        GetSubscriptionAnalyticsUseCase,
        "subscription_repository",
        "transaction_repository",
        "currency_repository",
    )
    _wire(
        "skip_subscription_period",
        SkipSubscriptionPeriodUseCase,
        "subscription_repository",
    )
    _wire(
        "duplicate_subscription",
        DuplicateSubscriptionUseCase,
        "subscription_repository",
        "category_repository",
    )
    _wire("cancel_subscription", CancelSubscriptionUseCase, "subscription_repository")
    _wire(
        "get_subscription_charge_series",
        GetSubscriptionChargeSeriesUseCase,
        "transaction_repository",
    )
    _wire(
        "append_subscription_audit",
        AppendSubscriptionAuditUseCase,
        "subscription_audit_repository",
    )
    _wire(
        "list_subscription_audit",
        ListSubscriptionAuditUseCase,
        "subscription_audit_repository",
    )

    # Currencies: provider is optional for UpdateExchangeRatesUseCase
    if container.currency_repository is not None:
        container.update_exchange_rates = UpdateExchangeRatesUseCase(
            container.currency_repository,
            provider=container.exchange_rate_provider,
        )
        container.convert_currency = ConvertCurrencyUseCase(
            container.currency_repository
        )
        container.list_currencies = ListCurrenciesUseCase(
            container.currency_repository
        )
        from lib.domain.use_cases.currencies import SeedCurrenciesUseCase

        container.seed_currencies = SeedCurrenciesUseCase(
            container.currency_repository
        )
    else:
        for name in (
            "update_exchange_rates",
            "convert_currency",
            "list_currencies",
            "seed_currencies",
        ):
            container.missing.append(name)
            container.errors[name] = "missing dependency: currency_repository"

    _wire("get_settings", GetSettingsUseCase, "settings_repository")
    _wire("update_settings", UpdateSettingsUseCase, "settings_repository")
    _wire("get_pin_credentials", GetPinCredentialsUseCase, "settings_repository")
    _wire("set_pin_credentials", SetPinCredentialsUseCase, "settings_repository")
    _wire("clear_pin_credentials", ClearPinCredentialsUseCase, "settings_repository")

    _wire("list_categories", ListCategoriesUseCase, "category_repository")
    _wire("create_category", CreateCategoryUseCase, "category_repository")
    if container.category_repository is not None:
        container.update_category = UpdateCategoryUseCase(
            container.category_repository,
            budgets=container.budget_repository,
            transactions=container.transaction_repository,
        )
        container.delete_category = DeleteCategoryUseCase(
            container.category_repository,
            budgets=container.budget_repository,
        )
    else:
        for name in ("update_category", "delete_category"):
            container.missing.append(name)
            container.errors[name] = "missing dependency: category_repository"
    _wire(
        "find_or_create_category",
        FindOrCreateCategoryUseCase,
        "category_repository",
    )

    _wire(
        "set_budget",
        SetBudgetUseCase,
        "budget_repository",
        "category_repository",
        "transaction_repository",
        "currency_repository",
        "settings_repository",
        "account_repository",
    )
    _wire("delete_budget", DeleteBudgetUseCase, "budget_repository")
    _wire("get_budget_progress", GetBudgetProgressUseCase, "budget_repository")
    _wire("get_budgets_for_month", GetBudgetsForMonthUseCase, "budget_repository")
    _wire(
        "recalculate_budget_spent",
        RecalculateBudgetSpentUseCase,
        "budget_repository",
        "transaction_repository",
        "currency_repository",
        "settings_repository",
        "account_repository",
    )
    _wire(
        "suggest_budget_limit",
        SuggestBudgetLimitUseCase,
        "transaction_repository",
        "currency_repository",
        "settings_repository",
    )
    _wire(
        "suggest_subscription_budgets",
        SuggestSubscriptionBudgetsUseCase,
        "subscription_repository",
        "budget_repository",
        "currency_repository",
        "settings_repository",
    )
    _wire("get_budget_analytics", GetBudgetAnalyticsUseCase, "budget_repository")
    if container.set_budget is not None and container.budget_repository is not None:
        try:
            container.copy_budgets_from_previous = CopyBudgetsFromPreviousMonthUseCase(
                container.budget_repository,
                container.set_budget,
            )
        except Exception as exc:  # pragma: no cover
            container.missing.append("copy_budgets_from_previous")
            container.errors["copy_budgets_from_previous"] = f"construct failed: {exc}"

    _wire("create_recurring_rule", CreateRecurringRuleUseCase, "recurring_rule_repository")
    _wire("update_recurring_rule", UpdateRecurringRuleUseCase, "recurring_rule_repository")
    _wire("delete_recurring_rule", DeleteRecurringRuleUseCase, "recurring_rule_repository")
    _wire("list_recurring_rules", ListRecurringRulesUseCase, "recurring_rule_repository")
    _wire("pause_recurring_rule", PauseRecurringRuleUseCase, "recurring_rule_repository")
    _wire(
        "skip_recurring_occurrence",
        SkipRecurringOccurrenceUseCase,
        "recurring_rule_repository",
    )
    _wire(
        "process_due_recurring",
        ProcessDueRecurringRulesUseCase,
        "recurring_rule_repository",
        "account_repository",
        "add_transaction",
    )
    if container.process_due_recurring is not None:
        try:
            container.process_due_recurring._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    container.preview_csv_import = PreviewCsvImportUseCase()
    _wire(
        "commit_csv_import",
        CommitCsvImportUseCase,
        "add_transaction",
        "account_repository",
    )
    if container.commit_csv_import is not None:
        try:
            container.commit_csv_import._session_factory = session_factory  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _wire(
        "record_net_worth_snapshot",
        RecordNetWorthSnapshotUseCase,
        "net_worth_repository",
        "account_repository",
        "currency_repository",
        "settings_repository",
    )
    _wire("list_net_worth_snapshots", ListNetWorthSnapshotsUseCase, "net_worth_repository")

    async def _snapshot_net_worth() -> None:
        uc = container.record_net_worth_snapshot
        if uc is None:
            return
        await uc.execute()

    for _name in ("add_transaction", "update_transaction", "delete_transaction"):
        _uc = getattr(container, _name, None)
        if _uc is not None:
            try:
                _uc._after_commit = _snapshot_net_worth  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

    _wire(
        "export_data",
        ExportDataUseCase,
        "account_repository",
        "transaction_repository",
        "goal_repository",
        "debt_repository",
        "subscription_repository",
        "currency_repository",
        "settings_repository",
        "category_repository",
        "budget_repository",
    )

    if (
        container.add_transaction is not None
        and container.delete_transaction is not None
        and container.account_repository is not None
        and container.currency_repository is not None
    ):
        try:
            container.transfer_between_accounts = TransferAccountsUseCase(
                container.add_transaction,
                container.delete_transaction,
                container.account_repository,
                container.currency_repository,
                container.find_or_create_category,
                session_factory,
            )
        except Exception as exc:  # pragma: no cover
            container.missing.append("transfer_between_accounts")
            container.errors["transfer_between_accounts"] = f"construct failed: {exc}"
    else:
        container.missing.append("transfer_between_accounts")
        container.errors["transfer_between_accounts"] = "missing transfer dependencies"

    if container.missing:
        logger.info(
            "Container built with %d missing dependencies: %s",
            len(container.missing),
            ", ".join(container.missing),
        )
    else:
        logger.info("Container built successfully (all dependencies wired)")

    return container
