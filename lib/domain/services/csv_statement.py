"""Parse bank / export CSV bytes into mapped transaction rows (no I/O)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Sequence

from lib.domain.entities.money import quantize_money
from lib.domain.entities.transaction import TransactionType

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M",
    "%d-%m-%Y",
    "%Y/%m/%d",
)

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251", "cp1252", "latin-1")
_DELIMS = (",", ";", "\t", "|")

PRESET_FINWISE = "finwise"
PRESET_SIMPLE = "simple"
PRESET_RU_BANK = "ru_bank"
PRESET_EN_BANK = "en_bank"
PRESET_CUSTOM = "custom"

PRESETS: dict[str, dict[str, str]] = {
    PRESET_FINWISE: {
        "date": "date",
        "amount": "amount",
        "currency": "currency",
        "description": "comment",
        "account": "account_id",
        "type": "type",
    },
    PRESET_SIMPLE: {
        "date": "date",
        "amount": "amount",
        "description": "description",
    },
    PRESET_RU_BANK: {
        "date": "Дата",
        "amount": "Сумма",
        "description": "Назначение",
    },
    PRESET_EN_BANK: {
        "date": "Date",
        "amount": "Amount",
        "currency": "Currency",
        "description": "Description",
        "account": "Account",
    },
}

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "дата", "datetime", "posted", "value date", "operdate"),
    "amount": ("amount", "сумма", "sum", "value", "debit", "credit"),
    "currency": ("currency", "валюта", "ccy", "curr"),
    "description": (
        "description",
        "comment",
        "назначение",
        "описание",
        "details",
        "memo",
        "payee",
        "narrative",
    ),
    "account": ("account", "account_id", "счёт", "счет", "wallet"),
    "type": ("type", "тип", "direction", "drcr"),
}


@dataclass(frozen=True)
class CsvDetectResult:
    """Detected file shape."""

    encoding: str
    delimiter: str
    headers: list[str]
    preset: str
    mapping: dict[str, str]
    sample_rows: list[dict[str, str]]


@dataclass(frozen=True)
class CsvMappedRow:
    """One validated (or failed) import candidate."""

    index: int
    date: Optional[datetime]
    amount: Optional[Decimal]
    currency: str
    description: str
    account_hint: str
    tx_type: TransactionType
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.date is not None and self.amount is not None


def detect_encoding(payload: bytes) -> str:
    """Pick a working text encoding (UTF-8 first, then common bank encodings)."""
    if not payload:
        return "utf-8"
    for enc in _ENCODINGS:
        try:
            payload.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def detect_delimiter(text: str) -> str:
    """Choose the delimiter with the most separators on the header line."""
    header = ""
    for line in text.splitlines():
        if line.strip():
            header = line
            break
    counts = {d: header.count(d) for d in _DELIMS}
    best = max(counts, key=counts.get)
    if counts[best] <= 0:
        return ","
    return best


def _norm_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _match_header(headers: Sequence[str], *aliases: str) -> Optional[str]:
    wanted = {_norm_header(a) for a in aliases if a}
    for header in headers:
        if _norm_header(header) in wanted:
            return header
    return None


def guess_preset(headers: Sequence[str]) -> str:
    """Return a named preset that matches the header set, else custom."""
    lower = {_norm_header(h) for h in headers}
    if {"date", "amount", "comment", "type"}.issubset(lower) or {
        "date",
        "amount",
        "account_id",
    }.issubset(lower):
        return PRESET_FINWISE
    if "дата" in lower and "сумма" in lower:
        return PRESET_RU_BANK
    if "date" in lower and "amount" in lower and (
        "currency" in lower or "account" in lower
    ):
        return PRESET_EN_BANK
    if "date" in lower and "amount" in lower:
        return PRESET_SIMPLE
    return PRESET_CUSTOM


def mapping_from_headers(headers: Sequence[str], *, preset: Optional[str] = None) -> dict[str, str]:
    """Build a column map using a preset, then fill gaps from aliases."""
    key = preset or guess_preset(headers)
    mapping: dict[str, str] = {}
    preset_map = PRESETS.get(key) or {}
    for field, header_name in preset_map.items():
        hit = _match_header(headers, header_name)
        if hit:
            mapping[field] = hit
    for field, aliases in _HEADER_ALIASES.items():
        if field in mapping:
            continue
        hit = _match_header(headers, *aliases)
        if hit:
            mapping[field] = hit
    return mapping


def detect_csv(payload: bytes) -> CsvDetectResult:
    """Detect encoding, delimiter, headers, and a sensible column map."""
    encoding = detect_encoding(payload)
    text = payload.decode(encoding, errors="replace")
    delimiter = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [str(h) for h in (reader.fieldnames or []) if str(h).strip()]
    preset = guess_preset(headers)
    mapping = mapping_from_headers(headers, preset=preset)
    sample: list[dict[str, str]] = []
    for row in reader:
        if not any(str(v or "").strip() for v in row.values()):
            continue
        sample.append({str(k): str(v or "") for k, v in row.items() if k is not None})
        if len(sample) >= 8:
            break
    return CsvDetectResult(
        encoding=encoding,
        delimiter=delimiter,
        headers=headers,
        preset=preset,
        mapping=mapping,
        sample_rows=sample,
    )


def parse_csv_amount(raw: object) -> Decimal:
    """Parse bank-style amounts: ``1 234,56``, ``(12.00)``, ``-12``."""
    text = str(raw or "").strip()
    if not text:
        raise InvalidOperation
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = text.replace("\xa0", " ").replace(" ", "")
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    elif text.count(",") > 0 and text.count(".") > 0:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    value = quantize_money(Decimal(text))
    if negative:
        value = -value
    return value


def parse_csv_date(raw: object) -> datetime:
    """Parse a date/time string into an aware UTC datetime."""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty date")
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text[:19] if "T" in text else text, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError("invalid date")


def _infer_type(raw: object, amount: Decimal) -> TransactionType:
    token = str(raw or "").strip().lower()
    if token in {"income", "in", "credit", "доход", "cr"}:
        return TransactionType.INCOME
    if token in {"expense", "out", "debit", "расход", "dr"}:
        return TransactionType.EXPENSE
    if amount < 0:
        return TransactionType.EXPENSE
    return TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE


def map_rows(
    payload: bytes,
    mapping: dict[str, str],
    *,
    default_currency: str = "RUB",
    detect: Optional[CsvDetectResult] = None,
    max_rows: int = 5_000,
) -> list[CsvMappedRow]:
    """Turn CSV bytes + column mapping into preview/commit rows."""
    info = detect or detect_csv(payload)
    text = payload.decode(info.encoding, errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=info.delimiter)
    out: list[CsvMappedRow] = []
    for index, row in enumerate(reader, start=2):
        if len(out) >= max_rows:
            break
        if not any(str(v or "").strip() for v in row.values()):
            continue
        error: Optional[str] = None
        parsed_date: Optional[datetime] = None
        amount: Optional[Decimal] = None
        try:
            date_key = mapping.get("date") or ""
            amount_key = mapping.get("amount") or ""
            if not date_key or not amount_key:
                raise ValueError("mapping incomplete")
            parsed_date = parse_csv_date(row.get(date_key))
            amount = parse_csv_amount(row.get(amount_key))
        except (ValueError, InvalidOperation, ArithmeticError):
            error = "invalid_row"
        desc_key = mapping.get("description") or ""
        ccy_key = mapping.get("currency") or ""
        acc_key = mapping.get("account") or ""
        type_key = mapping.get("type") or ""
        description = str(row.get(desc_key) or "").strip() if desc_key else ""
        currency = (
            str(row.get(ccy_key) or "").strip().upper()
            if ccy_key
            else default_currency
        ) or default_currency
        account_hint = str(row.get(acc_key) or "").strip() if acc_key else ""
        signed = amount if amount is not None else Decimal("0")
        tx_type = _infer_type(row.get(type_key) if type_key else "", signed)
        abs_amount = abs(amount) if amount is not None else None
        if abs_amount is not None and abs_amount <= 0 and error is None:
            error = "invalid_amount"
            abs_amount = None
        out.append(
            CsvMappedRow(
                index=index,
                date=parsed_date,
                amount=abs_amount,
                currency=currency,
                description=description,
                account_hint=account_hint,
                tx_type=tx_type,
                error=error,
            )
        )
    return out


def iter_valid(rows: Iterable[CsvMappedRow]) -> list[CsvMappedRow]:
    """Rows that passed dry-run validation."""
    return [row for row in rows if row.ok]
