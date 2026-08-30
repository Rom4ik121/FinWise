"""Align the sole cash account with the app display currency when needed."""

from __future__ import annotations

import logging
from typing import Any

from lib.domain.entities.currency_codes import normalize_currency_code
from lib.domain.entities.money import quantize_money
from lib.domain.services.rate_book import RateBook

logger = logging.getLogger("finanse.domain.use_cases.align_currencies")


async def align_sole_account_currency(container: Any) -> bool:
    """If there is exactly one account and it differs from settings base, convert it.

    Converts ``initial_balance``, ``balance``, and each transaction amount via
    ``RateBook``. Refuses (returns ``False``) when any rate is missing — never
    silently relabels currency codes without converting money.
    """
    if (
        container.get_settings is None
        or container.list_accounts is None
        or container.currency_repository is None
        or container.account_repository is None
        or container.transaction_repository is None
    ):
        return False

    settings = await container.get_settings.execute()
    base = normalize_currency_code(settings.default_currency)
    accounts = await container.list_accounts.execute(active_only=False)
    if len(accounts) != 1:
        return False

    account = accounts[0]
    current = normalize_currency_code(account.currency)
    if current == base:
        return False

    rates = await container.currency_repository.list_rates()
    book = RateBook(rates)

    new_initial = book.convert(account.initial_balance, current, base)
    if new_initial is None:
        logger.warning(
            "Cannot align sole account %s: missing rate %s→%s",
            account.name,
            current,
            base,
        )
        return False

    txs = []
    if container.list_transactions is not None:
        txs = await container.list_transactions.execute(account_id=account.id)

    converted_rows: list[tuple[Any, object]] = []
    for tx in txs:
        src = normalize_currency_code(tx.currency)
        if src == base:
            continue
        converted = book.convert(tx.amount, src, base)
        if converted is None:
            logger.warning(
                "Cannot align sole account %s: missing rate for tx %s (%s→%s)",
                account.name,
                tx.id,
                src,
                base,
            )
            return False
        converted_rows.append(
            (
                tx,
                tx.model_copy(
                    update={
                        "currency": base,
                        "amount": quantize_money(converted),
                    }
                ),
            )
        )

    for _old, updated_tx in converted_rows:
        await container.transaction_repository.update(updated_tx)

    patched = account.model_copy(
        update={
            "currency": base,
            "initial_balance": quantize_money(new_initial),
        }
    )
    await container.account_repository.update(patched)

    if container.recalculate_account_balance is not None:
        await container.recalculate_account_balance.execute(account.id)
    else:
        new_balance = book.convert(account.balance, current, base)
        if new_balance is None:
            return False
        await container.account_repository.update(
            patched.model_copy(update={"balance": quantize_money(new_balance)})
        )

    logger.info(
        "Aligned sole account %s currency %s → %s (converted amounts)",
        account.name,
        current,
        base,
    )
    return True
