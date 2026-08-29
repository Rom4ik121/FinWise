"""Parse spoken expense / income phrases into a draft transaction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from lib.domain.entities.transaction import TransactionType

_EXPENSE_WORDS = {
    "расход",
    "расхода",
    "трата",
    "траты",
    "потратил",
    "потратила",
    "expense",
    "spend",
    "spent",
    "xarajat",
}
_INCOME_WORDS = {
    "доход",
    "дохода",
    "получил",
    "получила",
    "income",
    "earned",
    "daromad",
}
_TYPE_WORDS = _EXPENSE_WORDS | _INCOME_WORDS
_MULTIPLIERS = {
    "тыс": Decimal("1000"),
    "тысяч": Decimal("1000"),
    "тысячи": Decimal("1000"),
    "k": Decimal("1000"),
    "к": Decimal("1000"),
    "млн": Decimal("1000000"),
    "миллион": Decimal("1000000"),
    "миллиона": Decimal("1000000"),
    "m": Decimal("1000000"),
}

_AMOUNT_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)(?:\s*(?P<mult>тыс(?:яч[аи]?)?|миллион(?:а)?|млн|[kкм]))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VoiceDraft:
    """Parsed voice command for a money operation."""

    tx_type: TransactionType
    amount: Optional[Decimal]
    category: str
    raw: str


def parse_voice_expense(text: str) -> VoiceDraft:
    """Turn a spoken phrase into type, amount, and category name.

    Examples: ``расход кофе 15000``, ``доход зарплата 2 млн``, ``такси 25 тысяч``.
    """
    raw = (text or "").strip()
    lowered = raw.casefold()
    tx_type = TransactionType.EXPENSE
    for token in re.split(r"\s+", lowered):
        clean = token.strip(".,!?")
        if clean in _INCOME_WORDS:
            tx_type = TransactionType.INCOME
            break
        if clean in _EXPENSE_WORDS:
            tx_type = TransactionType.EXPENSE
            break

    amount: Optional[Decimal] = None
    amount_span: tuple[int, int] | None = None
    for match in _AMOUNT_RE.finditer(lowered):
        try:
            number = Decimal(match.group("num").replace(",", "."))
        except (InvalidOperation, AttributeError):
            continue
        mult_raw = (match.group("mult") or "").casefold()
        for key, factor in _MULTIPLIERS.items():
            if mult_raw.startswith(key):
                number *= factor
                break
        try:
            amount = number.quantize(Decimal("0.01"))
        except InvalidOperation:
            amount = number
        amount_span = match.span()

    category_source = raw
    if amount_span is not None:
        category_source = f"{raw[: amount_span[0]]} {raw[amount_span[1]:]}".strip()
    filtered = [
        word
        for word in re.split(r"\s+", category_source)
        if word and word.casefold().strip(".,!?") not in _TYPE_WORDS
    ]
    category = " ".join(filtered).strip(" .,!?") or "Прочее"
    return VoiceDraft(tx_type=tx_type, amount=amount, category=category, raw=raw)
