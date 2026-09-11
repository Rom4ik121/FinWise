"""Currencies and exchange rates page with pair converter."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

import flet as ft

from lib.domain.entities.currency import Currency, ExchangeRate
from lib.domain.entities.currency_codes import normalize_currency_code
from lib.presentation.layout import make_v_scroll
from lib.presentation.components.layout.page_shell import page_column, page_frame
from lib.presentation.money_input import make_amount_field, parse_amount_field
from lib.presentation.styles import card_surface, muted_text
from lib.presentation.responsive import MIN_TAP, card_padding
from lib.presentation.utils import (
    format_money,
    run_async,
    safe_convert,
    safe_update,
    snack,
    snack_exception,
    tr,
)
from lib.presentation.widgets.currency_ticker_picker import CurrencyTickerPicker
from lib.presentation.widgets.empty_state import EmptyState
from lib.presentation.widgets.loading import loading_indicator

if TYPE_CHECKING:
    from lib.presentation.state.app_state import AppState


def _format_rate(value: Decimal) -> str:
    """Readable rate: trim trailing zeros, keep meaningful precision."""
    quantized = value.normalize()
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _money_figure_and_code(amount: Decimal, currency: str) -> tuple[str, str]:
    """Full converted amount plus ticker — never abbreviated to K/M."""
    text = format_money(amount, currency)
    figure, sep, code = text.rpartition(" ")
    if not sep:
        return text, ""
    return figure, code


def _result_size(figure: str) -> int:
    """Keep the converted figure readable on narrow screens."""
    n = len(figure)
    if n >= 16:
        return 16
    if n >= 12:
        return 19
    return 22


def _rates_with_usd_cross(
    base_rates: list,
    usd_rates: list,
    base: str,
) -> list:
    """Fill missing ``base→quote`` rows via the USD book (e.g. UZS→BTC)."""
    base_code = str(base).upper()
    merged = list(base_rates)
    by_quote = {
        str(getattr(rate, "quote", "")).upper(): rate
        for rate in merged
        if getattr(rate, "quote", None)
    }
    usd_per_base: Optional[Decimal] = None
    usd_row = by_quote.get("USD")
    if usd_row is not None and getattr(usd_row, "rate", None):
        usd_per_base = Decimal(str(usd_row.rate))
    if usd_per_base is None:
        inverse = next(
            (
                rate
                for rate in usd_rates
                if str(getattr(rate, "quote", "")).upper() == base_code
                and getattr(rate, "rate", None)
            ),
            None,
        )
        if inverse is not None and inverse.rate:
            usd_per_base = Decimal("1") / Decimal(str(inverse.rate))
    if usd_per_base is None or usd_per_base <= 0:
        return merged

    for usd_row in usd_rates:
        quote = str(getattr(usd_row, "quote", "")).upper()
        if not quote or quote == base_code or quote in by_quote:
            continue
        quote_rate = getattr(usd_row, "rate", None)
        if not quote_rate:
            continue
        derived = usd_per_base * Decimal(str(quote_rate))
        if derived <= 0:
            continue
        merged.append(
            ExchangeRate(
                base=base_code,
                quote=quote,
                rate=derived,
                updated_at=usd_row.updated_at,
            )
        )
        by_quote[quote] = merged[-1]
    return merged


def _matches_query(currency: Currency, query: str) -> bool:
    """Match ticker, name, or symbol (case-insensitive)."""
    if not query:
        return True
    q = query.strip().casefold()
    haystacks = (
        currency.code.casefold(),
        (currency.name or "").casefold(),
        (currency.symbol or "").casefold(),
    )
    return any(q in item for item in haystacks if item)


class CurrenciesPage(ft.Column):
    """Show fiat/crypto rates plus an interactive pair converter."""

    def __init__(self, page: ft.Page, state: "AppState") -> None:
        self._page = page
        self._state = state
        self._currencies: list[Currency] = []
        self._rate_map: dict[str, object] = {}
        self._convert_gen = 0

        lang = state.language
        base = state.base_currency
        default_quote = "USD" if base != "USD" else "EUR"

        self._amount = make_amount_field(
            lang,
            label=tr("currencies.amount", lang),
            value="1",
            extra_on_change=lambda _e: run_async(page, self._recalculate),
            expand=True,
            dense=True,
            border_radius=14,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
        )
        self._amount.on_submit = lambda _e: run_async(page, self._recalculate)
        from lib.presentation.form_keyboard import wire_field_chain

        wire_field_chain(page, [self._amount])
        self._from_picker = CurrencyTickerPicker(
            page,
            lang=lang,
            label=tr("currencies.from", lang),
            value=base,
            include_crypto=True,
            code_only=True,
            on_changed=lambda _code: run_async(page, self._recalculate),
        )
        self._to_picker = CurrencyTickerPicker(
            page,
            lang=lang,
            label=tr("currencies.to", lang),
            value=default_quote,
            include_crypto=True,
            code_only=True,
            on_changed=lambda _code: run_async(page, self._recalculate),
        )
        self._result_figure = ft.Text(
            "—",
            size=22,
            weight=ft.FontWeight.W_800,
            color=ft.Colors.PRIMARY,
            selectable=True,
            no_wrap=False,
            max_lines=2,
            overflow=ft.TextOverflow.VISIBLE,
        )
        self._result_code = ft.Text(
            "",
            size=12,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=False,
        )
        self._rate_line = ft.Text(
            "",
            size=10,
            color=ft.Colors.ON_SURFACE_VARIANT,
            max_lines=2,
            no_wrap=False,
            visible=False,
        )
        self._result_hint = ft.Text(
            "",
            size=10,
            color=ft.Colors.ERROR,
            max_lines=2,
            no_wrap=False,
            visible=False,
        )

        self._list_search = ft.TextField(
            label=tr("currencies.search", lang),
            hint_text=tr("currencies.search_hint", lang),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.SURFACE,
            on_change=lambda _e: self._render_lists(),
            on_submit=lambda _e: self._apply_search_to_converter(),
        )
        from lib.presentation.form_keyboard import configure_field, wire_field_chain

        configure_field(self._list_search, "search")
        wire_field_chain(page, [self._list_search])
        self._base_caption = muted_text("", size=11)
        self._converter = self._build_converter_card(lang)
        self._rates_host = ft.Column(spacing=0, tight=True)
        self._body = make_v_scroll(spacing=8)
        self._body.controls = [
            self._converter,
            self._list_search,
            self._base_caption,
            self._rates_host,
        ]
        super().__init__(
            **page_column(
                page_frame(
                    title=tr("nav.currencies", lang),
                    body=self._body,
                    page=page,
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        on_click=lambda _e: state.close_secondary(),
                    ),
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.SYNC,
                            icon_color=ft.Colors.PRIMARY,
                            tooltip=tr("currencies.refresh", lang),
                            on_click=lambda _e: run_async(page, self.refresh_rates),
                        ),
                    ],
                ),
                page=page,
            )
        )
        run_async(page, self.reload)

    def _build_converter_card(self, lang: str) -> ft.Control:
        swap_btn = ft.Container(
            width=MIN_TAP,
            height=MIN_TAP,
            border_radius=12,
            alignment=ft.Alignment.CENTER,
            ink=True,
            tooltip=tr("currencies.swap", lang),
            on_click=lambda _e: run_async(self._page, self._swap_pair),
            content=ft.Icon(
                ft.Icons.SWAP_HORIZ_ROUNDED,
                size=22,
                color=ft.Colors.PRIMARY,
            ),
        )
        result_box = ft.Container(
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                expand=True,
                                content=self._result_figure,
                            ),
                            self._result_code,
                        ],
                    ),
                    self._rate_line,
                    self._result_hint,
                ],
            ),
        )
        return card_surface(
            ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    self._amount,
                    ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self._from_picker,
                            swap_btn,
                            self._to_picker,
                        ],
                    ),
                    result_box,
                ],
            ),
            padding=card_padding(self._page, hero=True),
        )

    def _set_result(
        self,
        *,
        figure: str = "—",
        code: str = "",
        forward: str = "",
        reverse: str = "",
        error: str = "",
    ) -> None:
        from lib.presentation.responsive import scale_font

        self._result_figure.value = figure
        base_size = _result_size(figure) if figure and figure != "—" else 22
        self._result_figure.size = scale_font(base_size, self._page, minimum=14, maximum=28)
        self._result_code.value = code
        self._result_code.visible = bool(code)
        if forward and reverse:
            rate = f"{forward}  ·  {reverse}"
        else:
            rate = forward or reverse
        self._rate_line.value = rate
        self._rate_line.visible = bool(rate)
        self._result_hint.value = error
        self._result_hint.visible = bool(error)
        self._update_result()

    def _selected_pair(self) -> tuple[str, str]:
        src = normalize_currency_code(
            self._from_picker.value or self._state.base_currency
        )
        dst = normalize_currency_code(
            self._to_picker.value or ("USD" if src != "USD" else "EUR")
        )
        return src, dst

    def _parse_amount(self) -> Optional[Decimal]:
        try:
            value = parse_amount_field(self._amount)
        except (InvalidOperation, ValueError):
            return None
        if value < 0:
            return None
        return value

    def _search_query(self) -> str:
        return (self._list_search.value or "").strip()

    def _filtered_currencies(self) -> list[Currency]:
        query = self._search_query()
        return [c for c in self._currencies if _matches_query(c, query)]

    async def _swap_pair(self) -> None:
        src, dst = self._selected_pair()
        self._from_picker.set_value(dst, notify=False)
        self._to_picker.set_value(src, notify=False)
        await self._recalculate()

    async def _recalculate(self) -> None:
        self._convert_gen += 1
        gen = self._convert_gen
        lang = self._state.language
        try:
            amount = self._parse_amount()
            src, dst = self._selected_pair()
            if amount is None:
                if gen == self._convert_gen:
                    self._set_result(error=tr("invalid_amount", lang))
                return

            converted = await safe_convert(
                self._state.container, amount, src, dst
            )
            one_forward = await safe_convert(
                self._state.container, Decimal("1"), src, dst, quantize=False
            )
            one_reverse = await safe_convert(
                self._state.container, Decimal("1"), dst, src, quantize=False
            )
            if gen != self._convert_gen:
                return

            if converted is None or one_forward is None or one_reverse is None:
                self._set_result(error=tr("currencies.no_rate", lang))
            else:
                figure, code = _money_figure_and_code(converted, dst)
                self._set_result(
                    figure=figure,
                    code=code,
                    forward=tr(
                        "currencies.unit_rate",
                        lang,
                        src=src,
                        rate=_format_rate(one_forward),
                        dst=dst,
                    ),
                    reverse=tr(
                        "currencies.unit_rate",
                        lang,
                        src=dst,
                        rate=_format_rate(one_reverse),
                        dst=src,
                    ),
                )
        except Exception:  # noqa: BLE001
            if gen == self._convert_gen:
                self._set_result(error=tr("error.generic", lang))

    def _update_result(self) -> None:
        for control in (
            self._result_figure,
            self._result_code,
            self._rate_line,
            self._result_hint,
        ):
            try:
                safe_update(control)
            except Exception:  # noqa: BLE001
                pass

    def _tile(self, currency: Currency) -> ft.Control:
        code = currency.code
        rate = self._rate_map.get(code.upper())
        name = currency.name or ""
        trailing = "—"
        if rate is not None:
            trailing = _format_rate(Decimal(str(rate.rate)))  # type: ignore[attr-defined]
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=4, vertical=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            ink=True,
            on_click=lambda _e, c=code: run_async(self._page, self._use_as_quote, c),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(code, width=48, weight=ft.FontWeight.W_700, size=13),
                    ft.Text(
                        name,
                        expand=2,
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        max_lines=1,
                    ),
                    ft.Text(
                        trailing,
                        expand=3,
                        size=12,
                        weight=ft.FontWeight.W_600,
                        text_align=ft.TextAlign.RIGHT,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    def _section_label(self, text: str) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.only(top=10, bottom=4),
            content=ft.Text(
                text,
                size=13,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.PRIMARY,
            ),
        )

    def _render_lists(self) -> None:
        lang = self._state.language
        base = self._state.base_currency
        filtered = self._filtered_currencies()
        fiat = [c for c in filtered if not c.is_crypto]
        crypto = [c for c in filtered if c.is_crypto]
        self._base_caption.value = tr("currencies.base_rates", lang, base=base)

        rows: list[ft.Control] = []
        if fiat:
            rows.append(self._section_label(tr("currencies.fiat", lang)))
            rows.extend(self._tile(c) for c in fiat)
        if crypto:
            rows.append(self._section_label(tr("currencies.crypto", lang)))
            rows.extend(self._tile(c) for c in crypto)
        if not filtered and self._search_query():
            rows.append(
                EmptyState(tr("currencies.not_found", lang), icon=ft.Icons.SEARCH_OFF)
            )
        elif not filtered:
            rows.append(muted_text(tr("currencies.not_found", lang), size=12))
        self._rates_host.controls = rows
        try:
            safe_update(self._body)
        except Exception:  # noqa: BLE001
            pass

    def _apply_search_to_converter(self) -> None:
        """Enter in search: if exact ticker match, set it as quote currency."""
        query = normalize_currency_code(self._search_query())
        if not query:
            return
        match = next(
            (c for c in self._currencies if c.code.upper() == query),
            None,
        )
        if match is None:
            filtered = self._filtered_currencies()
            if len(filtered) == 1:
                match = filtered[0]
        if match is None:
            return
        run_async(self._page, self._use_as_quote, match.code)

    async def reload(self) -> None:
        """Load currencies and known rates vs base currency."""
        lang = self._state.language
        self._rates_host.controls = [loading_indicator()]
        try:
            safe_update(self._body)
        except Exception:  # noqa: BLE001
            pass

        base = self._state.base_currency
        try:
            currencies = await self._state.container.list_currencies.execute(
                include_crypto=True
            )
            self._currencies = list(currencies)
            repo = self._state.container.currency_repository
            rates = []
            if repo is not None and hasattr(repo, "list_rates"):
                rates = await repo.list_rates(base=base)
                usd_book = (
                    await repo.list_rates(base="USD")
                    if str(base).upper() != "USD"
                    else []
                )
                rates = _rates_with_usd_cross(rates, usd_book, base)
            elif repo is not None and hasattr(repo, "list_all_rates"):
                rates = await repo.list_all_rates()
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
            self._rates_host.controls = [EmptyState(tr("error.generic", lang))]
            try:
                safe_update(self._body)
            except Exception:  # noqa: BLE001
                pass
            return

        self._from_picker.set_currencies(self._currencies)
        self._to_picker.set_currencies(self._currencies)
        codes = {c.code.upper() for c in self._currencies}
        src, dst = self._selected_pair()
        if src not in codes and self._currencies:
            self._from_picker.set_value(self._currencies[0].code, notify=False)
            src = self._currencies[0].code.upper()
        if dst not in codes or dst == src:
            fallback = next((c for c in codes if c != src), src)
            self._to_picker.set_value(fallback, notify=False)

        rate_map: dict[str, object] = {}
        for rate in rates:
            quote = getattr(rate, "quote", None)
            if quote:
                rate_map[str(quote).upper()] = rate
        self._rate_map = rate_map

        self._render_lists()
        await self._recalculate()

    async def _use_as_quote(self, code: str) -> None:
        """Tap a rate row to set it as the converter target."""
        code = normalize_currency_code(code)
        src, _dst = self._selected_pair()
        if code == src:
            self._from_picker.set_value(self._to_picker.value or src, notify=False)
        self._to_picker.set_value(code, notify=False)
        await self._recalculate()

    async def refresh_rates(self) -> None:
        """Manually refresh exchange rates via use case."""
        lang = self._state.language
        try:
            await self._state.container.update_exchange_rates.execute(
                base=self._state.base_currency
            )
            from lib.presentation.utils import invalidate_rate_book_cache

            invalidate_rate_book_cache()
            self._state.bump_refresh(
                "dashboard", "accounts", "analytics", "transactions"
            )
            snack(self._page, tr("action.saved", lang))
        except Exception as exc:  # noqa: BLE001
            snack_exception(self._page, exc, lang=self._state.language)
        await self.reload()
