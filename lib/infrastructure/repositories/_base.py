"""Shared helpers for SQLAlchemy repository implementations."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Generator, Optional, TypeVar

from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("finanse.infrastructure.repositories")

SessionFactory = Callable[[], Session] | sessionmaker[Session]

T = TypeVar("T")

_uow_session: ContextVar[Optional[Session]] = ContextVar("finanse_uow_session", default=None)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Normalize datetimes to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_uow_session() -> Optional[Session]:
    """Return the active unit-of-work session, if any."""
    return _uow_session.get()


@contextmanager
def unit_of_work(session_factory: SessionFactory) -> Iterator[Session]:
    """Run multiple repository calls in a single DB transaction.

    Nested ``session_scope`` calls reuse this session and do not commit until
    the outer ``unit_of_work`` exits. Call repositories on the **same thread**
    (skip ``asyncio.to_thread`` while active — see ``in_unit_of_work``).
    """
    if _uow_session.get() is not None:
        raise RuntimeError("Nested unit_of_work is not supported")
    session = session_factory()
    token = _uow_session.set(session)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Unit of work rolled back due to error")
        raise
    finally:
        _uow_session.reset(token)
        session.close()


def in_unit_of_work() -> bool:
    """True when an outer :func:`unit_of_work` owns the session."""
    return _uow_session.get() is not None


@contextmanager
def session_scope(session_factory: SessionFactory) -> Generator[Session, None, None]:
    """Provide a short-lived session with commit / rollback.

    When inside :func:`unit_of_work`, yields the shared session without
    committing (the outer UoW commits once).
    """
    existing = _uow_session.get()
    if existing is not None:
        yield existing
        return

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Database session rolled back due to error")
        raise
    finally:
        session.close()
