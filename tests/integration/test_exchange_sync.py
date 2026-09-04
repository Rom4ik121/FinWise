"""Connect and sync exchange accounts without hitting live APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from lib.domain.entities.account import Account
from lib.domain.entities.transaction import TransactionType
from lib.infrastructure.api.ccxt_exchange_client import (
    Holding,
    NormalizedTrade,
    Snapshot,
)
from tests.conftest import run_async
from tests.factories import make_account


def _snapshot() -> Snapshot:
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    return Snapshot(
        total=Decimal("1000.00"),
        currency="USDT",
        holdings=[
            Holding(asset="BTC", amount=Decimal("0.01"), value=Decimal("900.00")),
            Holding(asset="USDT", amount=Decimal("100.00"), value=Decimal("100.00")),
        ],
        trades=[
            NormalizedTrade(
                external_id="buy-1",
                kind="trade",
                side="buy",
                amount=Decimal("50.00"),
                currency="USDT",
                date=now,
                comment="BUY BTC/USDT",
            ),
            NormalizedTrade(
                external_id="sell-1",
                kind="trade",
                side="sell",
                amount=Decimal("20.00"),
                currency="USDT",
                date=now,
                comment="SELL ETH/USDT",
            ),
            NormalizedTrade(
                external_id="dep-1",
                kind="deposit",
                side="buy",
                amount=Decimal("100.00"),
                currency="USDT",
                date=now,
                comment="deposit USDT",
            ),
        ],
    )


def test_container_wires_exchange_use_cases(container) -> None:
    assert container.exchange_connection_repository is not None
    assert container.connect_exchange_account is not None
    assert container.sync_exchange_account is not None


def test_connect_rejects_unknown_provider(container) -> None:
    async def _run() -> None:
        with pytest.raises(ValueError, match="Unknown exchange"):
            await container.connect_exchange_account.execute(
                account=make_account(name="X", currency="USDT", balance="0"),
                provider="not-a-venue",
                api_key="k",
                secret="s",
            )

    run_async(_run())


def test_connect_and_sync_imports_trades(container, monkeypatch) -> None:
    monkeypatch.setattr(
        container.connect_exchange_account._gateway,
        "test_credentials",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        container.sync_exchange_account._gateway,
        "fetch_snapshot",
        lambda **_kwargs: _snapshot(),
    )

    async def _run() -> None:
        draft = Account(
            name="placeholder",
            currency="RUB",
            initial_balance=Decimal("0"),
            balance=Decimal("0"),
            icon="token",
            color="#F3BA2F",
        )
        saved = await container.connect_exchange_account.execute(
            account=draft,
            provider="binance",
            api_key="key",
            secret="secret",
        )
        assert saved.name == "Binance"
        link = await container.exchange_connection_repository.get_by_account_id(
            saved.id
        )
        assert link is not None
        assert link.provider == "binance"
        assert link.credentials_encrypted

        result = await container.sync_exchange_account.execute(saved.id)
        assert result.imported == 3
        assert result.holdings == 2
        assert result.account.balance == Decimal("1000.00")
        assert result.account.currency == "USDT"

        txs = await container.transaction_repository.list_by_account(saved.id)
        tags = {tag for tx in txs for tag in tx.tags}
        assert "ext:binance:trade:buy-1" in tags
        assert "ext:binance:trade:sell-1" in tags
        assert "ext:binance:deposit:dep-1" in tags
        assert any(tx.type == TransactionType.EXPENSE and tx.amount == Decimal("50.00") for tx in txs)
        assert any(tx.type == TransactionType.INCOME and tx.amount == Decimal("20.00") for tx in txs)

        again = await container.sync_exchange_account.execute(saved.id)
        assert again.imported == 0
        txs_again = await container.transaction_repository.list_by_account(saved.id)
        assert len(txs_again) == len(txs)

        assert await container.delete_account.execute(saved.id) is True
        assert (
            await container.exchange_connection_repository.get_by_account_id(saved.id)
            is None
        )

    run_async(_run())


def test_connect_skips_probe_when_verify_false(container, monkeypatch) -> None:
    def _boom(**_kwargs):
        raise AssertionError("probe skipped")

    monkeypatch.setattr(
        container.connect_exchange_account._gateway,
        "test_credentials",
        _boom,
    )

    async def _run() -> None:
        saved = await container.connect_exchange_account.execute(
            account=make_account(name="X", currency="RUB", balance="0"),
            provider="binance",
            api_key="k",
            secret="s",
            verify=False,
        )
        assert saved.name == "Binance"
        link = await container.exchange_connection_repository.get_by_account_id(
            saved.id
        )
        assert link is not None

    run_async(_run())
