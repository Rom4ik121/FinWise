"""Account icon key helpers."""

from __future__ import annotations

from lib.presentation.account_icons import (
    account_icon_groups,
    all_account_icon_keys,
    crypto_icon_keys,
    crypto_icon_src,
    currency_glyph_label,
    currency_icon_key,
    exchange_icon_key,
    extra_crypto_icon_keys,
    is_valid_account_icon,
    parse_currency_icon_key,
    parse_exchange_icon_key,
    resolve_account_icon_key,
)


def test_currency_icon_key_roundtrip() -> None:
    key = currency_icon_key("usd")
    assert key == "ccy_USD"
    assert parse_currency_icon_key(key) == "USD"
    assert parse_currency_icon_key("wallet") is None


def test_glyph_label() -> None:
    assert currency_glyph_label("USD", "$") == "$"
    assert currency_glyph_label("BTC", "Bitcoin") == "₿"
    assert currency_glyph_label("USDT") == "₮"


def test_groups_and_validation() -> None:
    groups = account_icon_groups()
    assert groups
    keys = all_account_icon_keys()
    assert "wallet" in keys
    assert "currency_bitcoin" not in dict(groups)["icon_group.finance"]
    group_names = [name for name, _icons in groups]
    assert group_names == [
        "icon_group.finance",
        "icon_group.cards",
        "icon_group.fiat",
        "icon_group.crypto",
        "icon_group.exchanges",
    ]
    manual = dict(account_icon_groups(include_exchanges=False))
    assert "icon_group.exchanges" not in manual
    assert is_valid_account_icon("wallet")
    assert is_valid_account_icon("exch_binance")
    assert not is_valid_account_icon("not_a_real_icon_xyz")


def test_entity_icon_groups_exclude_crypto_and_exchanges() -> None:
    from lib.presentation.account_icons import entity_icon_groups, is_valid_entity_icon

    groups = dict(entity_icon_groups())
    assert "icon_group.crypto" not in groups
    assert "icon_group.exchanges" not in groups
    assert "icon_group.fiat" not in groups
    assert "restaurant" in groups["icon_group.food"]
    assert "shopping_cart" in groups["icon_group.shopping"]
    assert is_valid_entity_icon("restaurant")
    assert is_valid_entity_icon("flag")
    assert is_valid_entity_icon("savings")
    assert not is_valid_entity_icon("exch_binance")
    assert not is_valid_entity_icon("ccy_BTC")
    flat = [i for icons in groups.values() for i in icons]
    assert not any(i.startswith("exch_") for i in flat)
    assert not any(i.startswith("ccy_") for i in flat)
    assert len(flat) > 80


def test_all_catalog_cryptos_have_account_icons() -> None:
    groups = dict(account_icon_groups())
    crypto_keys = set(groups["icon_group.crypto"])
    expected = set(crypto_icon_keys())
    assert len(expected) >= 50
    assert expected <= crypto_keys
    for key in expected:
        assert is_valid_account_icon(key)


def test_exchange_icon_keys() -> None:
    key = exchange_icon_key("Binance")
    assert key == "exch_binance"
    assert parse_exchange_icon_key(key) == "binance"
    assert resolve_account_icon_key("wallet", "binance") == "exch_binance"
    assert resolve_account_icon_key("exch_okx", "binance") == "exch_okx"
    groups = dict(account_icon_groups())
    assert "exch_binance" in groups["icon_group.exchanges"]
    from pathlib import Path

    logo = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "icons"
        / "exchanges"
        / "binance.png"
    )
    assert logo.is_file()


def test_crypto_token_pngs_are_vendored() -> None:
    assert crypto_icon_src("BTC")
    assert crypto_icon_src("ETH")
    assert crypto_icon_src("USDT")
    catalog = crypto_icon_keys()
    assert currency_icon_key("BTC") in catalog
    assert is_valid_account_icon(currency_icon_key("BTC"))
    groups = dict(account_icon_groups())
    assert currency_icon_key("BTC") in groups["icon_group.crypto"]
    # Extras are only tokens on disk that are not in currencies.json (pruned).
    assert extra_crypto_icon_keys() == ()
