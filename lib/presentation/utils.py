"""Small presentation helpers shared across pages and widgets."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

import flet as ft

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.money import is_crypto_currency, money_quantum
from lib.infrastructure.services.localization import t

if TYPE_CHECKING:
    from lib.domain.services.rate_book import RateBook

logger = logging.getLogger("finanse.presentation.utils")

# Domain English / codes → i18n keys (never show raw programmer text).
_DOMAIN_ERROR_KEYS: dict[str, str] = {
    "insufficient_funds": "error.insufficient_funds",
    "Insufficient funds": "error.insufficient_funds",
    "Cannot transfer to the same account": "transfer.same_account",
    "No exchange rate for this currency pair": "transfer.no_rate",
    "Transfer amount must be positive": "invalid_amount",
    "Fee cannot be negative": "invalid_amount",
    "Transaction amount must be positive": "invalid_amount",
    "Line amount must be positive": "invalid_amount",
    "Transaction items must sum to a positive amount": "invalid_amount",
    "Category is required": "budgets.category_required",
    "Budget amount_limit must be positive": "budgets.limit_required",
    "Invalid encrypted export": "settings.restore_bad_file",
    "Transfer legs cannot be edited independently": "transfer.edit_hint",
    "error.exchange_unavailable": "error.exchange_unavailable",
    "error.generic": "error.generic",
    "error.insufficient_funds": "error.insufficient_funds",
    "error.network": "error.network",
    "error.no_accounts": "error.no_accounts",
}

_DOMAIN_ERROR_PREFIXES: tuple[tuple[str, str], ...] = (
    ("No exchange rate", "fx.missing_rates"),
    ("Account not found", "error.generic"),
    ("Transaction not found", "error.generic"),
    ("Goal not found", "error.generic"),
    ("Debt not found", "error.generic"),
    ("Subscription not found", "error.generic"),
    ("Category not found", "error.generic"),
    ("Budget not found", "error.generic"),
    ("Subscription cannot be charged", "error.generic"),
    ("Subscription charging is not configured", "error.generic"),
    ("budget_id or category_id", "error.generic"),
    ("Budget category must be", "budgets.category_required"),
    ("Exchange rate must be positive", "invalid_amount"),
    ("reminder_", "error.generic"),
)

_TECHNICAL_RE = re.compile(
    r"(traceback|file \"|site-packages|sqlalchemy|operationalerror|"
    r"integrityerror|attributeerror|typeerror|modulenotfound|"
    r"permissionerror|errno\s*\d|\\\w:\\|/users/|c:\\\\|"
    r"\.py:\d+|at 0x[0-9a-f]+)",
    re.IGNORECASE,
)


def tr(key: str, lang: str = "ru", *, default: str | None = None, **kwargs: Any) -> str:
    """Translate ``key`` for the given language with optional format kwargs."""
    text = t(key, lang, default=default)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def dropdown_select_kwargs(handler: Callable[..., Any]) -> dict[str, Any]:
    """Return the Flet ``Dropdown`` event kwarg for this installed version.

    Flet 0.86+ uses ``on_select``; 0.83–0.85 used ``on_change``.
    """
    try:
        params = inspect.signature(ft.Dropdown.__init__).parameters
    except (TypeError, ValueError):
        params = {}
    if "on_select" in params:
        return {"on_select": handler}
    return {"on_change": handler}


def bind_dropdown_select(dropdown: Any, handler: Callable[..., Any]) -> None:
    """Attach a selection handler using the event name this Flet build supports."""
    try:
        from lib.presentation.styles import polish_form_control

        polish_form_control(dropdown)
    except Exception:  # noqa: BLE001
        pass
    if hasattr(dropdown, "on_select"):
        dropdown.on_select = handler
        return
    dropdown.on_change = handler


def format_money(
    amount: Decimal | float | int | str,
    currency: str = "RUB",
    *,
    signed: bool = False,
) -> str:
    """Format a monetary amount for display (8 dp for known crypto)."""
    value = Decimal(str(amount))
    q = money_quantum(currency)
    quantized = value.quantize(q)
    prefix = ""
    if signed:
        if quantized > 0:
            prefix = "+"
        elif quantized < 0:
            prefix = "−"
            quantized = abs(quantized)
    if is_crypto_currency(currency):
        body = f"{quantized:,.8f}".rstrip("0").rstrip(".")
        if not body or body == "-":
            body = "0"
        return f"{prefix}{body.replace(',', ' ')} {currency}"
    return f"{prefix}{quantized:,.2f} {currency}".replace(",", " ")


def _trim_compact(body: str) -> str:
    return body.replace(".0M", "M").replace(".0K", "K").replace(".0B", "B")


def format_money_parts(
    amount: Decimal | float | int | str,
    currency: str = "RUB",
    *,
    signed: bool = False,
) -> tuple[str, str]:
    """Compact figure and currency code for dense UI (``−1.2M``, ``UZS``)."""
    value = Decimal(str(amount))
    quantized = value.quantize(Decimal("0.01"))
    prefix = ""
    if quantized < 0:
        prefix = "−"
        quantized = abs(quantized)
    elif signed and quantized > 0:
        prefix = "+"
    magnitude = float(quantized)
    if magnitude >= 1_000_000_000:
        body = _trim_compact(f"{magnitude / 1_000_000_000:.1f}B")
    elif magnitude >= 1_000_000:
        body = _trim_compact(f"{magnitude / 1_000_000:.1f}M")
    elif magnitude >= 1_000:
        body = _trim_compact(f"{magnitude / 1_000:.1f}K")
    elif quantized == quantized.to_integral_value():
        body = f"{int(quantized)}"
    else:
        body = f"{quantized:.2f}".rstrip("0").rstrip(".")
    return f"{prefix}{body}", currency


def format_money_compact(
    amount: Decimal | float | int | str,
    currency: str = "RUB",
    *,
    signed: bool = False,
) -> str:
    """Shorter money for narrow columns (KPI, chips, budget bars)."""
    figure, code = format_money_parts(amount, currency, signed=signed)
    return f"{figure} {code}"


def format_date(dt: datetime | None, *, with_time: bool = False) -> str:
    """Format a datetime in the user's local timezone."""
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    if with_time:
        return local.strftime("%d.%m.%Y %H:%M")
    return local.strftime("%d.%m.%Y")


def try_convert_amount(
    book: "RateBook",
    amount: Decimal | float | int | str,
    currency: str | None,
    base: str,
) -> Decimal | None:
    """Convert ``amount`` to ``base``, or ``None`` when the rate is missing."""
    value = Decimal(str(amount))
    src = normalize_currency_code(currency or base)
    dst = normalize_currency_code(base)
    if src == dst:
        return value
    return book.convert(value, src, dst)


def run_async(
    page: ft.Page,
    handler: Callable[..., Awaitable[Any]],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Schedule an async handler on the page event loop (Flet 0.83+)."""
    if hasattr(page, "run_task"):
        page.run_task(handler, *args, **kwargs)
        return
    asyncio.create_task(handler(*args, **kwargs))


def control_page(control: Any) -> Optional[Any]:
    """Page a control is mounted on, or None if it is not on a page yet.

    Flet 0.86+ raises ``RuntimeError`` on ``control.page`` when unmounted,
    so ``getattr(control, "page", None)`` is not safe.
    """
    try:
        return control.page
    except (RuntimeError, AttributeError):
        return None
    except Exception:  # noqa: BLE001
        return None


def safe_update(control: ft.Control) -> None:
    """Call ``control.update()`` only when the control is mounted."""
    if control_page(control) is None:
        return
    try:
        control.update()
    except Exception:  # noqa: BLE001
        pass


def _looks_technical(text: str) -> bool:
    """True for stack traces, SQL, paths, and other developer-only copy."""
    raw = (text or "").strip()
    if not raw:
        return True
    if len(raw) > 160:
        return True
    if _TECHNICAL_RE.search(raw):
        return True
    lower = raw.lower()
    if lower.startswith("error.") or lower.startswith("exception"):
        # bare "error.foo" keys are handled elsewhere; "Exception: ..." is tech
        if " " in raw or ":" in raw[6:]:
            return "exception" in lower or "error:" in lower
    return False


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


def user_facing_error(
    exc: BaseException | str | None,
    lang: str = "ru",
) -> str:
    """Translate domain failures; hide programmer diagnostics from the UI."""
    raw = str(exc).strip() if exc is not None else ""
    if not raw:
        return tr("error.generic", lang)

    mapped = _DOMAIN_ERROR_KEYS.get(raw)
    if mapped:
        return tr(mapped, lang)

    if raw.startswith(
        (
            "error.",
            "transfer.",
            "settings.",
            "fx.",
            "goal.",
            "budgets.",
            "invalid_",
            "debt.",
            "action.",
        )
    ):
        return tr(raw, lang)

    for prefix, key in _DOMAIN_ERROR_PREFIXES:
        if raw.startswith(prefix) or raw.lower().startswith(prefix.lower()):
            return tr(key, lang)

    lower = raw.lower()
    if "archived" in lower:
        return tr("goal.archived_block", lang)
    if "completed" in lower and ("goal" in lower or "cannot" in lower):
        return tr("goal.completed_block", lang)
    if "insufficient" in lower:
        return tr("error.insufficient_funds", lang)
    if (
        "not permitted" in lower
        or "errno 1" in lower
        or "clouddocs" in lower
        or "mobile documents" in lower
    ):
        return tr("settings.file_denied", lang)

    if _looks_technical(raw):
        return tr("error.generic", lang)

    # Unmapped English domain text → generic (never dump to end users).
    if not _has_cyrillic(raw) and re.search(r"[A-Za-z]", raw):
        return tr("error.generic", lang)

    if len(raw) > 120:
        return tr("error.generic", lang)
    return raw


def _sanitize_error_text(message: str, *, lang: str = "ru") -> str:
    """Drop technical leftovers that slipped into SnackBar text."""
    text = (message or "").strip()
    if not text:
        return tr("error.generic", lang)
    if _looks_technical(text):
        return tr("error.generic", lang)
    return text


def snack_exception(
    page: ft.Page,
    exc: BaseException | str | None,
    *,
    lang: str = "ru",
    log: bool = True,
) -> None:
    """Log the real exception and show a safe user-facing SnackBar."""
    if log and isinstance(exc, BaseException):
        logger.warning("UI error suppressed for user: %s", exc, exc_info=True)
    elif log and exc is not None:
        logger.warning("UI error suppressed for user: %s", exc)
    snack(page, user_facing_error(exc, lang), error=True)


def snack(
    page: ft.Page,
    message: str,
    *,
    error: bool = False,
) -> None:
    """Success → small top toast; errors → SnackBar. Never blank the screen."""
    if error:
        # Last-line defense: never show stack traces / SQL / paths in the UI.
        message = _sanitize_error_text(message)
    if not error:
        try:
            from lib.presentation.haptics import haptic

            haptic("light")
        except Exception:  # noqa: BLE001
            pass
        try:
            from lib.presentation.ui_feedback import flash_saved

            if flash_saved(page, message):
                return
        except Exception:  # noqa: BLE001
            pass
    # Fallback / errors: floating SnackBar (no modal barrier wash).
    bar = ft.SnackBar(
        content=ft.Text(
            message,
            color=ft.Colors.ON_ERROR if error else ft.Colors.ON_PRIMARY,
        ),
        bgcolor=ft.Colors.ERROR if error else ft.Colors.PRIMARY,
        behavior=ft.SnackBarBehavior.FLOATING,
        show_close_icon=False,
        shape=ft.RoundedRectangleBorder(radius=14),
        duration=2000,
    )
    try:
        # Prefer non-dialog API when present.
        page.snack_bar = bar  # type: ignore[attr-defined]
        page.snack_bar.open = True  # type: ignore[attr-defined]
        page.update()
        return
    except Exception:  # noqa: BLE001
        pass
    page.show_dialog(bar)


def account_icon(name: str | None) -> ft.IconData:
    """Map stored account icon keys to Flet Icons."""
    from lib.presentation.icon_registry import resolve_icon

    return resolve_icon(name, default="wallet")


def category_icon(name: str | None) -> ft.IconData:
    """Map stored category icon keys to Flet Icons."""
    from lib.presentation.icon_registry import resolve_icon

    return resolve_icon(name, default="category")


_RATE_BOOK_TTL_SECONDS = 90.0  # kept for docs; cache lives in domain rate_cache


def invalidate_rate_book_cache() -> None:
    """Drop cached FX books (call after rates update)."""
    from lib.domain.services.rate_cache import invalidate_rate_book_cache as _invalidate

    _invalidate()


async def load_rate_book(container: Any, *, force: bool = False) -> "RateBook":
    """Load stored FX rows with a short in-memory cache for UI screens."""
    from lib.domain.services.rate_book import RateBook
    from lib.domain.services.rate_cache import get_cached_rate_book

    repo = getattr(container, "currency_repository", None)
    if repo is None:
        return RateBook(())
    return await get_cached_rate_book(repo, force=force)


async def safe_convert(
    container: Any,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    *,
    quantize: bool = True,
    rate_book: Any = None,
) -> Optional[Decimal]:
    """Convert via in-memory ``rate_book`` or use case; return None on failure."""
    if rate_book is not None:
        return rate_book.convert(
            amount, from_currency, to_currency, quantize=quantize
        )
    uc = getattr(container, "convert_currency", None)
    if uc is None:
        return None
    if from_currency.upper() == to_currency.upper():
        value = Decimal(str(amount))
        return value.quantize(Decimal("0.01")) if quantize else value
    try:
        return await uc.execute(
            Decimal(str(amount)),
            from_currency=from_currency,
            to_currency=to_currency,
            quantize=quantize,
        )
    except TypeError:
        try:
            return await uc.execute(
                Decimal(str(amount)),
                from_currency=from_currency,
                to_currency=to_currency,
            )
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None
