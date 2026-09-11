"""Account period PDF export includes categories and charts."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from lib.core.config import AppConfig
from lib.infrastructure.services.export_service import (
    ExportService,
    PdfSectionFlags,
    _account_pdf_strings,
)


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
    import shutil
    import subprocess

    path = _sample_pdf(tmp_path, "ru")
    raw = path.read_bytes()
    # Glyph-based TTFont streams do not keep plain UTF-8 Cyrillic; ensure EN labels gone.
    assert b"Balance:" not in raw
    assert b"Generated:" not in raw
    assert b"Income (ops)" not in raw
    assert b"of turnover" not in raw
    assert path.stat().st_size > 2000
    decoded = raw.decode("latin-1", errors="ignore")
    # Helvetica-only reports turn Russian into tofu boxes.
    assert "FinWiseSans" in decoded or "Liberation" in decoded or "DejaVu" in decoded
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        extracted = subprocess.check_output(
            [pdftotext, "-layout", str(path), "-"],
            text=True,
        )
        assert "Отчёт" in extracted
        assert "Баланс" in extracted
        assert "Доход" in extracted


def test_unicode_pdf_font_registers_cyrillic() -> None:
    from reportlab.pdfbase import pdfmetrics

    from lib.infrastructure.services.export_service import (
        _PDF_FONT,
        _register_unicode_pdf_fonts,
    )

    regular, bold, ttf = _register_unicode_pdf_fonts()
    assert regular == _PDF_FONT
    assert bold.startswith("FinWiseSans")
    assert ttf is not None and ttf.is_file()
    # Helvetica has no Cyrillic; a real TTF must have a non-zero Ж width.
    assert pdfmetrics.stringWidth("Ж", _PDF_FONT, 12) > 0
    # Second call must reuse, not fall back to Helvetica.
    regular2, _bold2, _ttf2 = _register_unicode_pdf_fonts()
    assert regular2 == _PDF_FONT


def test_account_pdf_can_omit_transaction_section(tmp_path: Path) -> None:
    import shutil
    import subprocess

    cfg = AppConfig(data_dir=tmp_path / "omit")
    cfg.ensure_directories()
    svc = ExportService(cfg)
    path = svc.export_account_period_pdf(
        account_name="Cash",
        currency="USD",
        period_label="30 дней",
        balance=Decimal("100.00"),
        income=Decimal("50.00"),
        expense=Decimal("30.00"),
        ops_income=Decimal("50.00"),
        ops_expense=Decimal("30.00"),
        by_category=[("Еда", Decimal("20.00"))],
        expenses=[("2026-09-01", "Еда", Decimal("20.00"))],
        language="ru",
        sections=PdfSectionFlags(
            summary=True,
            categories=True,
            transactions=False,
            charts=False,
        ),
    )
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return
    extracted = subprocess.check_output(
        [pdftotext, "-layout", str(path), "-"],
        text=True,
    )
    assert "Отчёт" in extracted
    assert "Операции расхода" not in extracted
    assert "Динамика" not in extracted


def test_export_summary_pdf_localized_ru(tmp_path: Path) -> None:
    import shutil
    import subprocess

    from tests.factories import make_account

    cfg = AppConfig(data_dir=tmp_path / "summary")
    cfg.ensure_directories()
    svc = ExportService(cfg)
    path = svc.export_summary_pdf(
        accounts=[make_account(name="Касса", currency="UZS")],
        language="ru",
        period_label="30 дней",
        scope_label="Личные",
        currency="UZS",
        total_balance=Decimal("10.00"),
        income=Decimal("5.00"),
        expense=Decimal("2.00"),
        sections=PdfSectionFlags(
            summary=True,
            accounts=True,
            transactions=False,
            categories=False,
            charts=False,
            goals=False,
            debts=False,
            subscriptions=False,
        ),
    )
    assert path.is_file()
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return
    extracted = subprocess.check_output(
        [pdftotext, "-layout", str(path), "-"],
        text=True,
    )
    assert "Финансовый отчёт" in extracted
    assert "Касса" in extracted
    assert "Баланс" in extracted


def test_account_pdf_strings_cover_langs() -> None:
    for lang in ("ru", "en", "uz"):
        s = _account_pdf_strings(lang)
        assert s["title"]
        assert s["balance"]
        assert s["income"]
        assert s["expense"]


def test_matplotlib_pdf_forces_agg_backend() -> None:
    from lib.infrastructure.services.export_service import _ensure_matplotlib_agg

    _ensure_matplotlib_agg()
    import matplotlib

    assert matplotlib.get_backend().lower() == "agg"


def test_export_summary_pdf_debts_use_counterparty(tmp_path: Path) -> None:
    from tests.factories import make_account, make_debt

    cfg = AppConfig(data_dir=tmp_path / "debts-pdf")
    cfg.ensure_directories()
    svc = ExportService(cfg)
    path = svc.export_summary_pdf(
        accounts=[make_account(name="Cash")],
        debts=[make_debt(counterparty="Alpha Bank", amount="250")],
        language="en",
        period_label="30 days",
        currency="RUB",
        total_balance=Decimal("10.00"),
        income=Decimal("0"),
        expense=Decimal("0"),
        sections=PdfSectionFlags(
            summary=True,
            accounts=False,
            transactions=False,
            categories=False,
            charts=False,
            goals=False,
            debts=True,
            subscriptions=False,
        ),
    )
    assert path.is_file()
    assert path.stat().st_size > 500


def test_export_resolve_stays_inside_export_dir(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path / "confine")
    cfg.ensure_directories()
    svc = ExportService(cfg)
    inside = svc._resolve("../../etc/passwd")
    assert inside.parent == svc.export_dir.resolve()
    assert inside.name == "passwd"
    outside = tmp_path / "outside.json"
    confined = svc._resolve(str(outside))
    assert confined.parent == svc.export_dir.resolve()
    assert confined.name == "outside.json"
    with pytest.raises(ValueError, match="Invalid export filename"):
        svc._resolve("..")
    with pytest.raises(ValueError, match="Invalid export filename"):
        svc._resolve("")
