"""Goal change audit log entry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GoalAuditEntry(BaseModel):
    """One row in the goal audit trail."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    goal_id: str
    action: str
    details: Optional[dict[str, Any]] = None
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("created_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: object) -> object:
        if value is None:
            return _utc_now()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value
