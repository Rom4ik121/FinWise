"""Settings use cases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from lib.domain.entities.settings import AppSettings
from lib.domain.repositories.settings_repository import SettingsRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GetSettingsUseCase:
    """Load persisted application settings."""

    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    async def execute(self) -> AppSettings:
        """Return current settings (defaults created if missing)."""
        return await self._settings.get()


class UpdateSettingsUseCase:
    """Persist updated application settings."""

    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    async def execute(self, settings: AppSettings) -> AppSettings:
        """Save settings and stamp ``updated_at`` in UTC."""
        updated = settings.model_copy(update={"updated_at": _utc_now()})
        return await self._settings.update(updated)


class GetPinCredentialsUseCase:
    """Read stored PIN hash/salt and biometric flag."""

    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    async def execute(self) -> tuple[Optional[str], Optional[str], bool]:
        return await self._settings.get_pin_credentials()


class SetPinCredentialsUseCase:
    """Persist PIN credentials (and optional biometric flag)."""

    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    async def execute(
        self,
        pin_hash: str,
        pin_salt: str,
        *,
        biometric_enabled: bool | None = None,
    ) -> None:
        if not (pin_hash or "").strip() or not (pin_salt or "").strip():
            raise ValueError("PIN is required")
        await self._settings.set_pin_credentials(
            pin_hash.strip(),
            pin_salt.strip(),
            biometric_enabled=biometric_enabled,
        )


class ClearPinCredentialsUseCase:
    """Clear PIN lock and disable biometric; return refreshed settings."""

    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    async def execute(self) -> AppSettings:
        await self._settings.clear_pin_credentials()
        # Repo clears biometric_enabled on the row; reload so AppSettings matches.
        current = await self._settings.get()
        if current.biometric_enabled:
            current = await self._settings.update(
                current.model_copy(
                    update={
                        "biometric_enabled": False,
                        "updated_at": _utc_now(),
                    }
                )
            )
        return current
