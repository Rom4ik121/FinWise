"""Account period PDF export includes categories and charts."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from lib.core.config import AppConfig
from lib.infrastructure.services.export_service import ExportService, _account_pdf_strings


def _sample_pdf(tmp_path: Path, language: str) -> Path:
    cfg = AppConfig(data_dir=tmp_path / language)
    cfg.ensure_directories()
    svc = ExportService(cfg)
    return svc.export_account_period_pdf(
        account_name="Cash",
        currency="USD",
        period_label="30 дней" if language == "ru" else "30 days",
        balance=Decimal("100.00"),
        income=Decimal("50.00"),
        expense=Decimal("30.00"),
        ops_income=Decimal("50.00"),
        ops_expense=Decimal("30.00"),
        by_category=[("Food", Decimal("20.00")), ("Taxi", Decimal("10.00"))],
        expenses=[
            ("2026-09-01", "Food", Decimal("20.00")),
            ("2026-09-02", "Taxi", Decimal("10.00")),
        ],
        by_period=[
            ("W1", Decimal("50.00"), Decimal("30.00")),
            ("W2", Decimal("40.00"), Decimal("20.00")),
        ],
        language=language,
    )


def test_export_account_period_pdf_writes_file(tmp_path: Path) -> None:
    path = _sample_pdf(tmp_path, "en")
    assert path.is_file()
    assert path.suffix == ".pdf"
    assert path.stat().st_size > 500


def test_export_account_period_pdf_localized_ru(tmp_path: Path) -> None:
    path = _sample_pdf(tmp_path, "ru")
    raw = path.read_bytes()
    # Glyph-based TTFont streams do not keep plain UTF-8 Cyrillic; ensure EN labels gone.
    assert b"Balance:" not in raw
    assert b"Generated:" not in raw
    assert b"Income (ops)" not in raw
    assert b"of turnover" not in raw
    assert path.stat().st_size > 2000


def test_account_pdf_strings_cover_langs() -> None:
    for lang in ("ru", "en", "uz"):
        s = _account_pdf_strings(lang)
        assert s["title"]
        assert s["balance"]
        assert s["income"]
        assert s["expense"]
