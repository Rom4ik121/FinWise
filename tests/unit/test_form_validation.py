"""Form validation helpers for empty save."""

from __future__ import annotations

from decimal import Decimal

from lib.presentation.form_validation import require_name, require_positive_amount


class _Field:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.error = None


class _Page:
    pass


def test_require_name_rejects_blank(monkeypatch) -> None:
    shown: list[str] = []
    monkeypatch.setattr(
        "lib.presentation.form_validation.snack",
        lambda _page, msg, error=False: shown.append(msg),
    )
    monkeypatch.setattr("lib.presentation.form_validation.safe_update", lambda *_a, **_k: None)
    field = _Field("  ")
    assert require_name(field, _Page(), "en") is None
    assert field.error
    assert shown


def test_require_name_accepts_text(monkeypatch) -> None:
    monkeypatch.setattr("lib.presentation.form_validation.snack", lambda *_a, **_k: None)
    monkeypatch.setattr("lib.presentation.form_validation.safe_update", lambda *_a, **_k: None)
    field = _Field("  Rent ")
    assert require_name(field, _Page(), "en") == "Rent"
    assert field.error is None


def test_require_positive_amount_rejects_empty_and_zero(monkeypatch) -> None:
    monkeypatch.setattr("lib.presentation.form_validation.snack", lambda *_a, **_k: None)
    monkeypatch.setattr("lib.presentation.form_validation.safe_update", lambda *_a, **_k: None)
    assert require_positive_amount(_Field(""), _Page(), "en") is None
    assert require_positive_amount(_Field("0"), _Page(), "en") is None
    assert require_positive_amount(_Field("50"), _Page(), "en") == Decimal("50")
