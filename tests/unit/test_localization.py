"""Localization dictionary and helpers."""

from __future__ import annotations

from lib.infrastructure.services.localization import (
    LANG_LABELS,
    LANG_PICKER_ORDER,
    STRINGS,
    SUPPORTED_LANGS,
    available_keys,
    localize_category_name,
    merge_strings,
    normalize_lang,
    t,
)

_REQUIRED_LANGS = (
    "en",
    "ru",
    "uk",
    "be",
    "uz",
    "kk",
    "de",
    "es",
    "fr",
    "pt",
    "it",
    "pl",
    "tr",
    "id",
    "zh",
    "ja",
    "ko",
    "hi",
)


def test_supported_langs() -> None:
    assert SUPPORTED_LANGS == _REQUIRED_LANGS
    assert LANG_PICKER_ORDER == SUPPORTED_LANGS
    for code in SUPPORTED_LANGS:
        assert code in LANG_LABELS
        assert LANG_LABELS[code].strip()
        assert t(f"lang.{code}", "en") == LANG_LABELS[code]


def test_normalize_lang() -> None:
    assert normalize_lang("ru-RU") == "ru"
    assert normalize_lang("en_US") == "en"
    assert normalize_lang("uz-Latn") == "uz"
    assert normalize_lang("uk-UA") == "uk"
    assert normalize_lang("be_BY") == "be"
    assert normalize_lang("kk-KZ") == "kk"
    assert normalize_lang("de_DE") == "de"
    assert normalize_lang("pt-BR") == "pt"
    assert normalize_lang("pt-PT") == "pt"
    assert normalize_lang("zh-CN") == "zh"
    assert normalize_lang("zh-Hans") == "zh"
    assert normalize_lang("zh-TW") == "zh"
    assert normalize_lang("in_ID") == "id"
    assert normalize_lang(None) == "en"
    assert normalize_lang("xx") == "en"
    assert normalize_lang("ar") == "en"
    assert normalize_lang("he") == "en"


def test_every_key_has_all_langs() -> None:
    for key, entry in STRINGS.items():
        for lang in SUPPORTED_LANGS:
            assert lang in entry, f"{key} missing {lang}"
            assert entry[lang].strip(), f"{key}/{lang} empty"


def test_t_returns_correct_language() -> None:
    assert t("nav.home", "ru") == "Главная"
    assert t("nav.home", "en") == "Home"
    assert t("nav.home", "uz") == "Bosh sahifa"
    assert t("nav.home", "uk") == "Головна"
    assert t("nav.home", "de") == "Startseite"
    assert t("nav.home", "pt") == "Início"
    assert t("nav.home", "zh") == "首页"


def test_t_missing_key_and_default() -> None:
    assert t("does.not.exist") == "does.not.exist"
    assert t("does.not.exist", default="fallback") == "fallback"


def test_t_falls_back_to_english_never_blank() -> None:
    assert t("nav.settings", "fr").strip()
    assert t("nav.settings", "xx") == t("nav.settings", "en")


def test_localize_category_name() -> None:
    assert localize_category_name("Еда", "ru") == "Еда"
    assert localize_category_name("Еда", "en") == "Food"
    assert localize_category_name("Еда", "uz") == "Ovqat"
    assert localize_category_name("Еда", "uk") == "Їжа"
    assert localize_category_name("Еда", "de") == "Essen"
    assert localize_category_name("Торговля", "en") == "Trading"
    assert localize_category_name("Комиссия", "uz") == "Komissiya"
    assert localize_category_name("Custom", "en") == "Custom"


def test_portuguese_picker_label() -> None:
    assert LANG_LABELS["pt"] == "Português"
    assert t("lang.pt", "en") == "Português"


def test_merge_strings_and_available_keys() -> None:
    merge_strings({"test.tmp.key": {"ru": "А", "en": "A", "uz": "A"}})
    assert t("test.tmp.key", "ru") == "А"
    assert t("test.tmp.key", "de") == "A"  # English fallback, never blank
    assert "test.tmp.key" in available_keys()
