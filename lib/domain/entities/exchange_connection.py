"""Linked exchange / crypto-wallet API connection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeConnection(BaseModel):
    """API credentials and sync state for one FinWise account."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    provider: str
    credentials_encrypted: str = ""
    last_sync_at: Optional[datetime] = None
    last_error: str = ""
    holdings_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("last_sync_at", "created_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        raise TypeError("Expected datetime")
