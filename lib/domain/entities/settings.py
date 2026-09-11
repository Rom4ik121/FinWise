"""Application settings domain model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lib.core.config import (
    DEFAULT_CURRENCY,
    DEFAULT_EXCHANGE_UPDATE_INTERVAL_MINUTES,
    DEFAULT_LANGUAGE,
    DEFAULT_THEME,
    DEFAULT_UI_STYLE,
    KNOWN_UI_STYLES,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AppSettings(BaseModel):
    """Persisted user preferences for the application."""

    model_config = ConfigDict(from_attributes=True)

    id: str = "default"
    default_currency: str = DEFAULT_CURRENCY
    theme: str = DEFAULT_THEME
    ui_style: str = DEFAULT_UI_STYLE
    language: str = DEFAULT_LANGUAGE
    language_user_set: bool = False
    exchange_update_interval_minutes: int = DEFAULT_EXCHANGE_UPDATE_INTERVAL_MINUTES
    notifications_enabled: bool = True
    subscription_reminders: bool = True
    debt_reminders: bool = True
    goal_milestones: bool = True
    budget_alerts: bool = True
    low_balance_threshold: Optional[float] = None
    reminder_time: str = "09:00"  # local HH:MM for daily reminder sweep
    reminder_days: int = 3  # days before subscription billing to remind
    check_balance_before_subscription: bool = True
    biometric_enabled: bool = False
    # Home chart preferences (persisted across restarts).
    dashboard_hide_chart: bool = False
    dashboard_chart_days: int = 30
    # Legacy tour flags (feature removed; kept for DB column compatibility).
    completed_onboarding: bool = True
    completed_tour_debts: bool = True
    completed_tour_analytics: bool = True
    completed_tour_goals: bool = True
    # Last Transactions search/filter sheet (JSON). Cheap session restore.
    tx_filters_json: Optional[str] = None
    # Budget alert thresholds (percent of the monthly limit).
    budget_warn_pct: int = 80
    budget_limit_pct: int = 100
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("reminder_days")
    @classmethod
    def _validate_reminder_days(cls, value: int) -> int:
        days = int(value)
        if days < 0 or days > 365:
            raise ValueError("Reminder days must be between 0 and 365")
        return days

    @field_validator("reminder_time")
    @classmethod
    def _validate_reminder_time(cls, value: str) -> str:
        text = (value or "09:00").strip()
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError("Reminder time is invalid")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Reminder time is invalid")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("default_currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("ui_style", mode="before")
    @classmethod
    def _normalize_ui_style(cls, value: object) -> str:
        key = str(value or DEFAULT_UI_STYLE).strip().lower()
        if key in KNOWN_UI_STYLES:
            return key
        return DEFAULT_UI_STYLE

    @field_validator("dashboard_chart_days")
    @classmethod
    def _validate_chart_days(cls, value: int) -> int:
        days = int(value or 30)
        if days not in (7, 30, 90, 365):
            return 30
        return days

    @field_validator("budget_warn_pct", mode="before")
    @classmethod
    def _validate_budget_warn(cls, value: object) -> int:
        try:
            pct = int(value if value is not None else 80)
        except (TypeError, ValueError):
            return 80
        return max(1, min(99, pct))

    @field_validator("budget_limit_pct", mode="before")
    @classmethod
    def _validate_budget_limit(cls, value: object) -> int:
        try:
            pct = int(value if value is not None else 100)
        except (TypeError, ValueError):
            return 100
        return max(1, min(200, pct))

    @field_validator("updated_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime")
