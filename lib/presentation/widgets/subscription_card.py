"""Subscription list card."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from lib.domain.entities.subscription import Periodicity, Subscription, SubscriptionStatus
from lib.presentation.account_icons import account_icon_badge
from lib.presentation.components.layout.text import adaptive_text, money_label
from lib.presentation.responsive import entity_card_metrics
from lib.presentation.skins import get_active_skin
from lib.presentation.styles import alert_corner, card_surface, muted_text, style_popup_menu
from lib.presentation.utils import format_date


_STATUS_COLOR = {
    SubscriptionStatus.ACTIVE: ft.Colors.PRIMARY,
    SubscriptionStatus.PAUSED: ft.Colors.AMBER_700,
    SubscriptionStatus.EXPIRED: ft.Colors.ON_SURFACE_VARIANT,
    SubscriptionStatus.CANCELLED: ft.Colors.ERROR,
}


def periodicity_label(
    periodicity: Periodicity,
    language: str,
    *,
    custom_interval_days: int | None = None,
) -> str:
    from lib.presentation.utils import tr

    key = {
        Periodicity.DAILY: "subscription.daily",
        Periodicity.WEEKLY: "subscription.weekly",
        Periodicity.BIWEEKLY: "subscription.biweekly",
        Periodicity.MONTHLY: "subscription.monthly",
        Periodicity.QUARTERLY: "subscription.quarterly",
        Periodicity.SEMI_ANNUAL: "subscription.semi_annual",
        Periodicity.YEARLY: "subscription.yearly",
        Periodicity.CUSTOM: "subscription.custom",
    }.get(periodicity, "subscription.monthly")
    label = tr(key, language)
    if periodicity == Periodicity.CUSTOM and custom_interval_days:
        return f"{label} ({custom_interval_days}d)"
    return label


class SubscriptionCard(ft.Container):
    """Shows recurring charge details and next billing date."""

    def __init__(
        self,
        subscription: Subscription,
        *,
        language: str = "ru",
        alert: bool = False,
        sparkline: Optional[ft.Control] = None,
        on_open: Optional[Callable[[Subscription], None]] = None,
        on_edit: Optional[Callable[[Subscription], None]] = None,
        on_delete: Optional[Callable[[Subscription], None]] = None,
        page: ft.Page | None = None,
    ) -> None:
        from lib.presentation.utils import tr

        metrics = entity_card_metrics(page)
        period = periodicity_label(
            subscription.periodicity,
            language,
            custom_interval_days=subscription.custom_interval_days,
        )
        status = subscription.status
        status_label = tr(f"subscription.status.{status.value}", language)
        open_cb = on_open or on_edit
        icon_key = getattr(subscription, "icon", None) or "autorenew"
        icon_color = getattr(subscription, "color", None) or get_active_skin().primary_hex(
            dark=True
        )
        muted_parts = [period]
        if not subscription.auto_charge:
            muted_parts.append(tr("subscription.auto_charge_off", language))
        body_controls: list[ft.Control] = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    account_icon_badge(
                        icon_key,
                        color=icon_color,
                        size=metrics["icon"],
                        glyph_size=metrics["glyph"],
                    ),
                    adaptive_text(
                        subscription.name,
                        page=page,
                        size=16,
                        weight=ft.FontWeight.W_700,
                        expand=True,
                        max_lines=2,
                        minimum=13,
                        maximum=20,
                    ),
                    money_label(
                        subscription.amount,
                        subscription.currency,
                        page=page,
                        size=14,
                        color=icon_color,
                        compact=True,
                        text_align=ft.TextAlign.RIGHT,
                    ),
                    style_popup_menu(
                        ft.PopupMenuButton(
                            icon=ft.Icons.MORE_VERT,
                            icon_color=ft.Colors.ON_SURFACE_VARIANT,
                            items=[
                                ft.PopupMenuItem(
                                    content=ft.Text(tr("action.edit", language)),
                                    icon=ft.Icons.EDIT_OUTLINED,
                                    on_click=lambda _e: on_edit(subscription)
                                    if on_edit
                                    else None,
                                ),
                                ft.PopupMenuItem(
                                    content=ft.Text(tr("action.delete", language)),
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    on_click=lambda _e: on_delete(subscription)
                                    if on_delete
                                    else None,
                                ),
                            ],
                        )
                    ),
                ],
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=999,
                bgcolor=ft.Colors.with_opacity(
                    0.12, _STATUS_COLOR.get(status, ft.Colors.PRIMARY)
                ),
                content=ft.Text(
                    status_label,
                    size=metrics["chip"],
                    color=_STATUS_COLOR.get(status, ft.Colors.PRIMARY),
                    weight=ft.FontWeight.W_600,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1,
                ),
            ),
            muted_text(" · ".join(muted_parts), page=page),
            adaptive_text(
                tr(
                    "subscription.next_billing",
                    language,
                    date=format_date(subscription.next_billing_date),
                ),
                page=page,
                size=12,
                weight=ft.FontWeight.W_500,
                max_lines=2,
                minimum=10,
                maximum=15,
            ),
        ]
        if sparkline is not None:
            body_controls.append(sparkline)
        body = ft.Column(spacing=metrics["gap"], tight=True, controls=body_controls)
        card = card_surface(
            body,
            padding=metrics["padding"],
            ink=True,
            on_click=lambda _e: open_cb(subscription) if open_cb else None,
        )
        content: ft.Control = body
        if alert:
            content = ft.Stack(
                clip_behavior=ft.ClipBehavior.NONE,
                controls=[
                    body,
                    alert_corner(tooltip=tr("notify.subscription_due", language)),
                ],
            )
        super().__init__(
            padding=card.padding,
            border_radius=card.border_radius,
            bgcolor=card.bgcolor,
            border=card.border,
            shadow=card.shadow,
            opacity=1.0 if subscription.status == SubscriptionStatus.ACTIVE else 0.7,
            ink=True,
            on_click=card.on_click,
            animate=card.animate,
            content=content,
        )
