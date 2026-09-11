"""CSV statement detection, amount parsing, and dry-run mapping."""

from __future__ import annotations

from decimal import Decimal

from lib.domain.entities.transaction import TransactionType
from lib.domain.services.csv_statement import (
    PRESET_EN_BANK,
    PRESET_RU_BANK,
    PRESET_SIMPLE,
    detect_csv,
    detect_encoding,
    map_rows,
    parse_csv_amount,
    parse_csv_date,
)


def test_parse_csv_amount_bank_formats() -> None:
    assert parse_csv_amount("1 234,56") == Decimal("1234.56")
    assert parse_csv_amount("(12.00)") == Decimal("-12.00")
    assert parse_csv_amount("-12") == Decimal("-12.00")
    assert parse_csv_amount("1.234,50") == Decimal("1234.50")
    assert parse_csv_amount("1,234.50") == Decimal("1234.50")


def test_parse_csv_date_formats() -> None:
    assert parse_csv_date("2026-01-15").date().isoformat() == "2026-01-15"
    assert parse_csv_date("15.01.2026").date().isoformat() == "2026-01-15"
    assert parse_csv_date("01/15/2026").date().isoformat() == "2026-01-15"


def test_detect_ru_bank_cp1251_semicolon() -> None:
    payload = "Дата;Сумма;Назначение\n01.02.2026;100,50;Магнит".encode("cp1251")
    assert detect_encoding(payload) == "cp1251"
    info = detect_csv(payload)
    assert info.delimiter == ";"
    assert info.preset == PRESET_RU_BANK
    assert info.mapping["date"] == "Дата"
    assert info.mapping["amount"] == "Сумма"


def test_detect_en_bank_and_simple() -> None:
    en = detect_csv(b"Date,Amount,Description,Currency\n2026-01-01,10,Coffee,USD")
    assert en.preset == PRESET_EN_BANK
    simple = detect_csv(b"date,amount,description\n2026-01-01,10,Tea")
    assert simple.preset == PRESET_SIMPLE


def test_map_rows_invalid_and_signed_expense() -> None:
    payload = (
        b"date,amount,description\n"
        b"2026-01-15,25.00,Coffee\n"
        b"not-a-date,10.00,Bad\n"
        b"2026-01-16,-10.00,Refund\n"
        b"2026-01-17,0,Zero\n"
    )
    info = detect_csv(payload)
    rows = map_rows(payload, info.mapping, detect=info)
    assert len(rows) == 4
    assert rows[0].ok and rows[0].tx_type is TransactionType.INCOME
    assert rows[0].amount == Decimal("25.00")
    assert not rows[1].ok
    assert rows[2].ok and rows[2].tx_type is TransactionType.EXPENSE
    assert rows[2].amount == Decimal("10.00")
    assert not rows[3].ok
