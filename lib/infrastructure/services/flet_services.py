"""Attach Flet Service controls without putting them in the visual tree.

``page.add(service)`` makes Flutter try to build a widget. Custom services
only implement ``createService``, so the client shows
``Unknown control: …`` and the splash never finishes.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("finanse.infrastructure.services.flet_services")


def attach_page_service(
    page: Any,
    service: Any,
    *,
    native_extension: bool = True,
) -> bool:
    """Register ``service`` on ``page.services`` and keep a strong reference.

    Built-in Flet services (FilePicker, Share) must use
    ``native_extension=False`` so they still attach on ``flet run --android``
    web clients. Custom Dart extensions stay native-only: putting them on a
    web client paints ``Unknown control`` on the splash and the app never
    opens.
    """
    if page is None or service is None:
        return False
    if native_extension and getattr(page, "web", False):
        logger.info("Skip custom Flet service on web client")
        return False
    try:
        services = list(getattr(page, "services", None) or [])
        if any(type(item) is type(service) for item in services):
            return True
        services.append(service)
        page.services = services
        try:
            page.update()
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to attach Flet service %s", type(service).__name__)
        return False
