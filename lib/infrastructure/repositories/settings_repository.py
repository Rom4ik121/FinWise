"""SQLAlchemy settings repository."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from lib.core.config import DEFAULT_UI_STYLE
from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.settings import AppSettings
from lib.domain.repositories.settings_repository import SettingsRepository
from lib.infrastructure.db_models import SettingsModel
from lib.infrastructure.repositories._base import (
    SessionFactory,
    ensure_utc,
    in_unit_of_work,
    session_scope,
)

logger = logging.getLogger("finanse.infrastructure.repositories.settings")

DEFAULT_SETTINGS_ID = "default"


def _to_entity(model: SettingsModel) -> AppSettings:
    threshold = (
        float(model.low_balance_threshold)
        if model.low_balance_threshold is not None
        else None
    )
    return AppSettings(
        id=model.id,
        default_currency=normalize_currency_code(model.default_currency),
        theme=model.theme,
        ui_style=getattr(model, "ui_style", None) or DEFAULT_UI_STYLE,
        language=model.language,
        language_user_set=bool(getattr(model, "language_user_set", False)),
        exchange_update_interval_minutes=model.exchange_update_interval_minutes,
        notifications_enabled=model.notifications_enabled,
        subscription_reminders=model.subscription_reminders,
        debt_reminders=model.debt_reminders,
        goal_milestones=model.goal_milestones,
        budget_alerts=bool(getattr(model, "budget_alerts", True)),
        low_balance_threshold=threshold,
        reminder_time=getattr(model, "reminder_time", None) or "09:00",
        reminder_days=int(getattr(model, "reminder_days", None) or 3),
        check_balance_before_subscription=bool(
            getattr(model, "check_balance_before_subscription", True)
        ),
        biometric_enabled=bool(getattr(model, "biometric_enabled", False)),
        dashboard_hide_chart=bool(getattr(model, "dashboard_hide_chart", False)),
        dashboard_chart_days=int(getattr(model, "dashboard_chart_days", None) or 30),
        completed_onboarding=bool(getattr(model, "completed_onboarding", False)),
        completed_tour_debts=bool(getattr(model, "completed_tour_debts", False)),
        completed_tour_analytics=bool(getattr(model, "completed_tour_analytics", False)),
        completed_tour_goals=bool(getattr(model, "completed_tour_goals", False)),
        tx_filters_json=getattr(model, "tx_filters_json", None) or None,
        budget_warn_pct=int(getattr(model, "budget_warn_pct", None) or 80),
        budget_limit_pct=int(getattr(model, "budget_limit_pct", None) or 100),
        updated_at=ensure_utc(model.updated_at) or datetime.now(timezone.utc),
    )


def _apply_entity(model: SettingsModel, entity: AppSettings) -> None:
    model.id = entity.id or DEFAULT_SETTINGS_ID
    model.default_currency = normalize_currency_code(entity.default_currency)
    model.theme = entity.theme
    model.ui_style = entity.ui_style
    model.language = entity.language
    model.language_user_set = bool(getattr(entity, "language_user_set", False))
    model.exchange_update_interval_minutes = entity.exchange_update_interval_minutes
    model.notifications_enabled = entity.notifications_enabled
    model.subscription_reminders = entity.subscription_reminders
    model.debt_reminders = entity.debt_reminders
    model.goal_milestones = entity.goal_milestones
    model.budget_alerts = bool(getattr(entity, "budget_alerts", True))
    model.low_balance_threshold = entity.low_balance_threshold
    model.reminder_time = entity.reminder_time
    model.reminder_days = int(entity.reminder_days or 3)
    model.check_balance_before_subscription = bool(
        entity.check_balance_before_subscription
    )
    model.biometric_enabled = entity.biometric_enabled
    model.dashboard_hide_chart = bool(getattr(entity, "dashboard_hide_chart", False))
    model.dashboard_chart_days = int(getattr(entity, "dashboard_chart_days", 30) or 30)
    model.completed_onboarding = bool(getattr(entity, "completed_onboarding", False))
    model.completed_tour_debts = bool(getattr(entity, "completed_tour_debts", False))
    model.completed_tour_analytics = bool(getattr(entity, "completed_tour_analytics", False))
    model.completed_tour_goals = bool(getattr(entity, "completed_tour_goals", False))
    model.tx_filters_json = (entity.tx_filters_json or None)
    model.budget_warn_pct = int(getattr(entity, "budget_warn_pct", 80) or 80)
    model.budget_limit_pct = int(getattr(entity, "budget_limit_pct", 100) or 100)
    model.updated_at = ensure_utc(entity.updated_at) or datetime.now(timezone.utc)


class SqlAlchemySettingsRepository(SettingsRepository):
    """Settings persistence via SQLAlchemy sync session + ``asyncio.to_thread``."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def get(self) -> AppSettings:
        if in_unit_of_work():
            return self._get_or_create_sync()
        return await asyncio.to_thread(self._get_or_create_sync)

    async def update(self, settings: AppSettings) -> AppSettings:
        if in_unit_of_work():
            return self._update_sync(settings)
        return await asyncio.to_thread(self._update_sync, settings)

    async def set_pin_credentials(
        self, pin_hash: str, pin_salt: str, *, biometric_enabled: bool | None = None
    ) -> None:
        """Store PIN hash/salt (and optional biometric flag) on the settings row."""
        if in_unit_of_work():
            self._set_pin_credentials_sync(pin_hash, pin_salt, biometric_enabled)
            return
        await asyncio.to_thread(
            self._set_pin_credentials_sync, pin_hash, pin_salt, biometric_enabled
        )

    async def get_pin_credentials(self) -> tuple[Optional[str], Optional[str], bool]:
        """Return ``(pin_hash, pin_salt, biometric_enabled)``."""
        if in_unit_of_work():
            return self._get_pin_credentials_sync()
        return await asyncio.to_thread(self._get_pin_credentials_sync)

    def _get_or_create_sync(self) -> AppSettings:
        with session_scope(self._session_factory) as session:
            model = session.get(SettingsModel, DEFAULT_SETTINGS_ID)
            if model is None:
                from lib.infrastructure.services.locale_prefs import (
                    detect_language_and_currency,
                )

                lang, currency = detect_language_and_currency()
                entity = AppSettings(
                    id=DEFAULT_SETTINGS_ID,
                    language=lang,
                    default_currency=currency,
                    language_user_set=False,
                    # Legacy tour flags — feature removed; mark done so old DBs stay quiet.
                    completed_onboarding=True,
                    completed_tour_debts=True,
                    completed_tour_analytics=True,
                    completed_tour_goals=True,
                )
                model = SettingsModel(id=DEFAULT_SETTINGS_ID)
                _apply_entity(model, entity)
                session.add(model)
                session.flush()
                logger.info(
                    "Created default settings row (language=%s currency=%s)",
                    lang,
                    currency,
                )
            return _to_entity(model)

    def _update_sync(self, entity: AppSettings) -> AppSettings:
        with session_scope(self._session_factory) as session:
            settings_id = entity.id or DEFAULT_SETTINGS_ID
            model = session.get(SettingsModel, settings_id)
            if model is None:
                model = SettingsModel(id=settings_id)
                session.add(model)
            _apply_entity(model, entity)
            model.updated_at = datetime.now(timezone.utc)
            session.flush()
            logger.debug("Updated settings %s", model.id)
            return _to_entity(model)

    def _set_pin_credentials_sync(
        self,
        pin_hash: str,
        pin_salt: str,
        biometric_enabled: bool | None,
    ) -> None:
        with session_scope(self._session_factory) as session:
            model = session.get(SettingsModel, DEFAULT_SETTINGS_ID)
            if model is None:
                model = SettingsModel(id=DEFAULT_SETTINGS_ID)
                session.add(model)
            model.pin_hash = pin_hash
            model.pin_salt = pin_salt
            if biometric_enabled is not None:
                model.biometric_enabled = biometric_enabled
            model.updated_at = datetime.now(timezone.utc)
            session.flush()

    def _get_pin_credentials_sync(self) -> tuple[Optional[str], Optional[str], bool]:
        with session_scope(self._session_factory) as session:
            model = session.get(SettingsModel, DEFAULT_SETTINGS_ID)
            if model is None:
                return None, None, False
            return model.pin_hash, model.pin_salt, bool(model.biometric_enabled)

    async def clear_pin_credentials(self) -> None:
        """Remove stored PIN hash/salt."""
        await asyncio.to_thread(self._clear_pin_credentials_sync)

    def _clear_pin_credentials_sync(self) -> None:
        with session_scope(self._session_factory) as session:
            model = session.get(SettingsModel, DEFAULT_SETTINGS_ID)
            if model is None:
                return
            model.pin_hash = None
            model.pin_salt = None
            # Biometric unlock requires a PIN; clear the flag together.
            model.biometric_enabled = False
            model.updated_at = datetime.now(timezone.utc)
            session.flush()
