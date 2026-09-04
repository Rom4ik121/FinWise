"""Unit-of-work helpers shared by domain use cases (no SQLAlchemy types)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

logger = logging.getLogger("finanse.domain.unit_of_work")

# Opaque session object owned by infrastructure ``session_scope``.
_uow_session: ContextVar[Optional[Any]] = ContextVar(
    "finanse_uow_session", default=None
)


def get_uow_session() -> Optional[Any]:
    """Return the active unit-of-work session, if any."""
    return _uow_session.get()


def in_unit_of_work() -> bool:
    """True when an outer :func:`unit_of_work` owns the session."""
    return _uow_session.get() is not None


@contextmanager
def unit_of_work(session_factory: Callable[[], Any]) -> Iterator[Any]:
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
