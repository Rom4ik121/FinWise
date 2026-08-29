"""Hands-free spoken transaction save."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from lib.domain.entities.account import Account
from lib.domain.entities.category import Category
from lib.domain.entities.transaction import TransactionType
from lib.infrastructure.services.voice_capture import save_spoken_transaction
from lib.presentation.voice_shortcut import is_voice_route


def test_is_voice_route() -> None:
    assert is_voice_route("finwise://voice") is True
    assert is_voice_route("/voice") is True
    assert is_voice_route("voice") is True
    assert is_voice_route("https://example/home") is False
    assert is_voice_route("/invoice") is False
    assert is_voice_route("") is False


def test_save_spoken_transaction_persists_expense() -> None:
    account = Account(name="Cash", currency="UZS")
    list_accounts = MagicMock()
    list_accounts.execute = AsyncMock(return_value=[account])
    finder = MagicMock()
    finder.execute = AsyncMock(return_value=Category(name="такси"))
    add_tx = MagicMock()
    add_tx.execute = AsyncMock(side_effect=lambda tx: tx)
    container = MagicMock()
    container.list_accounts = list_accounts
    container.find_or_create_category = finder
    container.add_transaction = add_tx

    async def _run() -> None:
        result = await save_spoken_transaction(container, "расход такси 500")
        assert result.ok is True
        assert result.category == "такси"
        add_tx.execute.assert_awaited()
        saved = add_tx.execute.await_args.args[0]
        assert saved.type is TransactionType.EXPENSE
        assert saved.amount == Decimal("500.00")

    asyncio.run(_run())


def test_prepare_speech_permissions_without_service() -> None:
    from lib.infrastructure.services import speech as speech_mod

    previous = speech_mod.get_speech_service()
    speech_mod.set_speech_service(None)
    try:

        async def _run() -> None:
            result = await speech_mod.prepare_speech_permissions()
            assert result["ok"] is False
            assert result["error"] == "unavailable"

        asyncio.run(_run())
    finally:
        speech_mod.set_speech_service(previous)


def test_save_spoken_requires_amount() -> None:
    container = MagicMock()

    async def _run() -> None:
        result = await save_spoken_transaction(container, "расход такси")
        assert result.ok is False
        assert result.error == "need_amount"

    asyncio.run(_run())
