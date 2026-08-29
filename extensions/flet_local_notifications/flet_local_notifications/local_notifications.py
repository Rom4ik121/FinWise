"""FinanseLocalNotifications — OS local notifications via flutter_local_notifications."""

from __future__ import annotations

from typing import Any

import flet as ft

__all__ = ["FinanseLocalNotifications"]


@ft.control("FinanseLocalNotifications")
class FinanseLocalNotifications(ft.Service):
    """Non-visual service for permission, show, and schedule."""

    async def request_permissions(self) -> bool:
        return bool(await self._invoke_method("request_permissions"))

    async def are_notifications_enabled(self) -> bool:
        return bool(await self._invoke_method("are_notifications_enabled"))

    async def show_notification(
        self,
        notification_id: int,
        title: str,
        body: str,
        **kwargs: Any,
    ) -> bool:
        payload = {
            "id": int(notification_id),
            "title": title or "",
            "body": body or "",
            "channel_id": kwargs.get("channel_id") or "finwise_reminders",
            "channel_name": kwargs.get("channel_name") or "FinWise reminders",
        }
        return bool(await self._invoke_method("show_notification", payload))

    async def schedule_notification(
        self,
        notification_id: int,
        title: str,
        body: str,
        *,
        when_iso: str,
        channel_id: str = "finwise_reminders",
        channel_name: str = "FinWise reminders",
    ) -> bool:
        return bool(
            await self._invoke_method(
                "schedule_notification",
                {
                    "id": int(notification_id),
                    "title": title or "",
                    "body": body or "",
                    "when_iso": when_iso,
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                },
            )
        )

    async def haptic(self, kind: str = "light") -> bool:
        return bool(await self._invoke_method("haptic", {"kind": kind or "light"}))

    async def cancel_notification(self, notification_id: int) -> bool:
        return bool(
            await self._invoke_method("cancel_notification", {"id": int(notification_id)})
        )

    async def cancel_all(self) -> bool:
        return bool(await self._invoke_method("cancel_all"))
