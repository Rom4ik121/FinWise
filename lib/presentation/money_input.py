"""Locale-aware amount typing: group thousands with ``.`` or ``,``."""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

import flet as ft

from lib.infrastructure.services.localization import normalize_lang
from lib.presentation.utils import safe_update

# After a programmatic ``field.value`` write, Flet web often re-delivers the
# last keystroke. That turns repaired ``50`` into ``500`` (or ``050``). Ignore
# that echo briefly; a later real extra digit still lands.
AMOUNT_WRITE_ECHO_SECONDS = 0.12


def amount_separators(lang: str) -> tuple[str, str]:
    """Return ``(thousands, decimal)`` for the UI language.

    English and CJK / Hindi use ``1,234.50``; European and CIS languages use
    ``1.234,50``.
    """
    if normalize_lang(lang) in {"en", "zh", "ja", "ko", "hi"}:
        return ",", "."
    return ".", ","


def amount_text(field: Any) -> str:
    """Best-effort amount string from a TextField.

    Flet web can leave ``value`` empty until blur while the grouped ``on_change``
    cache already has the digits the user typed.
    """
    live = str(getattr(field, "value", None) or "").strip()
    cached = getattr(field, "_fw_amount_text", None)
    stored = ""
    if isinstance(cached, dict):
        stored = str(cached.get("text") or "").strip()
    return live or stored


def parse_optional_amount(text: str | None) -> Decimal:
    """Parse a fee-like field: empty means zero."""
    if not (text or "").strip():
        return Decimal("0")
    return parse_amount(text)


def parse_filter_amount(text: str | None) -> Decimal | None:
    """Amount bound for list filters: blank means “no bound”, not zero."""
    if not (text or "").strip():
        return None
    try:
        return parse_amount(text)
    except InvalidOperation:
        return None


def amount_list_filters(
    min_text: str | None, max_text: str | None
) -> dict[str, Decimal]:
    """``list()`` kwargs for amount bounds; empty/invalid text is omitted."""
    filters: dict[str, Decimal] = {}
    amin = parse_filter_amount(min_text)
    amax = parse_filter_amount(max_text)
    if amin is not None:
        filters["amount_min"] = amin
    if amax is not None:
        filters["amount_max"] = amax
    return filters


def parse_amount_field(field: Any) -> Decimal:
    """Parse a grouped amount TextField, including the unflushed cache."""
    return parse_amount(amount_text(field))


def parse_optional_amount_field(field: Any) -> Decimal:
    """Parse a fee-like TextField; empty (including unflushed empty) is zero."""
    return parse_optional_amount(amount_text(field))


def parse_amount(text: str | None) -> Decimal:
    """Parse a grouped amount into ``Decimal``.

    Raises ``InvalidOperation`` when the field is empty or not a number.
    """
    int_digits, frac, trailing = _split_int_frac(text)
    if trailing and not frac:
        frac = ""
    if not int_digits and not frac:
        raise InvalidOperation("empty amount")
    raw = f"{int_digits or '0'}.{frac}" if frac is not None else (int_digits or "0")
    return Decimal(raw)


def format_amount_input(text: str, lang: str) -> str:
    """Re-group digits in a live amount field without dropping a trailing decimal."""
    thousands, decimal = amount_separators(lang)
    stripped = (text or "").strip()
    if not stripped or stripped in {"-", "−"}:
        return "-" if stripped.startswith(("-", "−")) else ""
    negative = stripped.startswith(("-", "−"))
    int_digits, frac, trailing = _split_int_frac(text)
    if int_digits is None:
        return text
    grouped = _group_int(int_digits, thousands)
    if trailing or frac is not None:
        out = f"{grouped}{decimal}{frac or ''}"
    else:
        out = grouped
    return f"-{out}" if negative else out


def format_amount_value(value: object, lang: str) -> str:
    """Format a stored amount for an editable field."""
    if value is None or value == "":
        return ""
    try:
        quantized = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, ArithmeticError):
        return format_amount_input(str(value), lang)
    if quantized == quantized.to_integral_value():
        text = str(int(abs(quantized)))
    else:
        text = f"{abs(quantized):.2f}"
    formatted = format_amount_input(text, lang)
    return f"-{formatted}" if quantized < 0 else formatted


def repair_amount_caret_prepend(previous: str, current: str) -> str:
    """Undo Flet-web inserting the next digit at caret 0.

    Typing ``5`` then ``0`` with the caret stuck at the start yields ``05``.
    Grouping then strips the leading zero back to ``5``. If ``current`` is
    exactly one digit *prepended* to ``previous``, treat it as an append.
    """
    prev_int, prev_frac, prev_trail = _split_int_frac(previous)
    cur_int, cur_frac, cur_trail = _split_int_frac(current)
    if prev_frac is not None or cur_frac is not None or prev_trail or cur_trail:
        return current
    prev_digits = prev_int or ""
    cur_digits = cur_int or ""
    if (
        prev_digits
        and len(cur_digits) == len(prev_digits) + 1
        and cur_digits[1:] == prev_digits
    ):
        prepended = cur_digits[0]
        # "50" + caret-0 echo of "0" → "050". That is not a new digit.
        if prepended == "0" and len(prev_digits) >= 2:
            return previous
        return f"{prev_digits}{prepended}"
    return current


def is_amount_write_echo(committed: str, incoming: str) -> bool:
    """True when ``incoming`` is the last digit of ``committed`` echoed once.

    ``50`` + echoed ``0`` → ``500`` or ``050``. Fractional edits are never
    treated as echo so ``50,0`` still types normally.
    """
    if committed == incoming:
        return False
    prev_int, prev_frac, prev_trail = _split_int_frac(committed)
    cur_int, cur_frac, cur_trail = _split_int_frac(incoming)
    if prev_frac is not None or cur_frac is not None or prev_trail or cur_trail:
        return False
    prev_digits = prev_int or ""
    cur_digits = cur_int or ""
    if not prev_digits or not cur_digits:
        return False
    if cur_digits == prev_digits:
        return True
    last = prev_digits[-1]
    if cur_digits == f"{prev_digits}{last}":
        return True
    if cur_digits == f"{last}{prev_digits}":
        return True
    return False


def attach_grouped_digits(
    field: ft.TextField,
    lang: str,
    *,
    extra_on_change: Optional[Callable[[ft.ControlEvent], Any]] = None,
) -> ft.TextField:
    """Keep ``field`` grouped as the user types; optionally chain another handler.

    Do **not** rewrite or ``update()`` when the text is unchanged: Flet web
    resets the caret to 0 on every value write, so ``5`` + ``0`` becomes
    ``05`` and grouping strips it back to ``5``.
    """
    last = {"text": field.value or ""}
    field._fw_amount_text = last
    echo_until = {"t": 0.0}
    applying = {"on": False}

    def _on_change(e: ft.ControlEvent) -> None:
        if applying["on"]:
            return
        current = field.value or ""
        now = time.monotonic()
        if now < echo_until["t"] and is_amount_write_echo(last["text"], current):
            applying["on"] = True
            try:
                field.value = last["text"]
                try:
                    end = len(last["text"])
                    field.selection = ft.TextSelection(
                        base_offset=end, extent_offset=end
                    )
                except Exception:  # noqa: BLE001
                    pass
                safe_update(field)
            finally:
                applying["on"] = False
            if extra_on_change is not None:
                extra_on_change(e)
            return
        repaired = repair_amount_caret_prepend(last["text"], current)
        formatted = format_amount_input(repaired, lang)
        last["text"] = formatted
        if formatted != current:
            applying["on"] = True
            try:
                field.value = formatted
                echo_until["t"] = time.monotonic() + AMOUNT_WRITE_ECHO_SECONDS
                try:
                    end = len(formatted)
                    field.selection = ft.TextSelection(
                        base_offset=end, extent_offset=end
                    )
                except Exception:  # noqa: BLE001
                    pass
                safe_update(field)
            finally:
                applying["on"] = False
        if extra_on_change is not None:
            extra_on_change(e)

    field.on_change = _on_change
    field.on_blur = _on_change
    return field


def make_amount_field(
    lang: str,
    *,
    label: str,
    value: object = "",
    extra_on_change: Optional[Callable[[ft.ControlEvent], Any]] = None,
    **kwargs: Any,
) -> ft.TextField:
    """Build a numeric TextField that groups thousands while typing."""
    from lib.presentation.form_keyboard import configure_field

    kwargs.setdefault("keyboard_type", ft.KeyboardType.NUMBER)
    field = ft.TextField(
        label=label,
        value=format_amount_value(value, lang) if value not in (None, "") else "",
        **kwargs,
    )
    configure_field(field, "number")
    return attach_grouped_digits(field, lang, extra_on_change=extra_on_change)


def _group_int(digits: str, sep: str) -> str:
    if not digits:
        return "0"
    trimmed = digits.lstrip("0")
    if not trimmed:
        return "0"
    parts: list[str] = []
    while trimmed:
        parts.append(trimmed[-3:])
        trimmed = trimmed[:-3]
    return sep.join(reversed(parts))


def _split_int_frac(text: str | None) -> tuple[Optional[str], Optional[str], bool]:
    """Split typed text into integer digits, optional fraction, trailing-decimal flag.

    A separator is decimal only when it is the last one and 1–2 digits follow
    (or nothing, if the user just typed it). Longer tails are thousands:
    ``1,000000`` → 1_000_000, not 1.000000.
    """
    if text is None:
        return None, None, False
    s = str(text).strip().replace("−", "-")
    if s.startswith("-"):
        s = s[1:]
    s = s.replace(" ", "").replace("\u00a0", "").replace("'", "")
    raw = "".join(c for c in s if c.isdigit() or c in ".,")
    if not raw:
        return "", None, False

    trailing = raw.endswith(".") or raw.endswith(",")
    digits_only = "".join(c for c in raw if c.isdigit())

    if "," in raw and "." in raw:
        dec_pos = max(raw.rfind(","), raw.rfind("."))
        int_digits = "".join(c for c in raw[:dec_pos] if c.isdigit())
        frac = "".join(c for c in raw[dec_pos + 1 :] if c.isdigit())
        if trailing and not frac:
            return int_digits, "", True
        if len(frac) <= 2:
            return int_digits, frac, False
        return digits_only, None, False

    sep = "," if "," in raw else ("." if "." in raw else None)
    if sep is None:
        return digits_only, None, False

    parts = raw.split(sep)
    if trailing:
        int_digits = "".join(p for p in parts if p)
        return int_digits, "", True
    last = parts[-1]
    head = "".join(parts[:-1])
    if 1 <= len(last) <= 2:
        return head, last, False
    return "".join(parts), None, False
