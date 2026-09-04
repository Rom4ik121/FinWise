"""Abstract settings repository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from lib.domain.entities.settings import AppSettings


class SettingsRepository(ABC):
    """Persistence port for :class:`~lib.domain.entities.settings.AppSettings`."""

    @abstractmethod
    async def get(self) -> AppSettings:
        """Return current settings, creating defaults if absent."""

    @abstractmethod
    async def update(self, settings: AppSettings) -> AppSettings:
        """Persist updated settings."""

    @abstractmethod
    async def get_pin_credentials(self) -> tuple[Optional[str], Optional[str], bool]:
        """Return ``(pin_hash, pin_salt, biometric_enabled)``."""

    @abstractmethod
    async def set_pin_credentials(
        self,
        pin_hash: str,
        pin_salt: str,
        *,
        biometric_enabled: bool | None = None,
    ) -> None:
        """Store PIN hash/salt and optional biometric flag."""

    @abstractmethod
    async def clear_pin_credentials(self) -> None:
        """Remove PIN credentials and disable biometric unlock."""
