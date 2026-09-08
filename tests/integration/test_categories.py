"""Category use cases."""

from __future__ import annotations

import pytest

from lib.domain.entities.category import CategoryKind
from tests.conftest import run_async
from tests.factories import make_category


def test_create_unique_and_find_or_create(container) -> None:
    async def _run() -> None:
        created = await container.create_category.execute(
            make_category(name="Coffee")
        )
        with pytest.raises(ValueError):
            await container.create_category.execute(make_category(name="Coffee"))

        same = await container.find_or_create_category.execute("Coffee")
        assert same.id == created.id

        other = await container.find_or_create_category.execute("Tea")
        assert other.name == "Tea"

    run_async(_run())


def test_system_category_cannot_be_deleted(container) -> None:
    async def _run() -> None:
        system = await container.create_category.execute(
            make_category(name="SystemCat", is_system=True)
        )
        with pytest.raises(ValueError):
            await container.delete_category.execute(system.id)

        user = await container.create_category.execute(
            make_category(name="UserCat", is_system=False)
        )
        assert await container.delete_category.execute(user.id) is True

    run_async(_run())


def test_list_categories_for_type(container) -> None:
    async def _run() -> None:
        await container.create_category.execute(
            make_category(name="OnlyExpense", kind=CategoryKind.EXPENSE)
        )
        await container.create_category.execute(
            make_category(name="OnlyIncome", kind=CategoryKind.INCOME)
        )
        await container.create_category.execute(
            make_category(name="Both", kind=CategoryKind.BOTH)
        )
        for_expense = await container.list_categories.execute(for_type="expense")
        names = {c.name for c in for_expense}
        assert "OnlyExpense" in names
        assert "Both" in names
        assert "OnlyIncome" not in names

    run_async(_run())


def test_corporate_categories_isolated_per_account(container) -> None:
    async def _run() -> None:
        from tests.factories import make_account

        corp_a = await container.create_account.execute(
            make_account(name="Corp A", is_corporate=True)
        )
        corp_b = await container.create_account.execute(
            make_account(name="Corp B", is_corporate=True)
        )
        personal = await container.create_category.execute(
            make_category(name="Office")
        )
        cat_a = await container.create_category.execute(
            make_category(name="Office", account_id=corp_a.id)
        )
        cat_b = await container.create_category.execute(
            make_category(name="Office", account_id=corp_b.id)
        )
        assert personal.id != cat_a.id != cat_b.id

        personal_list = await container.list_categories.execute()
        assert personal.id in {c.id for c in personal_list}
        assert cat_a.id not in {c.id for c in personal_list}
        assert cat_b.id not in {c.id for c in personal_list}

        list_a = await container.list_categories.execute(account_id=corp_a.id)
        assert {c.id for c in list_a} == {cat_a.id}

        list_b = await container.list_categories.execute(account_id=corp_b.id)
        assert {c.id for c in list_b} == {cat_b.id}

        same = await container.find_or_create_category.execute(
            "Office", account_id=corp_a.id
        )
        assert same.id == cat_a.id

    run_async(_run())


def test_category_rename_updates_all_transactions(container) -> None:
    async def _run() -> None:
        from lib.domain.entities.transaction import TransactionItem
        from tests.factories import make_account, make_transaction

        personal = await container.create_account.execute(make_account(name="Cash"))
        corp = await container.create_account.execute(
            make_account(name="Firm", is_corporate=True)
        )
        cat = await container.create_category.execute(
            make_category(name="Сигареты")
        )
        first = await container.add_transaction.execute(
            make_transaction(personal.id, category="Сигареты", amount="10")
        )
        spaced = await container.add_transaction.execute(
            make_transaction(personal.id, category="  сигареты", amount="11")
        )
        receipt = await container.add_transaction.execute(
            make_transaction(personal.id, category="Сигареты", amount="12").model_copy(
                update={
                    "items": [
                        TransactionItem(name="Pack", amount="12", category="сигареты")
                    ]
                }
            )
        )
        corp_tx = await container.add_transaction.execute(
            make_transaction(corp.id, category="Сигареты", amount="99")
        )

        await container.update_category.execute(
            cat.model_copy(update={"name": "Табак", "icon": "smoking_rooms"})
        )

        saved_first = await container.transaction_repository.get_by_id(first.id)
        saved_spaced = await container.transaction_repository.get_by_id(spaced.id)
        saved_receipt = await container.transaction_repository.get_by_id(receipt.id)
        saved_corp = await container.transaction_repository.get_by_id(corp_tx.id)
        assert saved_first.category == "Табак"
        assert saved_spaced.category == "Табак"
        assert saved_receipt.category == "Табак"
        assert saved_receipt.items[0].category == "Табак"
        assert saved_corp.category == "Сигареты"

    run_async(_run())


def test_category_icon_update_canonicalizes_transaction_names(container) -> None:
    async def _run() -> None:
        from tests.factories import make_account, make_transaction

        account = await container.create_account.execute(make_account(name="Wallet"))
        cat = await container.create_category.execute(
            make_category(name="Сигареты")
        )
        tx = await container.add_transaction.execute(
            make_transaction(account.id, category="сигареты", amount="7")
        )
        await container.update_category.execute(
            cat.model_copy(update={"icon": "smoking_rooms", "color": "#EF4444"})
        )
        saved = await container.transaction_repository.get_by_id(tx.id)
        assert saved.category == "Сигареты"
        updated = await container.category_repository.get_by_id(cat.id)
        assert updated.icon == "smoking_rooms"
        assert updated.color == "#EF4444"

    run_async(_run())
